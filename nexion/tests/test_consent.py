import unittest
from datetime import datetime, timedelta, timezone
from nexion.consent import ConsentStore, ConsentError

class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.store=ConsentStore()
    def tearDown(self):
        self.store.close()
    def enroll(self, alias, scopes={"peer_chat"}):
        return self.store.apply(alias=alias,contact=f"{alias}@example.invalid",
                                scopes=set(scopes),explicitly_agreed=True)
    def activate(self, alias, scopes={"peer_chat"}):
        x=self.enroll(alias,scopes)
        self.store.confirm(x.participant_id,x.confirmation_token)
        return x
    def test_requires_affirmative_consent(self):
        with self.assertRaises(ConsentError):
            self.store.apply(alias="A",contact="a@example.invalid",scopes={"research"},explicitly_agreed=False)
    def test_requires_known_scope(self):
        with self.assertRaises(ConsentError):
            self.enroll("A",{"unknown"})
    def test_requires_nonempty_scopes(self):
        with self.assertRaises(ConsentError):
            self.enroll("A",set())
    def test_invalid_contact(self):
        with self.assertRaises(ConsentError):
            self.store.apply(alias="A",contact="not an email",scopes={"research"},explicitly_agreed=True)
    def test_pending_cannot_message(self):
        a=self.enroll("A"); b=self.activate("B")
        with self.assertRaises(ConsentError):
            self.store.send_peer_message(a.access_token,b.participant_id,"hi")
    def test_confirmation_requires_secret(self):
        a=self.enroll("A")
        with self.assertRaises(ConsentError):
            self.store.confirm(a.participant_id,"wrong")
        self.assertTrue(self.store.confirm(a.participant_id,a.confirmation_token))
    def test_expired_confirmation(self):
        a=self.enroll("A")
        old=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        self.store.db.execute("UPDATE participants SET expires_at=? WHERE id=?",(old,a.participant_id))
        self.store.db.commit()
        with self.assertRaises(ConsentError):
            self.store.confirm(a.participant_id,a.confirmation_token)
    def test_peer_chat_two_way_opt_in(self):
        a=self.activate("A"); b=self.activate("B")
        self.store.send_peer_message(a.access_token,b.participant_id,"Hello")
        self.store.send_peer_message(b.access_token,a.participant_id,"Reply")
        self.assertEqual(self.store.inbox(b.access_token)[0]["body"],"Hello")
        self.assertEqual(self.store.inbox(a.access_token)[0]["body"],"Reply")
    def test_scope_not_granted(self):
        a=self.activate("A",{"research"}); b=self.activate("B")
        with self.assertRaises(ConsentError):
            self.store.send_peer_message(a.access_token,b.participant_id,"hello")
    def test_recipient_must_opt_in(self):
        a=self.activate("A"); b=self.activate("B",{"research"})
        with self.assertRaises(ConsentError):
            self.store.send_peer_message(a.access_token,b.participant_id,"hello")
    def test_revoke_blocks_messages_and_deletes_private_data(self):
        a=self.activate("A"); b=self.activate("B")
        self.store.send_peer_message(a.access_token,b.participant_id,"private")
        self.store.withdraw(b.participant_id,b.withdrawal_token)
        with self.assertRaises(ConsentError):
            self.store.inbox(b.access_token)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],0)
    def test_revoke_requires_secret(self):
        a=self.activate("A")
        with self.assertRaises(ConsentError):
            self.store.withdraw(a.participant_id,"guess")
    def test_tokens_are_not_in_db_as_plaintext(self):
        a=self.enroll("A")
        row=self.store.db.execute("SELECT * FROM participants WHERE id=?",(a.participant_id,)).fetchone()
        self.assertNotIn(a.access_token,tuple(row));self.assertNotIn(a.withdrawal_token,tuple(row))
        self.assertNotIn(a.confirmation_token,tuple(row))
    def test_no_external_network_methods(self):
        self.assertFalse(any(hasattr(self.store,x) for x in ("broadcast","mass_email","factory_command")))
    def test_message_length_limit(self):
        a=self.activate("A");b=self.activate("B")
        with self.assertRaises(ConsentError):
            self.store.send_peer_message(a.access_token,b.participant_id,"x"*1001)
    def test_audit_has_no_private_content(self):
        a=self.activate("A");b=self.activate("B")
        self.store.send_peer_message(a.access_token,b.participant_id,"sensitive example text")
        self.assertNotIn("sensitive",str(self.store.audit_events(a.participant_id)))

if __name__=="__main__":
    unittest.main()
