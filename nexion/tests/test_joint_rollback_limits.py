"""Offline counterexample to freshness claims after all evidence is rolled back.

This does not perform a real attack, restore a production system, grant consent,
or contact any participant. It only copies disposable SQLite laboratory fixtures.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest

from nexion.consent import ConsentStore
from nexion.distributed_consent import DistributedConsentLab
from nexion.evidence_freshness import FLOOR_FORMAT, verify_witness_floor
from nexion.evidence_triage import FORMAT as WITNESS_FORMAT

WITNESS_KEY = bytes(range(32))
FLOOR_KEY = bytes(range(32, 64))
ANCHOR_KEY = bytes(range(64, 96))
SCOPE = "offline-joint-rollback-fixture"


def _sign(fmt, state, key):
    def canonical(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    envelope = {"format": fmt, "state": state}
    return canonical({**envelope, "mac": hmac.new(
        key, canonical(envelope), hashlib.sha256).hexdigest()})


class JointRollbackLimitsTests(unittest.TestCase):
    """Two different histories can yield indistinguishable local input bytes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.authority = self.root / "authority.db"
        self.journal = self.root / "journal.db"
        self.anchor = self.root / "anchor.json"
        self.store = None
        self.lab = None

        self._start()
        person = self.store.apply(alias="fixture", contact="fixture@example.invalid",
                                  scopes={"peer_chat"}, explicitly_agreed=True)
        self.store.confirm(person.participant_id, person.confirmation_token)
        self.participant = person
        self.initial_witness = self._witness()
        self.initial_floor = self._floor()
        self._stop()
        self.initial_files = self._files()

    def tearDown(self):
        self._stop()
        self.tmp.cleanup()

    def _start(self):
        self.store = ConsentStore(self.authority)
        self.lab = DistributedConsentLab(
            self.store, ["n1"], journal_path=self.journal,
            anchor_path=self.anchor, anchor_key=ANCHOR_KEY)

    def _stop(self):
        if self.lab is not None:
            self.lab.close()
            self.lab = None
        if self.store is not None:
            self.store.close()
            self.store = None

    def _files(self):
        # SQLite database handles must be closed before capturing their bytes.
        self.assertIsNone(self.store)
        self.assertIsNone(self.lab)
        return {p.name: p.read_bytes() for p in (self.authority, self.journal, self.anchor)}

    def _restore(self, files):
        self.assertIsNone(self.lab)
        self.assertIsNone(self.store)
        for path in (self.authority, self.journal, self.anchor):
            path.write_bytes(files[path.name])

    def _witness(self):
        head = self.lab._journal._head()
        return _sign(WITNESS_FORMAT, {"sequence": head["sequence"],
                      "digest": head["digest"], "withdrawn_digest": "0" * 64,
                      "checkpoint_digest": "0" * 64}, WITNESS_KEY)

    def _floor(self):
        head = self.lab._journal._head()
        return _sign(FLOOR_FORMAT, {"scope": SCOPE,
                      "min_sequence": head["sequence"],
                      "min_digest": head["digest"]}, FLOOR_KEY)

    def _assess(self, witness, floor):
        result = verify_witness_floor(
            self.journal, witness_document=witness, witness_key=WITNESS_KEY,
            floor_document=floor, floor_key=FLOOR_KEY, expected_scope=SCOPE)
        self.assertFalse(result.delivery_permitted)
        self.assertFalse(result.repair_permitted)
        return result.classification

    def _advance(self):
        self._start()
        self.lab.withdraw(self.participant.participant_id,
                          self.participant.withdrawal_token)
        current_witness = self._witness()
        current_floor = self._floor()
        self._stop()
        current_files = self._files()
        self.assertNotEqual(current_files[self.journal.name],
                            self.initial_files[self.journal.name])
        return current_files, current_witness, current_floor

    def test_never_advanced_and_jointly_restored_are_indistinguishable(self):
        first_observation = (self._files(), self.initial_witness, self.initial_floor)
        never_advanced = self._assess(self.initial_witness, self.initial_floor)
        self._advance()  # An actual simulated withdrawal happened in this history.
        self._restore(self.initial_files)  # All *local* evidence is now old.
        second_observation = (self._files(), self.initial_witness, self.initial_floor)
        self.assertEqual(first_observation, second_observation)
        self.assertEqual(never_advanced, "BOUNDED_CONSISTENT")
        self.assertEqual(self._assess(self.initial_witness, self.initial_floor),
                         never_advanced)

    def test_preserved_external_floor_detects_joint_local_rollback(self):
        _, _, trusted_new_floor = self._advance()
        self._restore(self.initial_files)
        self.assertEqual(self._assess(self.initial_witness, trusted_new_floor),
                         "REPLAY_OR_ROLLBACK")

    def test_local_journal_rollback_with_current_witness_and_floor_is_detected(self):
        _, current_witness, current_floor = self._advance()
        self._restore(self.initial_files)
        self.assertEqual(self._assess(current_witness, current_floor),
                         "REPLAY_OR_ROLLBACK")

    def test_stale_floor_with_current_journal_is_not_recognized_as_stale(self):
        _, current_witness, _ = self._advance()
        self.assertEqual(self._assess(current_witness, self.initial_floor),
                         "BOUNDED_CONSISTENT")

    def test_stale_witness_and_floor_with_current_journal_are_rejected(self):
        self._advance()
        self.assertEqual(self._assess(self.initial_witness, self.initial_floor),
                         "UNTRUSTED")

    def test_unauthenticated_new_floor_does_not_help(self):
        _, _, current_floor = self._advance()
        self._restore(self.initial_files)
        altered = json.loads(current_floor)
        altered["state"]["min_sequence"] = 0
        self.assertEqual(self._assess(self.initial_witness,
                                      json.dumps(altered).encode("utf-8")), "UNTRUSTED")

    def test_joint_rollback_remains_invisible_after_fresh_process_restart(self):
        self._advance()
        self._restore(self.initial_files)
        self._start()
        self.assertEqual(self.lab._journal._head()["sequence"], 0)
        self._stop()
        self.assertEqual(self._assess(self.initial_witness, self.initial_floor),
                         "BOUNDED_CONSISTENT")

    def test_diagnostics_leave_sqlite_and_anchor_untouched(self):
        self._advance()
        before = {p: hashlib.sha256(data).hexdigest() for p, data in self._files().items()}
        self._assess(self.initial_witness, self.initial_floor)
        after = {p: hashlib.sha256(data).hexdigest() for p, data in self._files().items()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
