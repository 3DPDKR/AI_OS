"""Deterministic, offline-only consent-revocation replication experiment.

The central ConsentStore is a *simulation oracle*, not a distributed database.
Each node has a local OfflineRelay and delayed revocation-event cursor.
Deliveries require a fresh, available authority check (fail closed), so stale
replicas cannot deliver during partitions. No network or hardware I/O occurs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional
from pathlib import Path
from datetime import datetime
import re

from .consent import ConsentError, ConsentStore
from .relay import OfflineRelay
from .revocation_journal import RevocationJournal, JournalCorruption

_NODE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class Unavailable(ConsentError):
    """Simulated node link or authority is unavailable; delivery is denied."""


@dataclass(frozen=True)
class RevocationEvent:
    sequence: int
    participant_id: str
    kind: str = "withdrawn"


@dataclass
class Replica:
    name: str
    relay: OfflineRelay
    connected: bool = True
    cursor: int = 0
    observed_withdrawals: set[str] = field(default_factory=set)


class DistributedConsentLab:
    """Simulate delayed revocation propagation with authoritative send gates.

    The shared store is deliberately in-memory/SQLite and not a network server.
    By default the log is in-memory. Optional journal_path enables a local
    durable SQLite event chain and node checkpoints (not a distributed log).
    No offline node is allowed to deliver using cached consent alone.
    """

    def __init__(self, store: ConsentStore, node_names: list[str], *,
                 clock: Optional[Callable[[], datetime]] = None,
                 journal_path: Optional[str | Path] = None):
        if not node_names or len(node_names) != len(set(node_names)):
            raise ValueError("Node names must be unique and nonempty")
        if any(not isinstance(name, str) or _NODE_PATTERN.fullmatch(name) is None
               for name in node_names):
            raise ValueError("Invalid node name")
        self.store = store
        self.nodes: Dict[str, Replica] = {
            name: Replica(name, OfflineRelay(store, clock=clock))
            for name in node_names
        }
        self.authority_available = True
        self._events: list[RevocationEvent] = []
        self._clock = clock
        self._journal = RevocationJournal(journal_path) if journal_path is not None else None
        self._journal_fault = False
        if self._journal is not None:
            for node in self.nodes.values():
                node.cursor, node.observed_withdrawals = self._journal.restore(node.name)

    def _verify_journal(self) -> None:
        if self._journal_fault:
            raise Unavailable("Prior journal error; reject operations until operator review")
        if self._journal is not None:
            try:
                self._journal.verify()
            except JournalCorruption as exc:
                self._journal_fault = True
                raise Unavailable("Revocation journal integrity unknown; operation denied") from exc

    def restart_node(self, node_name: str) -> None:
        """Simulate process restart: in-memory queued messages are discarded.

        On journal mode, the durable checkpoint is checked and loaded. This
        does NOT recover previous queued plaintext nor grant delivery access.
        """
        node = self._node(node_name)
        self._verify_journal()
        cursor, observed = (0, set()) if self._journal is None else self._journal.restore(node_name)
        self.nodes[node_name] = Replica(
            node_name, OfflineRelay(self.store, clock=self._clock),
            connected=node.connected, cursor=cursor, observed_withdrawals=observed,
        )

    def close(self) -> None:
        """Close only the optional journal; the caller owns ConsentStore."""
        if self._journal is not None:
            self._journal.close()

    def _node(self, node_name: str) -> Replica:
        try:
            return self.nodes[node_name]
        except KeyError as exc:
            raise ValueError("Unknown node") from exc

    def partition(self, node_name: str, disconnected: bool = True) -> None:
        self._node(node_name).connected = not disconnected

    def set_authority_available(self, available: bool) -> None:
        self.authority_available = bool(available)

    def queue(self, node_name: str, access_token: str, recipient_id: str,
              body: str, client_id: str, *, ttl_seconds: int = 3600) -> dict:
        """Stage a message using the shared mock store only if link and authority are up.

        This is NOT a model of independently verified remote identities.
        """
        node = self._node(node_name)
        if not node.connected or not self.authority_available:
            raise Unavailable("Fresh consent validation unavailable for queueing")
        self._verify_journal()
        return node.relay.queue(
            access_token, recipient_id, body, client_id, ttl_seconds=ttl_seconds)

    def withdraw(self, participant_id: str, withdrawal_token: str) -> RevocationEvent:
        """First commit revocation to the authoritative store; then log event."""
        if not self.authority_available:
            raise Unavailable("Consent authority unavailable")
        self._verify_journal()
        if self._journal is None:
            self.store.withdraw(participant_id, withdrawal_token)
            event = RevocationEvent(len(self._events) + 1, participant_id)
            self._events.append(event)
            return event
        # If interrupted after the authority commits, the durable pending
        # intent remains and future queue/flush calls fail closed.
        self._journal.begin_withdrawal(participant_id)
        try:
            self.store.withdraw(participant_id, withdrawal_token)
        except Exception:
            # The store's withdrawal is transactional and has rolled back.
            try:
                self._journal.abort_withdrawal(participant_id)
            except Exception:
                self._journal_fault = True
            raise
        try:
            item = self._journal.finish_withdrawal(participant_id)
        except Exception:
            self._journal_fault = True
            raise
        return RevocationEvent(item.sequence, item.participant_id)

    def sync(self, node_name: str) -> dict:
        """Reconcile the node on reconnection, with sequence-based replay."""
        node = self._node(node_name)
        if not node.connected:
            raise Unavailable("Node link unavailable")
        if not self.authority_available:
            raise Unavailable("Consent authority unavailable")
        self._verify_journal()
        if self._journal is None:
            new = self._events[node.cursor:]
            target_cursor = len(self._events)
        else:
            new = self._journal.events(after=node.cursor)
            target_cursor = self._journal.verify()
        # Checkpoint before marking the event sequence as applied. Even if
        # simulated process restarts, reconciliation rechecks live authority.
        changes = node.relay.reconcile()
        if self._journal is not None:
            self._journal.checkpoint(node_name, target_cursor)
        for event in new:
            node.observed_withdrawals.add(event.participant_id)
        node.cursor = target_cursor
        return {"cursor": node.cursor, "new_events": len(new), **changes}

    def flush(self, node_name: str, access_token: str) -> dict:
        """Fail closed if either link or authority cannot be checked right now."""
        node = self._node(node_name)
        self.sync(node_name)
        # No await/network/concurrency: sync+flush is one deterministic step.
        return node.relay.flush(access_token, link_available=True)

    def replica_state(self, node_name: str) -> dict:
        node = self._node(node_name)
        return {"name": node.name, "connected": node.connected,
                "cursor": node.cursor,
                "observed_withdrawals": sorted(node.observed_withdrawals)}

    def event_log(self) -> tuple[RevocationEvent, ...]:
        self._verify_journal()
        if self._journal is None:
            return tuple(self._events)
        return tuple(RevocationEvent(e.sequence, e.participant_id)
                     for e in self._journal.events())
