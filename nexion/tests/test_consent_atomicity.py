"""Deterministic offline SQLite cross-connection race/fault regressions.

No remote endpoints. Separate SQLite connections simulate distinct local workers;
Events control the interleaving instead of relying on random thread timing.
"""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from nexion.consent import ConsentError, ConsentStore


class ConsentAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tempdir.name) / "consent.sqlite3")
        self.main = ConsentStore(self.path)
        self.alice = self.enroll("alice")
        self.bob = self.enroll("bob")

    def tearDown(self):
        self.main.close()
        self.tempdir.cleanup()

    def enroll(self, alias):
        enrollment = self.main.apply(
            alias=alias, contact=f"{alias}@example.invalid",
            scopes={"peer_chat"}, explicitly_agreed=True,
        )
        self.main.confirm(enrollment.participant_id, enrollment.confirmation_token)
        return enrollment

    @staticmethod
    def _join_threads(threads):
        for thread in threads:
            thread.join(timeout=6)
            if thread.is_alive():
                raise AssertionError("worker did not finish (possible deadlock)")

    def test_withdraw_cannot_overtake_inflight_send_authorization(self):
        """Withdrawal must wait when a send has already begun its atomic check.

        The sender pauses just *after* _actor has checked its credential. An
        unprotected implementation allows withdrawal to commit during this
        pause, risking permission-check/write reordering. The fixed version
        holds the SQLite write reservation until the message is committed.
        """
        authorized = threading.Event()
        resume_send = threading.Event()
        withdraw_started = threading.Event()
        withdraw_finished = threading.Event()
        errors = []
        sender_result = []
        withdraw_result = []

        def sender():
            store = ConsentStore(self.path)
            try:
                original_actor = store._actor

                def gated_actor(*args, **kwargs):
                    result = original_actor(*args, **kwargs)
                    authorized.set()
                    if not resume_send.wait(timeout=5):
                        raise AssertionError("sender gate timeout")
                    return result

                store._actor = gated_actor
                sender_result.append(store.send_peer_message(
                    self.alice.access_token, self.bob.participant_id, "private local message"
                ))
            except BaseException as exc:
                errors.append(exc)
            finally:
                store.close()

        def withdrawer():
            store = ConsentStore(self.path)
            try:
                withdraw_started.set()
                withdraw_result.append(store.withdraw(
                    self.bob.participant_id, self.bob.withdrawal_token
                ))
            except BaseException as exc:
                errors.append(exc)
            finally:
                withdraw_finished.set()
                store.close()

        s = threading.Thread(target=sender, name="simulated-sender")
        w = threading.Thread(target=withdrawer, name="simulated-withdrawer")
        s.start()
        try:
            self.assertTrue(authorized.wait(timeout=4), "sender never reached gate")
            w.start()
            self.assertTrue(withdraw_started.wait(timeout=4))
            self.assertFalse(
                withdraw_finished.wait(timeout=0.20),
                "withdrawal overtook an in-flight authorization check",
            )
        finally:
            resume_send.set()
            self._join_threads([s] + ([w] if w.ident is not None else []))
        self.assertEqual(errors, [])
        self.assertEqual(len(sender_result), 1)
        self.assertEqual(withdraw_result, [True])
        self.assertEqual(self.main.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        self.assertEqual(self.main.db.execute(
            "SELECT state FROM participants WHERE id=?", (self.bob.participant_id,)
        ).fetchone()[0], "withdrawn")

    def test_send_started_after_withdrawal_is_rejected(self):
        store = ConsentStore(self.path)
        try:
            self.main.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
            with self.assertRaises(ConsentError):
                store.send_peer_message(self.alice.access_token, self.bob.participant_id, "hi")
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
            self.assertFalse(store.db.in_transaction)
        finally:
            store.close()

    def test_failed_send_releases_transaction(self):
        self.main.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        with self.assertRaises(ConsentError):
            self.main.send_peer_message(self.alice.access_token, self.bob.participant_id, "hi")
        self.assertFalse(self.main.db.in_transaction)
        carol = self.enroll("carol")
        self.assertTrue(self.main.send_peer_message(
            self.alice.access_token, carol.participant_id, "still usable"
        ))

    def test_failed_withdrawal_releases_transaction(self):
        with self.assertRaises(ConsentError):
            self.main.withdraw(self.bob.participant_id, "wrong-token")
        self.assertFalse(self.main.db.in_transaction)
        self.assertTrue(self.main.withdraw(self.bob.participant_id, self.bob.withdrawal_token))

    def test_competing_withdrawals_only_one_commits(self):
        start = threading.Barrier(3)
        success = []
        failures = []

        def withdrawer():
            store = ConsentStore(self.path)
            try:
                start.wait(timeout=4)
                success.append(store.withdraw(self.bob.participant_id, self.bob.withdrawal_token))
            except ConsentError as exc:
                failures.append(type(exc))
            finally:
                store.close()

        threads = [threading.Thread(target=withdrawer) for _ in range(2)]
        for t in threads:
            t.start()
        try:
            start.wait(timeout=4)
        finally:
            self._join_threads(threads)
        self.assertEqual(success, [True])
        self.assertEqual(failures, [ConsentError])
        self.assertEqual(self.main.audit_events(self.bob.participant_id).count(
            "consent_withdrawn"
        ), 1)

    def test_sender_withdrawal_removes_existing_messages_from_both_directions(self):
        self.main.send_peer_message(self.alice.access_token, self.bob.participant_id, "a to b")
        self.main.send_peer_message(self.bob.access_token, self.alice.participant_id, "b to a")
        self.main.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(self.main.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
