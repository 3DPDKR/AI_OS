"""Read-only recovery preflight; *never* execute a reconciliation.

This prototype revalidates an approved plan and its input records twice and
fails closed when a detectable change occurs. It is NOT a synchronization
primitive, a transaction spanning the two SQLite files, a signed permission,
or protection against a change that happens *after* the final read.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .consent import ConsentStore
from .recovery_protocol import (
    RecoveryDenied, RecoveryReviewSession, _snapshot,
)
from .revocation_journal import RevocationJournal


@dataclass(frozen=True)
class RecoveryPreflight:
    """Diagnostic result with deliberately non-executable safety flags."""
    plan_id: str
    participant_id: str
    action: str
    snapshot_digest: str
    status: str = "PRECHECK_ONLY"
    execute_automatically: bool = False
    may_reactivate_participant: bool = False
    delivery_permitted: bool = False


def preflight_recovery(session: RecoveryReviewSession,
                       store: ConsentStore, journal: RevocationJournal,
                       *, at: datetime | None = None) -> RecoveryPreflight:
    """Recheck approval and evidence before any hypothetical manual repair.

    No SQL INSERT/UPDATE/DELETE, journal repair method, or network call occurs.
    A genuine repair must instead acquire independently designed locks / atomic
    commit semantics across the authority and journal and re-validate there.
    """
    if not isinstance(session, RecoveryReviewSession) or session.state != "APPROVED":
        raise RecoveryDenied("An approved in-memory review session is required")

    first = session.work_order(store, journal, at=at)
    first_digest = _snapshot(store, journal)
    second = session.work_order(store, journal, at=at)
    second_digest = _snapshot(store, journal)
    if (first != second or first.plan_id != session.plan.plan_id
            or first_digest != second_digest
            or first_digest != session.plan.snapshot_digest
            or first.execute_automatically is not False
            or first.may_reactivate_participant is not False
            or first.delivery_permitted is not False):
        raise RecoveryDenied("Preflight state changed or is unsafe")

    return RecoveryPreflight(first.plan_id, first.participant_id,
                             first.action, second_digest)
