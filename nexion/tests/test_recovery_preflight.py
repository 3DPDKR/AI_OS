"""Offline fault-injection tests of the non-executable preflight barrier."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import json
import tempfile
import unittest

from nexion.consent import ConsentStore
from nexion.distributed_consent import DistributedConsentLab
from nexion.recovery_protocol import RecoveryDenied, RecoveryReviewSession, draft_recovery
from nexion.recovery_preflight import preflight_recovery

T0 = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
KEY = bytes(range(32))  # offline dummy data only


class RecoveryPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.anchor = root / "anchor.json"
        self.store = ConsentStore(root / "authority.db")
        self.enrollment = self.store.apply(
            alias="offline", contact="offline@example.invalid",
            scopes={"peer_chat"}, explicitly_agreed=True)
        self.store.confirm(self.enrollment.participant_id,
                           self.enrollment.confirmation_token)
        self.lab = DistributedConsentLab(
            self.store, ["node-a"], journal_path=root / "journal.db",
            anchor_path=self.anchor, anchor_key=KEY)
        self.journal = self.lab._journal

    def tearDown(self):
        self.lab.close()
        self.store.close()
        self.temp.cleanup()

    def approved(self, *, committed=True):
        self.journal.begin_withdrawal(self.enrollment.participant_id)
        if committed:
            self.store.withdraw(self.enrollment.participant_id,
                                self.enrollment.withdrawal_token)
        plan = draft_recovery(self.store, self.journal, at=T0)
        session = RecoveryReviewSession(plan, requested_by="requester")
        session.review(self.store, self.journal, reviewed_by="reviewer",
                       evidence_reference="offline-proof", at=T0)
        session.approve(self.store, self.journal, approved_by="reviewer", at=T0)
        return session

    def test_pending_committed_preflight_is_nonexecutable_and_read_only(self):
        session = self.approved()
        before = (self.store.db.total_changes, self.journal.db.total_changes,
                  self.anchor.read_bytes())
        result = preflight_recovery(session, self.store, self.journal, at=T0)
        self.assertEqual(result.status, "PRECHECK_ONLY")
        self.assertEqual(result.action, session.plan.action)
        self.assertFalse(result.execute_automatically)
        self.assertFalse(result.may_reactivate_participant)
        self.assertFalse(result.delivery_permitted)
        self.assertEqual(before, (self.store.db.total_changes,
                                  self.journal.db.total_changes,
                                  self.anchor.read_bytes()))
        row = self.store.db.execute("SELECT state FROM participants WHERE id=?",
                                    (self.enrollment.participant_id,)).fetchone()
        self.assertEqual(row["state"], "withdrawn")

    def test_pending_uncommitted_preflight_does_not_clear_intent(self):
        session = self.approved(committed=False)
        result = preflight_recovery(session, self.store, self.journal, at=T0)
        self.assertIn("clear_intent_only", result.action)
        self.assertEqual(self.journal._head()["pending_participant"],
                         self.enrollment.participant_id)

    def test_unapproved_and_restarted_sessions_fail_closed(self):
        session = self.approved()
        fresh = RecoveryReviewSession(session.plan, requested_by="requester")
        with self.assertRaises(RecoveryDenied):
            preflight_recovery(fresh, self.store, self.journal, at=T0)
        with self.assertRaises(RecoveryDenied):
            preflight_recovery(None, self.store, self.journal, at=T0)

    def test_late_expiration_refused(self):
        session = self.approved()
        with self.assertRaises(RecoveryDenied):
            preflight_recovery(session, self.store, self.journal,
                               at=T0 + timedelta(minutes=15))

    def test_audit_only_change_invalidates_existing_approval(self):
        session = self.approved()
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO audit (participant_id,event,time) VALUES (?,?,?)",
                (self.enrollment.participant_id, "unexpected", T0.isoformat()))
        with self.assertRaises(RecoveryDenied):
            preflight_recovery(session, self.store, self.journal, at=T0)

    def test_anchor_tampering_refused(self):
        session = self.approved()
        anchor = json.loads(self.anchor.read_text())
        anchor["mac"] = "0" * 64
        self.anchor.write_text(json.dumps(anchor))
        with self.assertRaises(RecoveryDenied):
            preflight_recovery(session, self.store, self.journal, at=T0)

    def test_mutation_between_approval_rechecks_refused(self):
        session = self.approved()
        original = session._check_current
        calls = 0
        def mutating_check(store, journal, at):
            nonlocal calls
            calls += 1
            if calls == 2:
                with self.store.db:
                    self.store.db.execute("UPDATE participants SET alias='changed' WHERE id=?",
                                          (self.enrollment.participant_id,))
            return original(store, journal, at)
        with mock.patch.object(session, "_check_current", side_effect=mutating_check):
            with self.assertRaises(RecoveryDenied):
                preflight_recovery(session, self.store, self.journal, at=T0)

    def test_mutation_after_second_work_order_refused(self):
        session = self.approved()
        original = session.work_order
        count = 0
        def late_change(*args, **kwargs):
            nonlocal count
            count += 1
            out = original(*args, **kwargs)
            if count == 2:
                with self.store.db:
                    self.store.db.execute(
                        "UPDATE participants SET alias='late' WHERE id=?",
                        (self.enrollment.participant_id,))
            return out
        with mock.patch.object(session, "work_order", side_effect=late_change):
            with self.assertRaises(RecoveryDenied):
                preflight_recovery(session, self.store, self.journal, at=T0)

    def test_second_approval_check_failure_leaves_reviewed(self):
        self.journal.begin_withdrawal(self.enrollment.participant_id)
        plan = draft_recovery(self.store, self.journal, at=T0)
        session = RecoveryReviewSession(plan, requested_by="requester")
        session.review(self.store, self.journal, reviewed_by="reviewer",
                       evidence_reference="proof", at=T0)
        original = session._check_current
        count = 0
        def failing_check(store, journal, at):
            nonlocal count
            count += 1
            if count == 2:
                raise RecoveryDenied("simulated last-moment state change")
            return original(store, journal, at)
        with mock.patch.object(session, "_check_current", side_effect=failing_check):
            with self.assertRaises(RecoveryDenied):
                session.approve(self.store, self.journal,
                                approved_by="reviewer", at=T0)
        self.assertEqual(session.state, "REVIEWED")
        self.assertIsNone(session.approved_by)
        with self.assertRaises(RecoveryDenied):
            session.work_order(self.store, self.journal, at=T0)

    def test_declared_permit_is_not_executable_even_if_modified_copy(self):
        session = self.approved()
        status = preflight_recovery(session, self.store, self.journal, at=T0)
        self.assertTrue(replace(status, execute_automatically=True).execute_automatically)
        # A frozen dataclass is not a cryptographic authorization and cannot
        # trigger writes; the model exposes no execute() method at all.
        self.assertFalse(hasattr(status, "execute"))
        self.assertEqual(self.journal._head()["pending_participant"],
                         self.enrollment.participant_id)


if __name__ == "__main__":
    unittest.main()
