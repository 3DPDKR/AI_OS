"""Offline restart/gap/tamper fault injection for NEXION v0.2.4.

Two local SQLite files only; no sockets, hardware access or outside contacts.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from nexion.consent import ConsentError, ConsentStore
from nexion.distributed_consent import DistributedConsentLab, Unavailable
from nexion.revocation_journal import GENESIS, JournalCorruption, RevocationJournal


class RevocationJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = str(Path(self.temp.name) / "consents.sqlite3")
        self.log_path = str(Path(self.temp.name) / "revocations.sqlite3")
        self.store = ConsentStore(self.store_path)
        self.alice = self.add("alice")
        self.bob = self.add("bob")
        self.carol = self.add("carol")
        self.lab = DistributedConsentLab(
            self.store, ["node-a", "node-b"], journal_path=self.log_path)

    def tearDown(self):
        if self.lab is not None:
            self.lab.close()
        self.store.close()
        self.temp.cleanup()

    def add(self, alias):
        result = self.store.apply(alias=alias, contact=f"{alias}@example.invalid",
                                  scopes={"peer_chat"}, explicitly_agreed=True)
        self.store.confirm(result.participant_id, result.confirmation_token)
        return result

    def withdraw(self, person):
        return self.lab.withdraw(person.participant_id, person.withdrawal_token)

    def mutate(self, sql, args=()):
        with sqlite3.connect(self.log_path) as db:
            db.execute(sql, args)

    def test_initial_log_has_verified_genesis(self):
        self.assertEqual(self.lab._journal.verify(), 0)
        self.assertEqual(self.lab._journal._head()["digest"], GENESIS)

    def test_two_events_survive_process_restart_with_replica_cursors(self):
        self.lab.sync("node-a")
        self.withdraw(self.bob)
        self.lab.sync("node-a")
        self.withdraw(self.carol)
        self.lab.sync("node-a")
        self.assertEqual(self.lab.replica_state("node-a")["cursor"], 2)
        self.assertEqual(self.lab.replica_state("node-b")["cursor"], 0)
        self.lab.close()
        self.lab = None
        self.store.close()
        self.store = ConsentStore(self.store_path)
        self.lab = DistributedConsentLab(
            self.store, ["node-a", "node-b"], journal_path=self.log_path)
        state = self.lab.replica_state("node-a")
        self.assertEqual(state["cursor"], 2)
        self.assertEqual(set(state["observed_withdrawals"]),
                         {self.bob.participant_id, self.carol.participant_id})
        self.assertEqual(self.lab.sync("node-a")["new_events"], 0)
        self.assertEqual(self.lab.sync("node-b")["new_events"], 2)

    def test_node_restart_forgets_volatile_queue_not_replaying_private_payload(self):
        self.lab.queue("node-a", self.alice.access_token, self.bob.participant_id,
                       "do not persist me", "id1")
        self.lab.restart_node("node-a")
        self.assertEqual(len(self.lab.nodes["node-a"].relay._items), 0)
        self.assertEqual(self.lab.flush("node-a", self.alice.access_token)["delivered"], 0)
        self.assertEqual(self.store.inbox(self.bob.access_token), [])

    def test_restart_preserves_disconnect_and_checkpoint(self):
        self.withdraw(self.bob)
        self.lab.sync("node-a")
        self.lab.partition("node-a")
        self.lab.restart_node("node-a")
        self.assertEqual(self.lab.replica_state("node-a")["cursor"], 1)
        with self.assertRaises(Unavailable):
            self.lab.flush("node-a", self.alice.access_token)

    def test_tail_truncation_fails_closed(self):
        self.withdraw(self.bob)
        self.mutate("DELETE FROM journal_events WHERE sequence=1")
        with self.assertRaises(Unavailable):
            self.lab.queue("node-a", self.alice.access_token, self.carol.participant_id,
                           "blocked", "x")
        with self.assertRaises(Unavailable):
            self.lab.flush("node-a", self.alice.access_token)

    def test_gap_in_event_log_detected(self):
        self.withdraw(self.bob)
        self.withdraw(self.carol)
        self.mutate("DELETE FROM journal_events WHERE sequence=1")
        with self.assertRaises(Unavailable):
            self.lab.sync("node-a")

    def test_event_participant_mutation_detected(self):
        self.withdraw(self.bob)
        self.mutate("UPDATE journal_events SET participant_id=? WHERE sequence=1",
                    (self.alice.participant_id,))
        with self.assertRaises(Unavailable):
            self.lab.sync("node-a")

    def test_event_digest_mutation_detected(self):
        self.withdraw(self.bob)
        self.mutate("UPDATE journal_events SET digest='0' WHERE sequence=1")
        with self.assertRaises(Unavailable):
            self.lab.sync("node-a")

    def test_head_regression_detected(self):
        self.withdraw(self.bob)
        self.mutate("UPDATE journal_head SET sequence=0,digest=?", (GENESIS,))
        with self.assertRaises(Unavailable):
            self.lab.sync("node-a")

    def test_future_cursor_detected_after_restart(self):
        self.withdraw(self.bob)
        self.lab.sync("node-a")
        self.lab.close()
        self.lab = None
        self.mutate("UPDATE replica_checkpoints SET sequence=777 WHERE node_name='node-a'")
        with self.assertRaises(JournalCorruption):
            DistributedConsentLab(self.store, ["node-a"], journal_path=self.log_path)

    def test_cursor_digest_corruption_detected(self):
        self.withdraw(self.bob)
        self.lab.sync("node-a")
        self.mutate("UPDATE replica_checkpoints SET digest=? WHERE node_name='node-a'",
                    (GENESIS,))
        with self.assertRaises(Unavailable):
            self.lab.flush("node-a", self.alice.access_token)

    def test_interrupted_withdrawal_intent_blocks_restart(self):
        self.lab._journal.begin_withdrawal(self.bob.participant_id)
        with self.assertRaises(Unavailable):
            self.lab.queue("node-a", self.alice.access_token, self.bob.participant_id,
                           "must not enqueue", "id")
        self.lab.close()
        self.lab = None
        with self.assertRaises(JournalCorruption):
            DistributedConsentLab(self.store, ["node-a"], journal_path=self.log_path)

    def test_failed_withdrawal_clears_intent_and_preserves_access(self):
        with self.assertRaises(ConsentError):
            self.lab.withdraw(self.bob.participant_id, "wrong-token")
        self.assertEqual(self.lab._journal.verify(), 0)
        self.lab.queue("node-a", self.alice.access_token, self.bob.participant_id,
                       "still authorized", "id1")
        self.assertEqual(self.lab.flush("node-a", self.alice.access_token)["delivered"], 1)

    def test_withdrawal_blocks_queued_send_after_node_restart(self):
        self.lab.queue("node-a", self.alice.access_token, self.bob.participant_id,
                       "private", "id1")
        self.withdraw(self.bob)
        self.lab.restart_node("node-a")
        self.assertEqual(self.lab.sync("node-a")["new_events"], 1)
        self.assertEqual(self.lab.flush("node-a", self.alice.access_token)["delivered"], 0)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)

    def test_no_journal_can_be_recreated_from_empty_existing_database(self):
        self.lab.close()
        self.lab = None
        with sqlite3.connect(self.log_path) as db:
            db.execute("DROP TABLE journal_head")
        with self.assertRaises(JournalCorruption):
            RevocationJournal(self.log_path)

    def test_missing_checkpoint_table_on_restart_fails_closed(self):
        self.withdraw(self.bob)
        self.lab.sync("node-a")
        self.lab.close()
        self.lab = None
        with sqlite3.connect(self.log_path) as db:
            db.execute("DROP TABLE replica_checkpoints")
        with self.assertRaises(JournalCorruption):
            DistributedConsentLab(self.store, ["node-a"], journal_path=self.log_path)

    def test_no_network_or_actuation_methods(self):
        for name in ("send", "broadcast", "connect", "actuate", "purchase"):
            self.assertFalse(hasattr(self.lab._journal, name))


if __name__ == "__main__":
    unittest.main()
