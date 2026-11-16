"""Read-only offline recovery triage and live fail-closed regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from nexion.consent import ConsentStore, ConsentError
from nexion.distributed_consent import DistributedConsentLab, Unavailable
from nexion.recovery_review import assess_recovery
from nexion.revocation_journal import RevocationJournal, JournalCorruption

KEY = bytes(range(32))  # fixed fixture ONLY, not a deployed secret


class RecoveryReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.consent_path = self.root / 'authority.sqlite3'
        self.journal_path = self.root / 'revocations.sqlite3'
        self.anchor_path = self.root / 'anchor.json'
        self.store = ConsentStore(self.consent_path)
        self.alice = self.person('alice')
        self.bob = self.person('bob')
        self.lab = self.start()

    def tearDown(self):
        if self.lab:
            self.lab.close()
        if self.store:
            self.store.close()
        self.tmp.cleanup()

    def person(self, alias):
        e = self.store.apply(alias=alias, contact=f'{alias}@example.invalid',
                             scopes={'peer_chat'}, explicitly_agreed=True)
        self.store.confirm(e.participant_id, e.confirmation_token)
        return e

    def start(self):
        return DistributedConsentLab(self.store, ['a', 'b'],
                                     journal_path=self.journal_path,
                                     anchor_path=self.anchor_path, anchor_key=KEY)

    def review(self):
        return assess_recovery(self.store, self.lab._journal)

    def open_review(self):
        return RevocationJournal.open_for_review(self.journal_path,
                                                anchor_path=self.anchor_path,
                                                anchor_key=KEY)

    def test_clean_genesis_and_clean_after_two_withdrawals(self):
        a = self.review()
        self.assertEqual((a.state, a.delivery_permitted, a.event_count), ('CLEAN', True, 0))
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        other = self.person('carol')
        self.lab.withdraw(other.participant_id, other.withdrawal_token)
        a = self.review()
        self.assertEqual((a.state, a.delivery_permitted, a.event_count, a.discrepancy_count),
                         ('CLEAN', True, 2, 0))

    def test_pending_intent_before_authority_commit(self):
        self.lab._journal.begin_withdrawal(self.bob.participant_id)
        a = self.review()
        self.assertEqual(a.state, 'PENDING_UNCOMMITTED')
        self.assertFalse(a.delivery_permitted)
        self.assertIn('operator', a.operator_action)

    def test_pending_intent_after_authority_commit(self):
        self.lab._journal.begin_withdrawal(self.bob.participant_id)
        self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        a = self.review()
        self.assertEqual(a.state, 'PENDING_COMMITTED')
        self.assertFalse(a.delivery_permitted)
        self.assertEqual(a.discrepancy_count, 1)

    def test_review_survives_restart_without_releasing_lockdown(self):
        self.lab._journal.begin_withdrawal(self.bob.participant_id)
        self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.lab.close(); self.lab = None
        with self.assertRaises(JournalCorruption):
            self.start()
        ro = self.open_review()
        try:
            a = assess_recovery(self.store, ro)
            self.assertEqual(a.state, 'PENDING_COMMITTED')
            self.assertFalse(a.delivery_permitted)
        finally:
            ro.close()

    def test_review_handle_refuses_each_write_method(self):
        ro = self.open_review()
        try:
            for method, args in (
                ('begin_withdrawal', (self.bob.participant_id,)),
                ('abort_withdrawal', (self.bob.participant_id,)),
                ('finish_withdrawal', (self.bob.participant_id,)),
                ('checkpoint', ('a', 0)),
            ):
                with self.subTest(method=method), self.assertRaises(JournalCorruption):
                    getattr(ro, method)(*args)
            self.assertTrue(assess_recovery(self.store, ro).delivery_permitted)
        finally:
            ro.close()

    def test_read_only_inspection_does_not_change_data(self):
        before = self.anchor_path.read_bytes()
        rows = list(self.store.db.execute('SELECT * FROM participants ORDER BY id'))
        head = tuple(self.lab._journal._head())
        for _ in range(3):
            ro = self.open_review()
            try:
                self.assertEqual(assess_recovery(self.store, ro).state, 'CLEAN')
            finally:
                ro.close()
        self.assertEqual(self.anchor_path.read_bytes(), before)
        self.assertEqual(list(self.store.db.execute('SELECT * FROM participants ORDER BY id')), rows)
        self.assertEqual(tuple(self.lab._journal._head()), head)

    def test_review_missing_file_never_creates_it(self):
        missing = self.root / 'missing.sqlite3'
        with self.assertRaises(JournalCorruption):
            RevocationJournal.open_for_review(missing)
        self.assertFalse(missing.exists())

    def test_review_wrong_hmac_key_denied(self):
        with self.assertRaises(JournalCorruption):
            RevocationJournal.open_for_review(self.journal_path,
                                             anchor_path=self.anchor_path,
                                             anchor_key=b'x' * 32)

    def test_review_partial_anchor_configuration_is_denied(self):
        with self.assertRaises(ValueError):
            RevocationJournal.open_for_review(self.journal_path,
                                             anchor_path=self.anchor_path)

    def test_out_of_band_withdrawal_detected_and_blocks_queue(self):
        self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        a = self.review()
        self.assertEqual((a.state, a.delivery_permitted), ('DIVERGED', False))
        with self.assertRaises(Unavailable):
            self.lab.queue('a', self.alice.access_token, self.alice.participant_id,
                           'blocked due to discrepancy', '1')
        with self.assertRaises(Unavailable):
            self.lab.flush('a', self.alice.access_token)

    def test_authority_rollback_detected_and_restart_refused(self):
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.store.db.execute("UPDATE participants SET state='active' WHERE id=?",
                              (self.bob.participant_id,))
        self.store.db.commit()
        self.assertEqual(self.review().state, 'DIVERGED')
        self.lab.close(); self.lab = None
        with self.assertRaises(Unavailable):
            self.start()

    def test_duplicate_logged_event_detected(self):
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.lab._journal.begin_withdrawal(self.bob.participant_id)
        self.lab._journal.finish_withdrawal(self.bob.participant_id)
        a = self.review()
        self.assertEqual(a.state, 'DIVERGED')
        self.assertEqual(a.discrepancy_count, 1)

    def test_event_without_participant_detected(self):
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.store.db.execute('DELETE FROM participants WHERE id=?',(self.bob.participant_id,))
        self.store.db.commit()
        self.assertEqual(self.review().state, 'DIVERGED')

    def test_unrelated_missing_revocation_during_pending_is_diverged(self):
        self.store.withdraw(self.alice.participant_id, self.alice.withdrawal_token)
        self.lab._journal.begin_withdrawal(self.bob.participant_id)
        self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(self.review().state, 'DIVERGED')

    def test_bad_anchor_is_untrusted_and_denied(self):
        data=json.loads(self.anchor_path.read_text())
        data['mac']='f'*64
        self.anchor_path.write_text(json.dumps(data))
        self.assertEqual(self.review().state, 'UNTRUSTED')
        with self.assertRaises(Unavailable):
            self.lab.sync('a')

    def test_bad_authority_schema_is_untrusted(self):
        self.store.db.execute('DROP TABLE participants')
        self.store.db.commit()
        self.assertEqual(self.review().state, 'UNTRUSTED')

    def test_post_crash_anchor_mismatch_stays_untrusted(self):
        def fail_anchor_write():
            raise OSError('injected crash')
        self.lab._journal._update_anchor = fail_anchor_write
        with self.assertRaises(OSError):
            self.lab._journal.begin_withdrawal(self.bob.participant_id)
        self.assertEqual(self.review().state, 'UNTRUSTED')

    def test_known_bad_token_rolls_back_and_remains_clean(self):
        with self.assertRaises(ConsentError):
            self.lab.withdraw(self.bob.participant_id, 'bad token')
        self.assertEqual(self.review().state, 'CLEAN')

    def test_no_repair_method_or_external_io(self):
        for name in ('repair', 'force_reactivate', 'broadcast', 'connect', 'actuate'):
            self.assertFalse(hasattr(self.lab._journal, name))
        self.assertFalse(hasattr(self.lab, 'repair'))


if __name__ == '__main__':
    unittest.main()
