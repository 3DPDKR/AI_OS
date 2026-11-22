"""Disposable SQLite laboratory tests; HMAC keys here are NOT operational secrets."""
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
from nexion.revocation_journal import GENESIS

W_KEY = bytes(range(32))
F_KEY = bytes(range(32, 64))
SCOPE = "nexion-offline-simulation"


def signed(fmt, state, key):
    def canonical(obj):
        return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode()
    envelope = {"format": fmt, "state": state}
    return canonical({**envelope, "mac": hmac.new(key, canonical(envelope), hashlib.sha256).hexdigest()})


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "authority.db"
        self.journal = root / "journal.db"
        self.anchor = root / "anchor.json"
        self.store = ConsentStore(self.db_path)
        self.people = []
        for alias in ("a", "b", "c"):
            p = self.store.apply(alias=alias, contact=alias + "@example.invalid",
                                 scopes={"peer_chat"}, explicitly_agreed=True)
            self.store.confirm(p.participant_id, p.confirmation_token)
            self.people.append(p)
        self.lab = DistributedConsentLab(self.store, ["n1"], journal_path=self.journal)

    def tearDown(self):
        self.lab.close()
        self.store.close()
        self.temp.cleanup()

    def _witness(self):
        head = self.lab._journal._head()
        return signed(WITNESS_FORMAT, {"sequence": head["sequence"],
                    "digest": head["digest"], "withdrawn_digest": "0" * 64,
                    "checkpoint_digest": "0" * 64}, W_KEY)

    def _floor(self, sequence=None, digest=None, scope=SCOPE):
        head = self.lab._journal._head()
        return signed(FLOOR_FORMAT, {"scope": scope,
                      "min_sequence": head["sequence"] if sequence is None else sequence,
                      "min_digest": head["digest"] if digest is None else digest}, F_KEY)

    def _check(self, witness=None, floor=None, **kwargs):
        args = {"witness_document": self._witness() if witness is None else witness,
                "witness_key": W_KEY, "floor_document": self._floor() if floor is None else floor,
                "floor_key": F_KEY, "expected_scope": SCOPE}
        args.update(kwargs)
        outcome = verify_witness_floor(self.journal, **args)
        self.assertFalse(outcome.delivery_permitted)
        self.assertFalse(outcome.repair_permitted)
        return outcome.classification

    def test_initial_genesis_floor(self):
        self.assertEqual(self._check(), "BOUNDED_CONSISTENT")

    def test_exact_floor_after_withdrawal(self):
        self.lab.withdraw(self.people[0].participant_id, self.people[0].withdrawal_token)
        self.assertEqual(self._check(), "BOUNDED_CONSISTENT")

    def test_future_verified_chain_above_floor(self):
        floor = self._floor()
        self.lab.withdraw(self.people[0].participant_id, self.people[0].withdrawal_token)
        self.assertEqual(self._check(floor=floor), "BOUNDED_CONSISTENT")

    def test_old_signed_witness_is_replay(self):
        old = self._witness()
        self.lab.withdraw(self.people[0].participant_id, self.people[0].withdrawal_token)
        self.assertEqual(self._check(witness=old), "REPLAY_OR_ROLLBACK")

    def test_rolled_back_journal_below_floor(self):
        self.lab.withdraw(self.people[0].participant_id, self.people[0].withdrawal_token)
        floor = self._floor()
        old = self._witness()
        self.lab._journal.db.execute("DELETE FROM journal_events")
        self.lab._journal.db.execute("UPDATE journal_head SET sequence=0,digest=?", (GENESIS,))
        self.lab._journal.db.commit()
        self.assertEqual(self._check(witness=old, floor=floor), "REPLAY_OR_ROLLBACK")

    def test_mismatch_floor_digest_rejected(self):
        self.assertEqual(self._check(floor=self._floor(digest="f" * 64)), "UNTRUSTED")

    def test_witness_mac_tampering_rejected(self):
        obj = json.loads(self._witness())
        obj["state"]["digest"] = "f" * 64
        self.assertEqual(self._check(witness=json.dumps(obj).encode()), "UNTRUSTED")

    def test_floor_mac_tampering_rejected(self):
        obj = json.loads(self._floor())
        obj["state"]["min_sequence"] = 5
        self.assertEqual(self._check(floor=json.dumps(obj).encode()), "UNTRUSTED")

    def test_wrong_scope_rejected(self):
        self.assertEqual(self._check(floor=self._floor(scope="another-lab")), "UNTRUSTED")

    def test_keys_must_differ(self):
        self.assertEqual(self._check(floor_key=W_KEY), "UNTRUSTED")

    def test_duplicate_json_keys_rejected(self):
        raw = self._witness().replace(b'"format":', b'"format":"X","format":')
        self.assertEqual(self._check(witness=raw), "UNTRUSTED")

    def test_corrupt_journal_chain_rejected(self):
        self.lab.withdraw(self.people[0].participant_id, self.people[0].withdrawal_token)
        self.lab._journal.db.execute("UPDATE journal_events SET prev_digest='fake'")
        self.lab._journal.db.commit()
        self.assertEqual(self._check(), "UNTRUSTED")

    def test_read_only_does_not_modify_evidence(self):
        self.lab.withdraw(self.people[0].participant_id, self.people[0].withdrawal_token)
        before = hashlib.sha256(self.journal.read_bytes()).digest()
        self.assertEqual(self._check(), "BOUNDED_CONSISTENT")
        self.assertEqual(hashlib.sha256(self.journal.read_bytes()).digest(), before)

    def test_no_permissions_even_for_valid_witness(self):
        result = verify_witness_floor(self.journal, witness_document=self._witness(),
                                     witness_key=W_KEY, floor_document=self._floor(),
                                     floor_key=F_KEY, expected_scope=SCOPE)
        self.assertEqual((result.delivery_permitted, result.repair_permitted), (False, False))


if __name__ == "__main__":
    unittest.main()
