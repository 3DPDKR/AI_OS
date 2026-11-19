"""Offline fault matrix at the authority/journal/anchor commit boundaries.

Only disposable SQLite databases and a test HMAC key are used. These tests
*observe* existing behavior; they do not implement or authorize any repair.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nexion.consent import ConsentError, ConsentStore
from nexion.distributed_consent import DistributedConsentLab, Unavailable
from nexion.recovery_protocol import draft_recovery
from nexion.recovery_review import assess_recovery
from nexion.revocation_journal import JournalCorruption, RevocationJournal


KEY = bytes(range(32))  # Dummy key used only for the disposable lab.


class RecoveryCrashWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.authority_path = root / "authority.db"
        self.journal_path = root / "revocation.db"
        self.anchor_path = root / "anchor.json"
        self.store = ConsentStore(self.authority_path)
        self.sender = self._enroll("sender")
        self.target = self._enroll("target")
        self.lab = DistributedConsentLab(
            self.store, ["node-a"], journal_path=self.journal_path,
            anchor_path=self.anchor_path, anchor_key=KEY)

    def tearDown(self):
        if self.lab is not None:
            self.lab.close()
        self.store.close()
        self.temp.cleanup()

    def _enroll(self, alias):
        enrollment = self.store.apply(
            alias=alias, contact=f"{alias}@example.invalid",
            scopes={"peer_chat"}, explicitly_agreed=True)
        self.store.confirm(enrollment.participant_id,
                           enrollment.confirmation_token)
        return enrollment

    def _withdraw_authority(self):
        self.store.withdraw(self.target.participant_id,
                            self.target.withdrawal_token)

    def _close_lab(self):
        self.lab.close()
        self.lab = None

    def _assert_restart_denied(self):
        self._close_lab()
        with self.assertRaises((JournalCorruption, Unavailable)):
            DistributedConsentLab(
                self.store, ["node-a"], journal_path=self.journal_path,
                anchor_path=self.anchor_path, anchor_key=KEY)

    def _review_after_restart(self, expected):
        self._close_lab()
        handle = RevocationJournal.open_for_review(
            self.journal_path, anchor_path=self.anchor_path, anchor_key=KEY)
        try:
            observation = assess_recovery(self.store, handle)
            self.assertEqual(observation.state, expected)
            self.assertFalse(observation.delivery_permitted)
        finally:
            handle.close()

    def _assert_withdrawn(self):
        state = self.store.db.execute(
            "SELECT state FROM participants WHERE id=?",
            (self.target.participant_id,)).fetchone()[0]
        self.assertEqual(state, "withdrawn")

    def test_clean_baseline_is_explicitly_not_a_repair_approval(self):
        result = assess_recovery(self.store, self.lab._journal)
        self.assertEqual(result.state, "CLEAN")
        self.assertEqual(self.lab._journal.verify(), 0)
        self.assertEqual(self.lab._journal.events(), ())

    def test_crash_after_pending_intent_before_authority_commit(self):
        self.lab._journal.begin_withdrawal(self.target.participant_id)
        self.assertEqual(assess_recovery(self.store, self.lab._journal).state,
                         "PENDING_UNCOMMITTED")
        with self.assertRaises(Unavailable):
            self.lab.queue("node-a", self.sender.access_token,
                           self.target.participant_id, "deny", "pending")
        self._review_after_restart("PENDING_UNCOMMITTED")

    def test_crash_after_authority_commit_before_journal_append(self):
        self.lab._journal.begin_withdrawal(self.target.participant_id)
        self._withdraw_authority()
        assessment = assess_recovery(self.store, self.lab._journal)
        self.assertEqual(assessment.state, "PENDING_COMMITTED")
        self.assertFalse(assessment.delivery_permitted)
        self.assertIn("append_missing_revocation_event",
                      draft_recovery(self.store, self.lab._journal).action)
        self._assert_withdrawn()
        self._review_after_restart("PENDING_COMMITTED")

    def test_fault_during_journal_transaction_rolls_back(self):
        self.lab._journal.begin_withdrawal(self.target.participant_id)
        self._withdraw_authority()
        before_anchor = self.anchor_path.read_bytes()
        # The journal's hash is computed inside BEGIN IMMEDIATE, before COMMIT.
        with mock.patch.object(self.lab._journal, "_hash",
                               side_effect=RuntimeError("simulated pre-commit failure")):
            with self.assertRaisesRegex(RuntimeError, "pre-commit"):
                self.lab._journal.finish_withdrawal(self.target.participant_id)
        self.assertEqual(self.lab._journal._head()["sequence"], 0)
        self.assertEqual(self.lab._journal._head()["pending_participant"],
                         self.target.participant_id)
        self.assertEqual(self.anchor_path.read_bytes(), before_anchor)
        self.assertEqual(assess_recovery(self.store, self.lab._journal).state,
                         "PENDING_COMMITTED")
        self._assert_withdrawn()
        self._assert_restart_denied()

    def test_fault_after_journal_commit_before_anchor_update(self):
        self.lab._journal.begin_withdrawal(self.target.participant_id)
        self._withdraw_authority()
        old_anchor = self.anchor_path.read_bytes()
        # The journal transaction is committed before _update_anchor() starts.
        with mock.patch.object(self.lab._journal, "_update_anchor",
                               side_effect=RuntimeError("simulated post-commit crash")):
            with self.assertRaisesRegex(RuntimeError, "post-commit"):
                self.lab._journal.finish_withdrawal(self.target.participant_id)
        self.assertEqual(self.lab._journal._head()["sequence"], 1)
        self.assertIsNone(self.lab._journal._head()["pending_participant"])
        self.assertEqual(self.anchor_path.read_bytes(), old_anchor)
        self._assert_withdrawn()
        with self.assertRaises(JournalCorruption):
            self.lab._journal.verify()
        assessment = assess_recovery(self.store, self.lab._journal)
        self.assertEqual(assessment.state, "UNTRUSTED")
        self.assertFalse(assessment.delivery_permitted)
        with self.assertRaises(Unavailable):
            self.lab.flush("node-a", self.sender.access_token)
        self._close_lab()
        with self.assertRaises(JournalCorruption):
            RevocationJournal.open_for_review(
                self.journal_path, anchor_path=self.anchor_path, anchor_key=KEY)
        with self.assertRaises((JournalCorruption, Unavailable)):
            DistributedConsentLab(
                self.store, ["node-a"], journal_path=self.journal_path,
                anchor_path=self.anchor_path, anchor_key=KEY)

    def test_after_anchor_update_consistency_does_not_restore_consent(self):
        self.lab._journal.begin_withdrawal(self.target.participant_id)
        self._withdraw_authority()
        self.lab._journal.finish_withdrawal(self.target.participant_id)
        self.assertEqual(self.lab._journal.verify(), 1)
        self.assertEqual(assess_recovery(self.store, self.lab._journal).state,
                         "CLEAN")
        self._assert_withdrawn()
        with self.assertRaises(ConsentError):
            self.lab.queue("node-a", self.sender.access_token,
                           self.target.participant_id, "deny", "post-anchor")
        self.assertEqual(self.store.db.execute(
            "SELECT COUNT(*) FROM messages").fetchone()[0], 0)

    def test_crash_without_pending_intent_detects_divergence(self):
        # Invalid write ordering: the authority is changed without a journal intent.
        self._withdraw_authority()
        assessment = assess_recovery(self.store, self.lab._journal)
        self.assertEqual(assessment.state, "DIVERGED")
        self.assertFalse(assessment.delivery_permitted)
        with self.assertRaises(Unavailable):
            self.lab.queue("node-a", self.sender.access_token,
                           self.target.participant_id, "deny", "no-intent")
        self._assert_restart_denied()

    def test_normal_commit_restart_does_not_resurrect_withdrawn_target(self):
        self.lab.withdraw(self.target.participant_id,
                          self.target.withdrawal_token)
        self._close_lab()
        self.lab = DistributedConsentLab(
            self.store, ["node-a"], journal_path=self.journal_path,
            anchor_path=self.anchor_path, anchor_key=KEY)
        self.assertEqual(self.lab._journal.verify(), 1)
        self._assert_withdrawn()
        with self.assertRaises(ConsentError):
            self.lab.queue("node-a", self.sender.access_token,
                           self.target.participant_id, "deny", "after-restart")

    def test_operator_review_is_read_only_at_crash_boundary(self):
        self.lab._journal.begin_withdrawal(self.target.participant_id)
        self._withdraw_authority()
        changes = (self.store.db.total_changes,
                   self.lab._journal.db.total_changes,
                   self.anchor_path.read_bytes())
        observation = assess_recovery(self.store, self.lab._journal)
        plan = draft_recovery(self.store, self.lab._journal)
        self.assertEqual(observation.state, "PENDING_COMMITTED")
        self.assertFalse(plan.delivery_permitted)
        self.assertEqual(changes, (self.store.db.total_changes,
                                   self.lab._journal.db.total_changes,
                                   self.anchor_path.read_bytes()))
        self.assertEqual(self.lab._journal._head()["pending_participant"],
                         self.target.participant_id)


if __name__ == "__main__":
    unittest.main()
