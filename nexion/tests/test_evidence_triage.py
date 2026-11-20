"""Offline, disposable read-only evidence triage tests (no real witnesses)."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nexion.consent import ConsentStore
from nexion.distributed_consent import DistributedConsentLab
from nexion.evidence_triage import FORMAT, triage_anchor_mismatch

ANCHOR_KEY = bytes(range(32))     # Dummy, NEVER use operationally.
WITNESS_KEY = bytes(range(32, 64)) # Distinct dummy witness test key.


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


class EvidenceTriageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.a, self.j, self.anchor = (root / n for n in
                                      ("authority.db", "journal.db", "anchor.json"))
        self.store = ConsentStore(self.a)
        self.sender = self._enroll("sender")
        self.target = self._enroll("target")
        self.lab = DistributedConsentLab(
            self.store, ["node-a"], journal_path=self.j,
            anchor_path=self.anchor, anchor_key=ANCHOR_KEY)

    def _enroll(self, alias):
        p = self.store.apply(alias=alias, contact=alias + "@example.invalid",
                             scopes={"peer_chat"}, explicitly_agreed=True)
        self.store.confirm(p.participant_id, p.confirmation_token)
        return p

    def _witness(self, *, key=WITNESS_KEY):
        head = self.lab._journal._head()
        cps = [list(row) for row in self.lab._journal.db.execute(
            "SELECT node_name,sequence,digest FROM replica_checkpoints ORDER BY node_name")]
        withdrawn = sorted(row[0] for row in self.store.db.execute(
            "SELECT id FROM participants WHERE state='withdrawn'"))
        state = {"sequence": head["sequence"], "digest": head["digest"],
                 "withdrawn_digest": hashlib.sha256(canonical(withdrawn)).hexdigest(),
                 "checkpoint_digest": hashlib.sha256(canonical(cps)).hexdigest()}
        doc = {"format": FORMAT, "state": state}
        doc["mac"] = hmac.new(key, canonical(doc), hashlib.sha256).hexdigest()
        return canonical(doc)

    def _triage(self, witness=None, **changes):
        args = {"anchor_key": ANCHOR_KEY, "witness_key": WITNESS_KEY,
                "witness_document": self._witness() if witness is None else witness}
        args.update(changes)
        result = triage_anchor_mismatch(self.a, self.j, self.anchor, **args)
        self.assertFalse(result.delivery_permitted)
        self.assertFalse(result.repair_permitted)
        return result

    def _post_commit_crash(self):
        self.lab._journal.begin_withdrawal(self.target.participant_id)
        self.store.withdraw(self.target.participant_id, self.target.withdrawal_token)
        with mock.patch.object(self.lab._journal, "_update_anchor",
                               side_effect=RuntimeError("deliberate lab failure")):
            with self.assertRaises(RuntimeError):
                self.lab._journal.finish_withdrawal(self.target.participant_id)

    def test_01_clean_baseline_still_denies_permission(self):
        self.assertEqual(self._triage().classification, "MATCHED_BUT_NOT_AUTHORIZED")

    def test_02_known_crash_window_is_candidate_not_repair(self):
        self._post_commit_crash()
        self.assertEqual(self._triage().classification, "POSSIBLE_POST_COMMIT_ANCHOR_LAG")

    def test_03_stale_witness_does_not_attest_new_state(self):
        witness = self._witness()
        self._post_commit_crash()
        self.assertEqual(self._triage(witness).classification, "UNTRUSTED")

    def test_04_witness_tampering_is_rejected(self):
        document = json.loads(self._witness())
        document["state"]["sequence"] = 42
        self.assertEqual(self._triage(canonical(document)).classification, "UNTRUSTED")

    def test_05_wrong_witness_key_is_rejected(self):
        self.assertEqual(self._triage(witness_key=b"x" * 32).classification, "UNTRUSTED")

    def test_06_same_keys_are_rejected(self):
        self.assertEqual(self._triage(witness_key=ANCHOR_KEY).classification, "UNTRUSTED")

    def test_07_unauthenticated_anchor_is_rejected(self):
        body = json.loads(self.anchor.read_bytes())
        body["mac"] = "a" * 64
        self.anchor.write_bytes(canonical(body))
        self.assertEqual(self._triage().classification, "UNTRUSTED")

    def test_08_valid_witness_does_not_excuse_altered_journal(self):
        self.lab.withdraw(self.target.participant_id, self.target.withdrawal_token)
        witness = self._witness()
        self.lab._journal.db.execute("UPDATE journal_events SET prev_digest=?",
                                     ("f" * 64,))
        self.lab._journal.db.commit()
        self.assertEqual(self._triage(witness).classification, "UNTRUSTED")

    def test_09_missing_revocation_event_in_authority_is_rejected(self):
        self.store.withdraw(self.target.participant_id, self.target.withdrawal_token)
        self.assertEqual(self._triage().classification, "UNTRUSTED")

    def test_10_unfinished_intent_is_not_repairable(self):
        self.lab._journal.begin_withdrawal(self.target.participant_id)
        self.assertEqual(self._triage().classification, "INCOMPLETE_INTENT")

    def test_11_missing_witness_is_rejected(self):
        self.assertEqual(self._triage(b"").classification, "UNTRUSTED")

    def test_12_missing_journal_is_rejected(self):
        witness = self._witness()
        self.lab.close()
        self.j.unlink()
        self.assertEqual(self._triage(witness).classification, "UNTRUSTED")
        self.lab = None

    def test_13_inspection_does_not_change_files(self):
        self._post_commit_crash()
        paths = (self.a, self.j, self.anchor)
        before = [hashlib.sha256(p.read_bytes()).digest() for p in paths]
        self._triage()
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).digest() for p in paths])

    def test_14_witness_with_additional_field_is_rejected(self):
        document = json.loads(self._witness())
        document["permit"] = True
        self.assertEqual(self._triage(canonical(document)).classification, "UNTRUSTED")

    def test_15_both_signed_files_rolled_back_against_fresh_witness(self):
        prior_journal = self.j.read_bytes()
        prior_anchor = self.anchor.read_bytes()
        self.lab.withdraw(self.target.participant_id, self.target.withdrawal_token)
        current_witness = self._witness()
        # Simulate coordinated replacement of journal and anchor; authority retains withdrawal.
        self.lab.close()
        self.j.write_bytes(prior_journal)
        self.anchor.write_bytes(prior_anchor)
        self.assertEqual(self._triage(current_witness).classification, "UNTRUSTED")
        self.lab = None

    def test_16_checkpoint_mismatch_is_rejected(self):
        self.lab._journal.db.execute("INSERT INTO replica_checkpoints VALUES (?,?,?)",
                                     ("node-a", 1, "e"*64))
        self.lab._journal.db.commit()
        self.assertEqual(self._triage().classification, "UNTRUSTED")

    def test_17_path_alias_or_symlink_is_rejected(self):
        self.assertEqual(triage_anchor_mismatch(
            self.a, self.a, self.anchor, anchor_key=ANCHOR_KEY,
            witness_document=self._witness(), witness_key=WITNESS_KEY
        ).classification, "UNTRUSTED")

    def test_18_expired_or_replayed_witness_freshness_not_assumed(self):
        # Model deliberately refuses to assert freshness: even matching evidence
        # cannot give permissions, and monotonic freshness is NOT implemented.
        self.assertEqual(self._triage().classification, "MATCHED_BUT_NOT_AUTHORIZED")

    def tearDown(self):  # ensures tests with intentionally closed lab also cleanup
        if self.lab is not None:
            self.lab.close()
        self.store.close()
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
