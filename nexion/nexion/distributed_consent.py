"""Deterministic, offline-only consent-revocation replication experiment.

The central ConsentStore is a *simulation oracle*, not a distributed database.
Each node has a local OfflineRelay and delayed revocation-event cursor.
Deliveries require a fresh, available authority check (fail closed), so stale
replicas cannot deliver during partitions. No network or hardware I/O occurs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional
from datetime import datetime
import re

from .consent import ConsentError, ConsentStore
from .relay import OfflineRelay

_NODE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}\\Z")


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
    The log is in-memory and only includes withdrawals performed via withdraw().
    No offline node is allowed to deliver using cached consent alone.
    """

    def __init__(self, store: ConsentStore, node_names: list[str], *,
                 clock: Optional[Callable[[], datetime]] = None):
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
        return node.relay.queue(
            access_token, recipient_id, body, client_id, ttl_seconds=ttl_seconds)

    def withdraw(self, participant_id: str, withdrawal_token: str) -> RevocationEvent:
        """First commit revocation to the authoritative store; then log event."""
        if not self.authority_available:
            raise Unavailable("Consent authority unavailable")
        self.store.withdraw(participant_id, withdrawal_token)
        event = RevocationEvent(len(self._events) + 1, participant_id)
        self._events.append(event)
        return event

    def sync(self, node_name: str) -> dict:
        """Reconcile the node on reconnection, with sequence-based replay."""
        node = self._node(node_name)
        if not node.connected:
            raise Unavailable("Node link unavailable")
        if not self.authority_available:
            raise Unavailable("Consent authority unavailable")
        new = self._events[node.cursor:]
        for event in new:
            node.observed_withdrawals.add(event.participant_id)
        # This also detects revocations made directly in ConsentStore, although
        # these are not represented in the event log's sequence counter.
        changes = node.relay.reconcile()
        node.cursor = len(self._events)
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
        return tuple(self._events)
