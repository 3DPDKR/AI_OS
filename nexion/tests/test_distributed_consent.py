"""Fault-injection regressions for simulated multi-node consent replication."""
import unittest

from nexion.consent import ConsentError, ConsentStore
from nexion.distributed_consent import DistributedConsentLab, Unavailable


class DistributedConsentTests(unittest.TestCase):
    def setUp(self):
        self.store = ConsentStore()
        self.alice = self.enroll("alice")
        self.bob = self.enroll("bob")
        self.carol = self.enroll("carol")
        self.lab = DistributedConsentLab(self.store, ["node-a", "node-b"])

    def tearDown(self):
        self.store.close()

    def enroll(self, name):
        e = self.store.apply(alias=name, contact=f"{name}@example.invalid",
                             scopes={"peer_chat"}, explicitly_agreed=True)
        self.store.confirm(e.participant_id, e.confirmation_token)
        return e

    def queue_both(self):
        self.lab.queue("node-a", self.alice.access_token, self.bob.participant_id,
                       "alpha secret", "a1")
        self.lab.queue("node-b", self.carol.access_token, self.bob.participant_id,
                       "beta secret", "b1")

    def test_partition_stale_replica_never_delivers_after_withdrawal(self):
        self.queue_both()
        self.lab.partition("node-b")
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(self.lab.flush("node-a", self.alice.access_token)["delivered"], 0)
        self.assertEqual(self.lab.replica_state("node-b")["cursor"], 0)
        with self.assertRaises(Unavailable):
            self.lab.flush("node-b", self.carol.access_token)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        self.lab.partition("node-b", disconnected=False)
        self.assertEqual(self.lab.sync("node-b")["cancelled"], 1)
        item = self.lab.nodes["node-b"].relay._items[(self.carol.participant_id, "b1")]
        self.assertEqual((item.state, item.body), ("cancelled", ""))
        self.assertEqual(self.lab.flush("node-b", self.carol.access_token)["delivered"], 0)

    def test_authority_outage_fails_closed_even_with_healthy_node(self):
        self.queue_both()
        self.lab.sync("node-a")
        self.lab.set_authority_available(False)
        with self.assertRaises(Unavailable):
            self.lab.flush("node-a", self.alice.access_token)
        self.assertEqual(self.store.inbox(self.bob.access_token), [])
        self.lab.set_authority_available(True)
        self.assertEqual(self.lab.flush("node-a", self.alice.access_token)["delivered"], 1)

    def test_both_links_work_and_retry_is_idempotent(self):
        self.queue_both()
        self.assertEqual(self.lab.flush("node-a", self.alice.access_token)["delivered"], 1)
        self.assertEqual(self.lab.flush("node-b", self.carol.access_token)["delivered"], 1)
        self.assertEqual(self.lab.flush("node-a", self.alice.access_token)["delivered"], 0)
        self.assertEqual(len(self.store.inbox(self.bob.access_token)), 2)

    def test_event_monotonic_sequence_and_incremental_replication(self):
        event1 = self.lab.withdraw(self.alice.participant_id, self.alice.withdrawal_token)
        self.assertEqual(event1.sequence, 1)
        self.assertEqual(self.lab.sync("node-a")["new_events"], 1)
        self.assertEqual(self.lab.sync("node-a")["new_events"], 0)
        event2 = self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(event2.sequence, 2)
        self.assertEqual(self.lab.sync("node-a")["new_events"], 1)
        self.assertEqual(self.lab.sync("node-b")["new_events"], 2)
        self.assertEqual(self.lab.replica_state("node-a")["cursor"], 2)

    def test_multiple_withdrawals_preserve_unique_revoked_credentials(self):
        self.lab.withdraw(self.alice.participant_id, self.alice.withdrawal_token)
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        rows = self.store.db.execute(
            "SELECT access_digest, withdrawal_digest FROM participants WHERE state='withdrawn'"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["access_digest"] for r in rows}), 2)
        self.assertEqual(len({r["withdrawal_digest"] for r in rows}), 2)
        self.assertTrue(all(r["access_digest"] and r["withdrawal_digest"] for r in rows))
        with self.assertRaises(ConsentError):
            self.store.inbox(self.alice.access_token)
        with self.assertRaises(ConsentError):
            self.store.inbox(self.bob.access_token)

    def test_sender_withdrawal_cancels_queued_data(self):
        self.queue_both()
        self.lab.withdraw(self.alice.participant_id, self.alice.withdrawal_token)
        self.assertEqual(self.lab.sync("node-a")["cancelled"], 1)
        with self.assertRaises(ConsentError):
            self.lab.flush("node-a", self.alice.access_token)
        self.assertEqual(self.lab.flush("node-b", self.carol.access_token)["delivered"], 1)

    def test_withdrawal_event_does_not_include_contact_body_or_tokens(self):
        self.queue_both()
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        journal = repr(self.lab.event_log())
        for secret in ("bob@example.invalid", "alpha secret", "beta secret",
                       self.bob.withdrawal_token, self.bob.access_token):
            self.assertNotIn(secret, journal)

    def test_direct_store_withdrawal_still_blocks_flush(self):
        self.queue_both()
        self.store.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(len(self.lab.event_log()), 0)
        self.assertEqual(self.lab.flush("node-a", self.alice.access_token)["delivered"], 0)

    def test_repeated_withdrawal_never_replays_event(self):
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        with self.assertRaises(ConsentError):
            self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(len(self.lab.event_log()), 1)

    def test_unavailable_authority_cannot_accept_revocation(self):
        self.lab.set_authority_available(False)
        with self.assertRaises(Unavailable):
            self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        self.assertEqual(self.lab.event_log(), ())

    def test_partitioned_node_cannot_queue_new_message(self):
        self.lab.partition("node-a")
        with self.assertRaises(Unavailable):
            self.lab.queue("node-a", self.alice.access_token, self.bob.participant_id,
                           "hello", "a1")

    def test_authority_outage_prevents_new_queue(self):
        self.lab.set_authority_available(False)
        with self.assertRaises(Unavailable):
            self.lab.queue("node-a", self.alice.access_token, self.bob.participant_id,
                           "hello", "a1")

    def test_partitioned_node_cannot_sync(self):
        self.lab.partition("node-a")
        with self.assertRaises(Unavailable):
            self.lab.sync("node-a")

    def test_offline_replica_cannot_scrub_until_reconnect(self):
        self.queue_both()
        self.lab.partition("node-b")
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        item = self.lab.nodes["node-b"].relay._items[(self.carol.participant_id, "b1")]
        self.assertEqual(item.body, "beta secret")  # privacy limitation: physically offline node
        self.lab.partition("node-b", False)
        self.lab.sync("node-b")
        self.assertEqual(item.body, "")

    def test_node_registration_rejects_bad_names(self):
        for names in ([], ["dup", "dup"], ["wrong node"], ["../root"]):
            with self.assertRaises(ValueError):
                DistributedConsentLab(self.store, names)

    def test_unknown_node_rejected(self):
        with self.assertRaises(ValueError):
            self.lab.partition("missing")

    def test_revoked_recipient_cannot_be_queued_again(self):
        self.lab.withdraw(self.bob.participant_id, self.bob.withdrawal_token)
        with self.assertRaises(ConsentError):
            self.lab.queue("node-a", self.alice.access_token, self.bob.participant_id,
                           "new", "a1")

    def test_no_transport_or_equipment_control_methods(self):
        for name in ("send_over_network", "mass_message", "manufacture", "actuate"):
            self.assertFalse(hasattr(self.lab, name))


if __name__ == "__main__":
    unittest.main()
