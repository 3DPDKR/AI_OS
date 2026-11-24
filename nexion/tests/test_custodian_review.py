"""Local SQLite fixtures and dummy keys only."""
import json
from pathlib import Path
import tempfile
import unittest

from nexion.custodian_review import review_custodians
from nexion.revocation_journal import GENESIS, RevocationJournal
from test_evidence_freshness import signed, W_KEY, F_KEY, SCOPE, FLOOR_FORMAT, WITNESS_FORMAT


class CustodianReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "journal.db"
        journal = RevocationJournal(self.path)
        journal.close()
        self.keys = {"a": F_KEY, "b": bytes(range(64, 96)), "c": bytes(range(96, 128))}
        self.docs = {name: self.floor(key) for name, key in self.keys.items()}
        self.witness = signed(WITNESS_FORMAT, {"sequence": 0, "digest": GENESIS,
                              "withdrawn_digest": GENESIS, "checkpoint_digest": GENESIS}, W_KEY)

    def floor(self, key, seq=0, digest=GENESIS, scope=SCOPE):
        return signed(FLOOR_FORMAT, {"scope": scope, "min_sequence": seq,
                      "min_digest": digest}, key)

    def check(self, expected, **kwargs):
        args = dict(witness_document=self.witness, witness_key=W_KEY,
                    custodian_keys=self.keys, floor_documents=self.docs, expected_scope=SCOPE)
        args.update(kwargs)
        result = review_custodians(self.path, **args)
        self.assertEqual(result.classification, expected)
        self.assertFalse(result.delivery_permitted)
        self.assertFalse(result.repair_permitted)

    def test_unanimous(self):
        self.check("BOUNDED_CONSISTENT")

    def test_one_missing(self):
        del self.docs["b"]
        self.check("CUSTODIAN_UNAVAILABLE")

    def test_all_missing(self):
        self.check("CUSTODIAN_UNAVAILABLE", floor_documents={})

    def test_extra_identity(self):
        self.docs["unknown"] = self.docs["a"]
        self.check("UNTRUSTED")

    def test_single_member(self):
        self.check("UNTRUSTED", custodian_keys={"a": F_KEY})

    def test_reused_key(self):
        self.keys["b"] = F_KEY
        self.check("UNTRUSTED")

    def test_witness_key_reused(self):
        self.keys["b"] = W_KEY
        self.check("UNTRUSTED")

    def test_swapped_replies(self):
        self.docs["a"], self.docs["b"] = self.docs["b"], self.docs["a"]
        self.check("UNTRUSTED")

    def test_tampered_mac(self):
        obj = json.loads(self.docs["b"])
        obj["state"]["min_sequence"] = 1
        self.docs["b"] = json.dumps(obj).encode()
        self.check("UNTRUSTED")

    def test_wrong_scope(self):
        self.docs["b"] = self.floor(self.keys["b"], scope="other")
        self.check("UNTRUSTED")

    def test_different_sequence(self):
        self.docs["b"] = self.floor(self.keys["b"], seq=1)
        self.check("CUSTODIAN_DISAGREEMENT")

    def test_same_sequence_different_digest(self):
        self.docs["b"] = self.floor(self.keys["b"], digest="f" * 64)
        self.check("CUSTODIAN_DISAGREEMENT")

    def test_agreed_newer_floor_blocks_old_journal(self):
        self.docs = {name: self.floor(key, seq=1) for name, key in self.keys.items()}
        self.check("REPLAY_OR_ROLLBACK")

    def test_bad_witness(self):
        self.check("UNTRUSTED", witness_document=b"invalid")

    def test_read_only(self):
        before = self.path.read_bytes()
        self.check("BOUNDED_CONSISTENT")
        self.assertEqual(before, self.path.read_bytes())

    def test_malformed_deep_json(self):
        self.docs["b"] = b"[" * 1500 + b"]" * 1500
        self.check("UNTRUSTED")
