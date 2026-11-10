"""NEXION voluntary participation core (offline reference implementation).

No outbound network, unsolicited contact, facility access or remote actuation.
Tokens shown to the creator in this local prototype are *not* email identity proof.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCOPES = frozenset({"peer_chat", "research", "simulation", "facility_review"})
CONSENT_VERSION = "NEXION-CONSENT-v1"

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _make_token() -> str:
    return secrets.token_urlsafe(32)

@dataclass(frozen=True)
class Enrollment:
    participant_id: str
    confirmation_token: str
    access_token: str
    withdrawal_token: str
    expires_at: str

class ConsentError(ValueError):
    """Invalid registration, missing active consent, or authentication failure."""

class ConsentStore:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(db_path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY,
                alias TEXT NOT NULL,
                contact TEXT NOT NULL,
                scopes TEXT NOT NULL,
                consent_version TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','active','withdrawn')),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                confirmed_at TEXT,
                confirm_digest TEXT NOT NULL,
                access_digest TEXT NOT NULL UNIQUE,
                withdrawal_digest TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                sender_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(sender_id) REFERENCES participants(id),
                FOREIGN KEY(recipient_id) REFERENCES participants(id)
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id TEXT NOT NULL,
                event TEXT NOT NULL,
                time TEXT NOT NULL
            );
        """)
        self.db.commit()

    def _audit(self, participant_id: str, event: str):
        self.db.execute(
            "INSERT INTO audit (participant_id,event,time) VALUES (?,?,?)",
            (participant_id, event, _utcnow().isoformat()),
        )

    def apply(self, *, alias: str, contact: str, scopes: set[str],
              explicitly_agreed: bool) -> Enrollment:
        if not explicitly_agreed:
            raise ConsentError("Affirmative consent is required")
        alias, contact = alias.strip(), contact.strip()
        if not (1 <= len(alias) <= 80) or not (3 <= len(contact) <= 254) or "@" not in contact:
            raise ConsentError("Valid alias and contact email are required")
        if not scopes or not scopes.issubset(SCOPES):
            raise ConsentError("Select at least one permitted participation scope")
        pid,confirm,access,revoke = str(uuid.uuid4()),_make_token(),_make_token(),_make_token()
        expires = _utcnow() + timedelta(hours=48)
        with self.db:
            self.db.execute("""INSERT INTO participants
                (id,alias,contact,scopes,consent_version,state,created_at,expires_at,
                confirm_digest,access_digest,withdrawal_digest)
                VALUES (?,?,?,?,?,'pending',?,?,?,?,?)""",
                (pid,alias,contact,json.dumps(sorted(scopes)),CONSENT_VERSION,
                 _utcnow().isoformat(),expires.isoformat(),_digest(confirm),
                 _digest(access),_digest(revoke)))
            self._audit(pid,"application_created")
        return Enrollment(pid,confirm,access,revoke,expires.isoformat())

    def confirm(self, participant_id: str, confirmation_token: str) -> bool:
        rec=self.db.execute("SELECT * FROM participants WHERE id=?",(participant_id,)).fetchone()
        if rec is None or rec["state"]!="pending":
            raise ConsentError("Application is not pending")
        if _utcnow() >= datetime.fromisoformat(rec["expires_at"]):
            raise ConsentError("Confirmation token has expired")
        if not hmac.compare_digest(rec["confirm_digest"],_digest(confirmation_token)):
            raise ConsentError("Invalid confirmation token")
        with self.db:
            self.db.execute("UPDATE participants SET state='active',confirmed_at=?,confirm_digest='' WHERE id=?",
                            (_utcnow().isoformat(),participant_id))
            self._audit(participant_id,"consent_confirmed")
        return True

    def _actor(self, access_token: str, scope: str | None = None) -> sqlite3.Row:
        rec=self.db.execute("SELECT * FROM participants WHERE access_digest=?",
                            (_digest(access_token),)).fetchone()
        if rec is None or rec["state"]!="active":
            raise ConsentError("Active consent and valid access token are required")
        if scope is not None and scope not in json.loads(rec["scopes"]):
            raise ConsentError("Participation scope not granted")
        return rec

    def withdraw(self, participant_id: str, withdrawal_token: str) -> bool:
        rec=self.db.execute("SELECT * FROM participants WHERE id=?",(participant_id,)).fetchone()
        if rec is None or rec["state"]=="withdrawn":
            raise ConsentError("No active or pending participation found")
        if not hmac.compare_digest(rec["withdrawal_digest"],_digest(withdrawal_token)):
            raise ConsentError("Invalid withdrawal token")
        with self.db:
            self.db.execute("DELETE FROM messages WHERE sender_id=? OR recipient_id=?",
                            (participant_id,participant_id))
            self.db.execute("""UPDATE participants SET state='withdrawn', contact='[withdrawn]',
                alias='[withdrawn]', scopes='[]', confirm_digest='',access_digest='',
                withdrawal_digest='' WHERE id=?""",(participant_id,))
            self._audit(participant_id,"consent_withdrawn")
        return True

    def send_peer_message(self, access_token: str, recipient_id: str, body: str) -> str:
        sender=self._actor(access_token,"peer_chat")
        recipient=self.db.execute("SELECT * FROM participants WHERE id=?",(recipient_id,)).fetchone()
        if recipient is None or recipient["state"]!="active" or "peer_chat" not in json.loads(recipient["scopes"]):
            raise ConsentError("Recipient has not opted in to peer chat")
        body=body.strip()
        if not (1 <= len(body) <= 1000):
            raise ConsentError("Messages must be 1..1000 characters")
        msg_id=str(uuid.uuid4())
        with self.db:
            self.db.execute("INSERT INTO messages VALUES (?,?,?,?,?)",
                            (msg_id,sender["id"],recipient_id,body,_utcnow().isoformat()))
            self._audit(sender["id"],"peer_message_created")
        return msg_id

    def inbox(self, access_token: str) -> list[dict]:
        actor=self._actor(access_token,"peer_chat")
        rows=self.db.execute("""SELECT id,sender_id,body,created_at FROM messages
            WHERE recipient_id=? ORDER BY created_at,id""",(actor["id"],)).fetchall()
        return [dict(row) for row in rows]

    def audit_events(self, participant_id: str) -> list[str]:
        return [row[0] for row in self.db.execute(
            "SELECT event FROM audit WHERE participant_id=? ORDER BY id",(participant_id,))]

    def close(self):
        self.db.close()
