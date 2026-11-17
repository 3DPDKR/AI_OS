"""No-I/O approval planning regression tests (fixtures are offline only)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from nexion.consent import ConsentStore
from nexion.distributed_consent import DistributedConsentLab
from nexion.recovery_protocol import (
    RecoveryDenied, RecoveryReviewSession, draft_recovery,
)

KEY = bytes(range(32))  # fake test key; not a real identity credential
T0 = datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc)


class RecoveryProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.authority = root / 'authority.sqlite3'
        self.anchor = root / 'anchor.json'
        self.journal = root / 'journal.sqlite3'
        self.store = ConsentStore(self.authority)
        self.bob = self.store.apply(alias='bob', contact='bob@example.invalid',
                                    scopes={'peer_chat'}, explicitly_agreed=True)
        self.store.confirm(self.bob.participant_id, self.bob.confirmation_token)
        self.lab = DistributedConsentLab(self.store, ['a'], journal_path=self.journal,
                                         anchor_path=self.anchor, anchor_key=KEY)

    def tearDown(self):
        self.lab.close()
        self.store.close()
        self.temp.cleanup()

    @property
    def log(self):
        return self.lab._journal

    def pending(self, *, committed=False):
        self.log.begin_withdrawal(self.bob.participant_id)
        if committed:
            self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        return draft_recovery(self.store, self.log, at=T0)

    def test_clean_refused(self):
        with self.assertRaises(RecoveryDenied):
            draft_recovery(self.store, self.log, at=T0)

    def test_committed_draft_only_proposes_append(self):
        plan = self.pending(committed=True)
        self.assertEqual(plan.source_state, 'PENDING_COMMITTED')
        self.assertIn('append_missing_revocation', plan.action)
        self.assertFalse(plan.delivery_permitted)

    def test_uncommitted_draft_only_proposes_clear_intent(self):
        plan = self.pending(committed=False)
        self.assertEqual(plan.source_state, 'PENDING_UNCOMMITTED')
        self.assertIn('clear_intent_only', plan.action)

    def test_approval_requires_distinct_reviewer_and_evidence(self):
        plan = self.pending(committed=True)
        session = RecoveryReviewSession(plan, requested_by='requester')
        with self.assertRaises(RecoveryDenied):
            session.review(self.store, self.log, reviewed_by='requester',
                           evidence_reference='ticket-1', at=T0)
        with self.assertRaises(RecoveryDenied):
            session.review(self.store, self.log, reviewed_by='reviewer',
                           evidence_reference='', at=T0)
        with self.assertRaises(RecoveryDenied):
            session.approve(self.store, self.log, approved_by='reviewer', at=T0)
        self.assertEqual(session.state, 'NEW')

    def test_approval_produces_non_executable_work_order(self):
        plan = self.pending(committed=True)
        session = RecoveryReviewSession(plan, requested_by='requester')
        session.review(self.store, self.log, reviewed_by='reviewer',
                       evidence_reference='offline-proof-1', at=T0)
        with self.assertRaises(RecoveryDenied):
            session.approve(self.store, self.log, approved_by='requester', at=T0)
        order = session.approve(self.store, self.log, approved_by='operator', at=T0)
        self.assertEqual(session.state, 'APPROVED')
        self.assertFalse(order.execute_automatically)
        self.assertFalse(order.may_reactivate_participant)
        self.assertFalse(order.delivery_permitted)
        self.assertEqual(order.evidence_reference, 'offline-proof-1')
        self.assertEqual(order.plan_id, plan.plan_id)
        self.assertEqual(self.store.db.execute(
            'SELECT state FROM participants WHERE id=?',
            (self.bob.participant_id,)).fetchone()[0], 'withdrawn')
        self.assertEqual(self.log._head()['pending_participant'], self.bob.participant_id)

    def test_rejected_plan_cannot_be_approved(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        session.reject()
        with self.assertRaises(RecoveryDenied):
            session.review(self.store, self.log, reviewed_by='rev',
                           evidence_reference='proof', at=T0)
        with self.assertRaises(RecoveryDenied):
            session.approve(self.store, self.log, approved_by='rev', at=T0)

    def test_double_approval_and_rejection_after_approval_denied(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        session.review(self.store, self.log, reviewed_by='rev',
                       evidence_reference='proof', at=T0)
        session.approve(self.store, self.log, approved_by='rev', at=T0)
        with self.assertRaises(RecoveryDenied):
            session.approve(self.store, self.log, approved_by='rev', at=T0)
        with self.assertRaises(RecoveryDenied):
            session.reject()

    def test_expired_or_backdated_approval_is_denied(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        session.review(self.store, self.log, reviewed_by='rev',
                       evidence_reference='proof', at=T0)
        for instant in (T0 - timedelta(seconds=1), T0 + timedelta(minutes=15)):
            with self.subTest(instant=instant), self.assertRaises(RecoveryDenied):
                session.approve(self.store, self.log, approved_by='rev', at=instant)

    def test_stale_on_authority_state_change(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        with self.assertRaises(RecoveryDenied):
            session.review(self.store, self.log, reviewed_by='rev',
                           evidence_reference='proof', at=T0)

    def test_stale_on_authority_profile_change(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        with self.store.db:
            self.store.db.execute('UPDATE participants SET alias=? WHERE id=?',
                                  ('changed', self.bob.participant_id))
        with self.assertRaises(RecoveryDenied):
            session.review(self.store, self.log, reviewed_by='rev',
                           evidence_reference='proof', at=T0)

    def test_stale_on_checkpoint_change(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        self.log.abort_withdrawal(self.bob.participant_id)
        self.log.checkpoint('a', 0)
        with self.assertRaises(RecoveryDenied):
            session.review(self.store, self.log, reviewed_by='rev',
                           evidence_reference='proof', at=T0)

    def test_work_order_rechecks_staleness(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        session.review(self.store, self.log, reviewed_by='rev',
                       evidence_reference='proof', at=T0)
        session.approve(self.store, self.log, approved_by='rev', at=T0)
        self.log.abort_withdrawal(self.bob.participant_id)
        with self.assertRaises(RecoveryDenied):
            session.work_order(self.store, self.log, at=T0)

    def test_invalid_ttl_and_naive_time_denied(self):
        for ttl in (timedelta(0), timedelta(minutes=-1), timedelta(days=1)):
            with self.subTest(ttl=ttl), self.assertRaises(RecoveryDenied):
                draft_recovery(self.store, self.log, at=T0, ttl=ttl)
        with self.assertRaises(RecoveryDenied):
            draft_recovery(self.store, self.log, at=datetime(2026, 11, 17))

    def test_untrusted_journal_denied(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        # Tamper with anchor: must block even the planning workflow.
        import json
        data = json.loads(self.anchor.read_text())
        data['mac'] = '0'*64
        self.anchor.write_text(json.dumps(data))
        with self.assertRaises(RecoveryDenied):
            session.review(self.store, self.log, reviewed_by='rev',
                           evidence_reference='proof', at=T0)
        with self.assertRaises(RecoveryDenied):
            draft_recovery(self.store, self.log, at=T0)

    def test_unrelated_divergence_denies_draft(self):
        self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        with self.assertRaises(RecoveryDenied):
            draft_recovery(self.store, self.log, at=T0)

    def test_forged_plan_action_rejected(self):
        plan = self.pending()
        for forged in (replace(plan, action='reactivate_participant'),
                       replace(plan, delivery_permitted=True),
                       replace(plan, plan_id='f'*64),
                       replace(plan, expires_at=plan.created_at + timedelta(days=1))):
            with self.subTest(forged=forged), self.assertRaises(RecoveryDenied):
                session = RecoveryReviewSession(forged, requested_by='req')
                session.review(self.store, self.log, reviewed_by='rev',
                               evidence_reference='proof', at=T0)

    def test_stale_on_authority_new_message(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        self.store.send_peer_message(self.bob.access_token,
                                     self.bob.participant_id, 'offline-test')
        with self.assertRaises(RecoveryDenied):
            session.review(self.store, self.log, reviewed_by='rev',
                           evidence_reference='proof', at=T0)

    def test_unapproved_work_order_denied(self):
        plan = self.pending()
        session = RecoveryReviewSession(plan, requested_by='req')
        with self.assertRaises(RecoveryDenied):
            session.work_order(self.store, self.log, at=T0)
        session.review(self.store, self.log, reviewed_by='rev',
                       evidence_reference='proof', at=T0)
        with self.assertRaises(RecoveryDenied):
            session.work_order(self.store, self.log, at=T0)

    def test_read_only_approval_no_db_or_anchor_writes(self):
        self.log.begin_withdrawal(self.bob.participant_id)
        before = (self.anchor.read_bytes(), self.store.db.total_changes,
                  self.log.db.total_changes, tuple(self.log._head()))
        plan = draft_recovery(self.store, self.log, at=T0)
        session = RecoveryReviewSession(plan, requested_by='req')
        session.review(self.store, self.log, reviewed_by='rev',
                       evidence_reference='proof', at=T0)
        session.approve(self.store, self.log, approved_by='rev', at=T0)
        self.assertEqual(before, (self.anchor.read_bytes(), self.store.db.total_changes,
                                  self.log.db.total_changes, tuple(self.log._head())))

    def test_approval_not_restored_across_process_memory(self):
        plan = self.pending()
        first = RecoveryReviewSession(plan, requested_by='req')
        first.review(self.store, self.log, reviewed_by='rev',
                     evidence_reference='proof', at=T0)
        first.approve(self.store, self.log, approved_by='rev', at=T0)
        second = RecoveryReviewSession(plan, requested_by='req')
        with self.assertRaises(RecoveryDenied):
            second.work_order(self.store, self.log, at=T0)


if __name__ == '__main__':
    unittest.main()
