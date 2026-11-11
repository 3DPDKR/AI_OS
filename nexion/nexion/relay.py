"""Opt-in, offline-only store-and-forward simulator for NEXION peer messages.

This model performs NO network I/O, email delivery, remote execution or device control.
It is not a deployable communications server: messages wait in process memory as
plaintext until they are flushed, cancelled or expired. Identity verification and
production authentication are explicitly out of scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from typing import Callable, Dict, Optional, Tuple

from .consent import ConsentError, ConsentStore

_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_MAX_TTL_SECONDS = 24 * 60 * 60


@dataclass
class Envelope:
    sender_id: str
    recipient_id: str
    client_id: str
    body: str
    fingerprint: str
    expires_at: datetime
    state: str = "queued"
    stored_message_id: Optional[str] = None


class OfflineRelay:
    """A bounded local queue. Only the original sender can flush its messages.

    Duplicate (sender, client_id) submissions are idempotent. The class never
    retains access or withdrawal tokens. Delivery rechecks both parties' current
    peer_chat consent, even if it was present when the message was queued.
    """

    def __init__(self, store: ConsentStore, *,
                 clock: Optional[Callable[[], datetime]] = None,
                 max_tracked: int = 500, max_pending_per_sender: int = 100):
        if max_tracked < 1 or max_pending_per_sender < 1:
            raise ValueError("queue limits must be positive")
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_tracked = max_tracked
        self.max_pending_per_sender = max_pending_per_sender
        self._secret = secrets.token_bytes(32)
        self._items: Dict[Tuple[str, str], Envelope] = {}
        self.audit: list[dict] = []

    def _now(self) -> datetime:
        current = self.clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("clock must provide a timezone-aware datetime")
        return current

    def _has_consent(self, participant_id: str) -> bool:
        record = self.store.db.execute(
            "SELECT state, scopes FROM participants WHERE id=?", (participant_id,)
        ).fetchone()
        return bool(record is not None and record["state"] == "active"
                    and "peer_chat" in json.loads(record["scopes"]))

    def _finalize(self, item: Envelope, state: str, message_id: Optional[str] = None):
        item.state = state
        item.body = ""  # Discard private message payload on any terminal transition.
        item.stored_message_id = message_id
        self.audit.append({"event": state, "sender_id": item.sender_id,
                           "recipient_id": item.recipient_id, "client_id": item.client_id})

    def reconcile(self) -> dict:
        """Apply revocation/expiry to pending messages, without network I/O."""
        now = self._now()
        cancelled = expired = 0
        for item in self._items.values():
            if item.state != "queued":
                continue
            # Prioritize revocation over expiry to erase messages immediately.
            if not (self._has_consent(item.sender_id) and self._has_consent(item.recipient_id)):
                self._finalize(item, "cancelled")
                cancelled += 1
            elif now >= item.expires_at:
                self._finalize(item, "expired")
                expired += 1
        return {"cancelled": cancelled, "expired": expired}

    def queue(self, access_token: str, recipient_id: str, body: str,
              client_id: str, *, ttl_seconds: int = 3600) -> dict:
        """Queue a message from a currently consenting sender to a consenting peer."""
        self.reconcile()
        sender = self.store._actor(access_token, "peer_chat")
        if not self._has_consent(recipient_id):
            raise ConsentError("Recipient has not opted into peer chat")
        if not isinstance(client_id, str) or _ID_PATTERN.fullmatch(client_id) is None:
            raise ConsentError("client_id must contain 1..64 safe ASCII characters")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= _MAX_TTL_SECONDS:
            raise ConsentError("ttl_seconds must be 1..86400")
        if not isinstance(body, str) or not 1 <= len(body.strip()) <= 1000:
            raise ConsentError("Message must be 1..1000 characters")
        body = body.strip()
        key = (sender["id"], client_id)
        fingerprint = hmac.new(self._secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
        if key in self._items:
            existing = self._items[key]
            if existing.recipient_id != recipient_id:
                raise ConsentError("client_id conflicts with existing recipient")
            if not hmac.compare_digest(existing.fingerprint, fingerprint):
                raise ConsentError("client_id conflicts with existing message")
            # Finished IDs remain reserved: clients cannot replay old IDs.
            return {"client_id": client_id, "state": existing.state,
                    "stored_message_id": existing.stored_message_id}
        if len(self._items) >= self.max_tracked:
            raise ConsentError("Relay tracking capacity reached")
        pending = sum(item.state == "queued" and item.sender_id == sender["id"]
                      for item in self._items.values())
        if pending >= self.max_pending_per_sender:
            raise ConsentError("Sender queue capacity reached")
        self._items[key] = Envelope(sender["id"], recipient_id, client_id, body,
                                    fingerprint, self._now() + timedelta(seconds=ttl_seconds))
        self.audit.append({"event": "queued", "sender_id": sender["id"],
                           "recipient_id": recipient_id, "client_id": client_id})
        return {"client_id": client_id, "state": "queued", "stored_message_id": None}

    def flush(self, access_token: str, *, link_available: bool = True) -> dict:
        """Retry the sender's queued messages into the LOCAL consent-store inbox."""
        self.reconcile()
        sender = self.store._actor(access_token, "peer_chat")
        delivered = 0
        if link_available:
            for item in self._items.values():
                if item.sender_id != sender["id"] or item.state != "queued":
                    continue
                # send_peer_message checks sender and recipient consents again.
                try:
                    mid = self.store.send_peer_message(
                        access_token, item.recipient_id, item.body)
                except ConsentError:
                    self._finalize(item, "cancelled")
                else:
                    self._finalize(item, "delivered", mid)
                    delivered += 1
        pending = sum(item.sender_id == sender["id"] and item.state == "queued"
                      for item in self._items.values())
        return {"delivered": delivered, "pending": pending,
                "link_available": bool(link_available)}

    def withdraw(self, participant_id: str, withdrawal_token: str) -> bool:
        """Withdraw through the consent store and promptly scrub this relay."""
        result = self.store.withdraw(participant_id, withdrawal_token)
        self.reconcile()
        return result

    def status(self, access_token: str, client_id: str) -> dict:
        """Read metadata only; never reveal another person's queue or body."""
        self.reconcile()
        sender = self.store._actor(access_token, "peer_chat")
        item = self._items.get((sender["id"], client_id))
        if item is None:
            raise ConsentError("No message with this client_id")
        return {"client_id": item.client_id, "state": item.state,
                "stored_message_id": item.stored_message_id}
