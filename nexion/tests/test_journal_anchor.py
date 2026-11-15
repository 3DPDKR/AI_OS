"""Offline-only HMAC anchor experiments; separate local files, no network."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from nexion.consent import ConsentStore, ConsentError
from nexion.distributed_consent import DistributedConsentLab, Unavailable
from nexion.revocation_journal import RevocationJournal, JournalCorruption, GENESIS
from nexion.journal_anchor import JournalAnchor, AnchorMismatch


KEY = bytes(range(32))  # Deterministic test ONLY; never a real shared secret.


class JournalAnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.journal = self.root / "journal.sqlite3"
        self.anchor = self.root / "signed-anchor.json"
        self.consent = ConsentStore(str(self.root / "consent.sqlite3"))
        self.alice = self.enroll("alice")
        self.bob = self.enroll("bob")
        self.lab = self.new_lab()

    def tearDown(self):
        if self.lab:
            self.lab.close()
        self.consent.close()
        self.temp.cleanup()

    def enroll(self, alias):
        e = self.consent.apply(alias=alias, contact=f"{alias}@example.invalid",
                               scopes={"peer_chat"}, explicitly_agreed=True)
        self.consent.confirm(e.participant_id, e.confirmation_token)
        return e

    def new_lab(self, *, key=KEY):
        return DistributedConsentLab(self.consent, ["a", "b"],
                                     journal_path=self.journal,
                                     anchor_path=self.anchor, anchor_key=key)

    def reopen(self):
        self.lab.close()
        self.lab = None
        self.lab = self.new_lab()
        return self.lab

    def test_genesis_anchor_created_and_verified(self):
        self.assertTrue(self.anchor.is_file())
        self.assertEqual(self.lab._journal.verify(), 0)
        document = json.loads(self.anchor.read_text())
        self.assertEqual(document["state"]["sequence"], 0)
        self.assertEqual(document["state"]["digest"], GENESIS)
        self.assertEqual(len(document["mac"]), 64)

    def test_signed_withdrawal_and_checkpoint_survive_restart(self):
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(self.lab.sync("a")["cursor"], 1)
        self.assertEqual(self.reopen().replica_state("a")["cursor"], 1)
        self.assertEqual(self.lab._journal.verify(), 1)

    def test_single_file_rollback_detected_without_modifying_anchor(self):
        backup = self.root / "old-journal.sqlite3"
        # Signed state before the first revocation.
        with sqlite3.connect(backup) as out:
            self.lab._journal.db.backup(out)
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.lab.close(); self.lab = None
        shutil.copyfile(backup, self.journal)
        with self.assertRaises(JournalCorruption):
            self.new_lab()

    def test_rewritten_consistent_head_still_rejected(self):
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        with sqlite3.connect(self.journal) as conn:
            conn.execute("DELETE FROM journal_events")
            conn.execute("UPDATE journal_head SET sequence=0,digest=?", (GENESIS,))
        with self.assertRaises(Unavailable):
            self.lab.sync("a")

    def test_appended_forged_technically_consistent_event_rejected(self):
        head = self.lab._journal._head()
        fake = self.lab._journal._hash(1, self.bob.participant_id, head["digest"])
        with sqlite3.connect(self.journal) as conn:
            conn.execute("INSERT INTO journal_events VALUES (1,?,?,?)",
                         (self.bob.participant_id, head["digest"], fake))
            conn.execute("UPDATE journal_head SET sequence=1,digest=?", (fake,))
        with self.assertRaises(Unavailable):
            self.lab.queue("a", self.alice.access_token, self.bob.participant_id,
                           "not accepted", "message")

    def test_checkpoint_regression_with_valid_chain_digest_is_rejected(self):
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.lab.sync("a")
        with sqlite3.connect(self.journal) as conn:
            conn.execute("UPDATE replica_checkpoints SET sequence=0,digest=? WHERE node_name='a'",
                         (GENESIS,))
        with self.assertRaises(Unavailable):
            self.lab.sync("a")

    def test_pending_intent_is_authenticated(self):
        self.lab._journal.begin_withdrawal(self.bob.participant_id)
        document = json.loads(self.anchor.read_text())
        self.assertEqual(document["state"]["pending"], self.bob.participant_id)
        with sqlite3.connect(self.journal) as conn:
            conn.execute("UPDATE journal_head SET pending_participant=NULL")
        with self.assertRaises(Unavailable):
            self.lab.queue("a", self.alice.access_token, self.bob.participant_id,
                           "blocked", "msg")

    def test_valid_pending_intent_still_refuses_open(self):
        self.lab._journal.begin_withdrawal(self.bob.participant_id)
        self.lab.close(); self.lab = None
        with self.assertRaises(JournalCorruption):
            self.new_lab()

    def test_missing_anchor_on_existing_journal_fails(self):
        self.lab.close(); self.lab = None
        self.anchor.unlink()
        with self.assertRaises(JournalCorruption):
            self.new_lab()

    def test_journal_recreation_with_old_anchor_fails(self):
        self.lab.close(); self.lab = None
        self.journal.unlink()
        with self.assertRaises(AnchorMismatch):
            self.new_lab()

    def test_wrong_key_fails_closed(self):
        self.lab.close(); self.lab = None
        with self.assertRaises(JournalCorruption):
            self.new_lab(key=b"x"*32)

    def test_modified_anchor_mac_fails_closed(self):
        document = json.loads(self.anchor.read_text())
        document["mac"] = "f" * 64
        self.anchor.write_text(json.dumps(document))
        with self.assertRaises(Unavailable):
            self.lab.sync("a")

    def test_invalid_or_missing_configuration(self):
        with self.assertRaises(ValueError):
            RevocationJournal(self.root / "other.sqlite3", anchor_path=self.root / "orphan.json")
        with self.assertRaises(ValueError):
            RevocationJournal(self.root / "other.sqlite3", anchor_path=self.root / "orphan.json", anchor_key=b"weak")
        with self.assertRaises(ValueError):
            RevocationJournal(self.root / "other.sqlite3", anchor_path=self.root / "other.sqlite3", anchor_key=KEY)

    def test_existing_unanchored_journal_cannot_silently_enroll(self):
        separate = self.root / "legacy.sqlite3"
        plain = RevocationJournal(separate)
        plain.close()
        with self.assertRaises(JournalCorruption):
            RevocationJournal(separate, anchor_path=self.root / "new.json", anchor_key=KEY)
        self.assertFalse((self.root / "new.json").exists())

    def test_power_loss_between_commit_and_anchor_write_fails_closed(self):
        # A simulated crash injection at the separate-file boundary.
        def fail_anchor_write():
            raise OSError("simulated power loss after journal commit")
        self.lab._journal._update_anchor = fail_anchor_write
        with self.assertRaises(OSError):
            self.lab._journal.begin_withdrawal(self.bob.participant_id)
        self.lab.close(); self.lab = None
        with self.assertRaises(JournalCorruption):
            self.new_lab()

    def test_unmodified_previous_lab_still_behaves_the_same(self):
        basic = self.root / "legacy.sqlite3"
        lab = DistributedConsentLab(self.consent, ["legacy"], journal_path=basic)
        try:
            lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
            self.assertEqual(lab.sync("legacy")["cursor"], 1)
        finally:
            lab.close()


if __name__ == "__main__":
    unittest.main()
