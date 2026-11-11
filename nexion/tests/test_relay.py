"""Regressions for offline-only message delivery and opt-in boundaries."""
import unittest
from datetime import datetime, timedelta, timezone

from nexion.consent import ConsentError, ConsentStore
from nexion.relay import OfflineRelay


class ManualClock:
    def __init__(self):
        self.time = datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.time

    def advance(self, seconds):
        self.time += timedelta(seconds=seconds)


class OfflineRelayTests(unittest.TestCase):
    def setUp(self):
        self.store = ConsentStore()
        self.clock = ManualClock()
        self.relay = OfflineRelay(self.store, clock=self.clock)
        self.alice = self.enroll("alice")
        self.bob = self.enroll("bob")

    def tearDown(self):
        self.store.close()

    def enroll(self, alias, scopes=None):
        if scopes is None:
            scopes = {"peer_chat"}
        obj = self.store.apply(alias=alias, contact=f"{alias}@example.invalid",
                               scopes=scopes, explicitly_agreed=True)
        self.store.confirm(obj.participant_id, obj.confirmation_token)
        return obj

    def queue_one(self, client_id="msg_1", **kw):
        return self.relay.queue(self.alice.access_token, self.bob.participant_id,
                                "hello", client_id, **kw)

    def test_partition_and_recovery(self):
        self.queue_one()
        self.assertEqual(self.relay.flush(self.alice.access_token, link_available=False)["pending"], 1)
        self.assertEqual(self.store.inbox(self.bob.access_token), [])
        self.assertEqual(self.relay.flush(self.alice.access_token)["delivered"], 1)
        self.assertEqual(self.store.inbox(self.bob.access_token)[0]["body"], "hello")

    def test_no_duplicate_delivery_after_retry(self):
        first = self.queue_one()
        duplicate = self.queue_one()
        self.assertEqual(first, duplicate)
        self.relay.flush(self.alice.access_token)
        self.assertEqual(self.relay.flush(self.alice.access_token)["delivered"], 0)
        self.assertEqual(len(self.store.inbox(self.bob.access_token)), 1)

    def test_reused_client_id_different_recipient_rejected(self):
        self.queue_one()
        other = self.enroll("other")
        with self.assertRaises(ConsentError):
            self.relay.queue(self.alice.access_token, other.participant_id, "hello", "msg_1")

    def test_reused_client_id_different_body_rejected(self):
        self.queue_one()
        with self.assertRaises(ConsentError):
            self.relay.queue(self.alice.access_token, self.bob.participant_id, "tampered", "msg_1")

    def test_expiration_drops_private_body(self):
        self.queue_one(ttl_seconds=1)
        self.clock.advance(2)
        self.assertEqual(self.relay.reconcile()["expired"], 1)
        self.assertEqual(self.relay.flush(self.alice.access_token)["delivered"], 0)
        self.assertEqual(self.relay.status(self.alice.access_token, "msg_1")["state"], "expired")
        self.assertEqual(self.relay._items[(self.alice.participant_id, "msg_1")].body, "")

    def test_sender_revocation_scrubs_queue(self):
        self.queue_one()
        self.assertTrue(self.relay.withdraw(self.alice.participant_id, self.alice.withdrawal_token))
        self.assertEqual(self.relay._items[(self.alice.participant_id, "msg_1")].state, "cancelled")
        with self.assertRaises(ConsentError):
            self.relay.flush(self.alice.access_token)
        self.assertEqual(self.store.inbox(self.bob.access_token), [])

    def test_recipient_revocation_scrubs_queue_and_inbox(self):
        self.queue_one()
        self.relay.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(self.relay.flush(self.alice.access_token)["delivered"], 0)
        self.assertEqual(self.relay.status(self.alice.access_token, "msg_1")["state"], "cancelled")

    def test_direct_withdrawal_rechecked_before_delivery(self):
        self.queue_one()
        self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(self.relay.flush(self.alice.access_token)["delivered"], 0)
        self.assertEqual(self.relay._items[(self.alice.participant_id, "msg_1")].body, "")

    def test_requires_both_opted_in(self):
        research_only = self.enroll("researcher", {"research"})
        with self.assertRaises(ConsentError):
            self.relay.queue(self.alice.access_token, research_only.participant_id, "hello", "x")
        with self.assertRaises(ConsentError):
            self.relay.queue(research_only.access_token, self.bob.participant_id, "hello", "x")

    def test_pending_participant_denied(self):
        pending = self.store.apply(alias="new", contact="new@example.invalid",
                                   scopes={"peer_chat"}, explicitly_agreed=True)
        with self.assertRaises(ConsentError):
            self.relay.queue(self.alice.access_token, pending.participant_id, "hi", "x")

    def test_pending_limit(self):
        relay = OfflineRelay(self.store, max_pending_per_sender=1)
        relay.queue(self.alice.access_token, self.bob.participant_id, "hello", "one")
        with self.assertRaises(ConsentError):
            relay.queue(self.alice.access_token, self.bob.participant_id, "other", "two")

    def test_global_limit(self):
        relay = OfflineRelay(self.store, max_tracked=1)
        relay.queue(self.alice.access_token, self.bob.participant_id, "hello", "one")
        with self.assertRaises(ConsentError):
            relay.queue(self.alice.access_token, self.bob.participant_id, "another", "two")

    def test_invalid_client_id_or_ttl(self):
        for bad in ("../esc", "space id", "x" * 65):
            with self.assertRaises(ConsentError):
                self.relay.queue(self.alice.access_token, self.bob.participant_id, "hi", bad)
        for bad in (0, -1, 86401, True):
            with self.assertRaises(ConsentError):
                self.queue_one(ttl_seconds=bad)

    def test_status_requires_sender_token(self):
        self.queue_one()
        with self.assertRaises(ConsentError):
            self.relay.status(self.bob.access_token, "msg_1")

    def test_no_access_tokens_stored_or_audited(self):
        self.queue_one()
        self.assertNotIn(self.alice.access_token, repr(self.relay._items))
        self.assertNotIn(self.alice.access_token, repr(self.relay.audit))
        self.assertNotIn("hello", repr(self.relay.audit))

    def test_finished_client_id_cannot_be_replayed(self):
        self.queue_one()
        self.relay.flush(self.alice.access_token)
        self.assertEqual(self.queue_one()["state"], "delivered")
        self.assertEqual(len(self.store.inbox(self.bob.access_token)), 1)

    def test_conflicting_duplicate_after_delivery_rejected(self):
        self.queue_one()
        self.relay.flush(self.alice.access_token)
        with self.assertRaises(ConsentError):
            self.relay.queue(self.alice.access_token, self.bob.participant_id,
                             "changed", "msg_1")

    def test_both_parties_can_exchange_messages(self):
        self.queue_one()
        self.relay.queue(self.bob.access_token, self.alice.participant_id, "reply", "r1")
        self.relay.flush(self.alice.access_token)
        self.relay.flush(self.bob.access_token)
        self.assertEqual(self.store.inbox(self.alice.access_token)[0]["body"], "reply")


if __name__ == "__main__":
    unittest.main()
