"""Offline, read-only operator recovery *planning* state machine.

No database repair, network call, participant reactivation, or operational
permission is implemented here. An approval is only a rehearsal work order.
Caller-supplied operator labels/evidence are NOT authenticated identities or
independently verified evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

from .consent import ConsentStore
from .recovery_review import assess_recovery
from .revocation_journal import JournalCorruption, RevocationJournal


class RecoveryDenied(ValueError):
    """Fail-closed: a recovery step is unsafe or approval is not valid."""


_ACTIONS = {
    "PENDING_COMMITTED": "append_missing_revocation_event_after_independent_evidence",
    "PENDING_UNCOMMITTED": "clear_intent_only_after_independent_rollback_evidence",
}


def _now(value: datetime | None) -> datetime:
    if value is None:
        value = datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RecoveryDenied("An aware UTC-compatible timestamp is required")
    return value.astimezone(timezone.utc)


def _label(value: str, field: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 120
            or not value.strip() or value != value.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise RecoveryDenied(f"Invalid {field}")
    return value


def _snapshot(store: ConsentStore, journal: RevocationJournal) -> str:
    """Conservative fingerprint of relevant state; never export raw credentials.

    This is a local stale-plan detector, not an atomic cross-DB snapshot, an
    authority signature, or protection from coordinated file/key rollback.
    """
    try:
        journal.verify(allow_pending=True)
        participants = [list(row) for row in store.db.execute(
            "SELECT * FROM participants ORDER BY id")]
        events = [list(row) for row in journal.db.execute(
            "SELECT * FROM journal_events ORDER BY sequence")]
        head = journal._anchor_snapshot()
        # Also detect out-of-band message writes after drafting a plan.
        messages = [list(row) for row in store.db.execute(
            "SELECT * FROM messages ORDER BY id")]
        # Audit-only changes also invalidate a pre-approved repair plan.
        audit = [list(row) for row in store.db.execute(
            "SELECT * FROM audit ORDER BY id")]
        canonical = json.dumps(["NEXION-recovery-snapshot-v2", participants,
                                events, head, messages, audit], ensure_ascii=False,
                               separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except (sqlite3.Error, JournalCorruption, ValueError, TypeError, KeyError) as exc:
        raise RecoveryDenied("Cannot trust current recovery snapshot") from exc


@dataclass(frozen=True)
class RecoveryPlan:
    plan_id: str
    source_state: str
    action: str
    participant_id: str
    snapshot_digest: str
    event_count: int
    created_at: datetime
    expires_at: datetime
    delivery_permitted: bool = False


@dataclass(frozen=True)
class RecoveryWorkOrder:
    """Human-facing, non-executable dry-run approval record."""
    plan_id: str
    action: str
    participant_id: str
    evidence_reference: str
    reviewed_by: str
    approved_by: str
    execute_automatically: bool = False
    may_reactivate_participant: bool = False
    delivery_permitted: bool = False


def draft_recovery(store: ConsentStore, journal: RevocationJournal, *,
                   at: datetime | None = None,
                   ttl: timedelta = timedelta(minutes=15)) -> RecoveryPlan:
    created = _now(at)
    if not isinstance(ttl, timedelta) or not timedelta(0) < ttl <= timedelta(hours=1):
        raise RecoveryDenied("Draft expiry must be between 0 and 60 minutes")
    assessment = assess_recovery(store, journal)
    if assessment.delivery_permitted or assessment.state not in _ACTIONS:
        raise RecoveryDenied(f"No safe pending recovery plan for {assessment.state}")
    try:
        participant_id = journal._head()["pending_participant"]
        if not isinstance(participant_id, str) or not participant_id:
            raise RecoveryDenied("Missing target participant")
        digest = _snapshot(store, journal)
    except (JournalCorruption, sqlite3.Error, TypeError, KeyError) as exc:
        raise RecoveryDenied("Cannot read recovery intent") from exc
    seed = json.dumps(["NEXION-recovery-plan-v1", assessment.state,
                       participant_id, digest], separators=(",", ":"))
    plan_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return RecoveryPlan(plan_id, assessment.state, _ACTIONS[assessment.state],
                        participant_id, digest, assessment.event_count,
                        created, created + ttl)


class RecoveryReviewSession:
    """Ephemeral local approval rehearsal; never repairs either database.

    NEW -> REVIEWED -> APPROVED or NEW/REVIEWED -> REJECTED.
    Expiration and staleness are checked on every forward transition.
    Losing the process loses the approval (never silently resumes).
    """
    def __init__(self, plan: RecoveryPlan, *, requested_by: str):
        if not isinstance(plan, RecoveryPlan):
            raise RecoveryDenied("Expected a typed recovery plan")
        self.plan = plan
        self.requested_by = _label(requested_by, "requester")
        self.state = "NEW"
        self.evidence_reference: str | None = None
        self.reviewed_by: str | None = None
        self.approved_by: str | None = None

    def _check_current(self, store: ConsentStore, journal: RevocationJournal,
                       at: datetime | None) -> None:
        # Validate all plan fields again; even a caller-constructed dataclass
        # must not be able to smuggle a dangerous action into a work order.
        if (self.plan.source_state not in _ACTIONS
                or self.plan.action != _ACTIONS[self.plan.source_state]
                or self.plan.delivery_permitted is not False
                or not isinstance(self.plan.participant_id, str)
                or not isinstance(self.plan.created_at, datetime)
                or not isinstance(self.plan.expires_at, datetime)
                or self.plan.created_at.tzinfo is None
                or self.plan.expires_at.tzinfo is None
                or not timedelta(0) < self.plan.expires_at - self.plan.created_at <= timedelta(hours=1)):
            raise RecoveryDenied("Recovery plan fields are invalid")
        seed = json.dumps(["NEXION-recovery-plan-v1", self.plan.source_state,
                           self.plan.participant_id, self.plan.snapshot_digest],
                          separators=(",", ":"))
        if hashlib.sha256(seed.encode("utf-8")).hexdigest() != self.plan.plan_id:
            raise RecoveryDenied("Recovery plan identifier mismatch")
        instant = _now(at)
        if not self.plan.created_at <= instant < self.plan.expires_at:
            raise RecoveryDenied("Recovery plan expired or clock moved backwards")
        assessment = assess_recovery(store, journal)
        if (assessment.state != self.plan.source_state
                or assessment.event_count != self.plan.event_count
                or assessment.delivery_permitted
                or journal._head()["pending_participant"] != self.plan.participant_id
                or _snapshot(store, journal) != self.plan.snapshot_digest):
            raise RecoveryDenied("Recovery plan is stale or records are untrusted")

    def review(self, store: ConsentStore, journal: RevocationJournal, *,
               reviewed_by: str, evidence_reference: str,
               at: datetime | None = None) -> None:
        if self.state != "NEW":
            raise RecoveryDenied("Only a new plan may be reviewed")
        reviewer = _label(reviewed_by, "reviewer")
        evidence = _label(evidence_reference, "evidence reference")
        if reviewer == self.requested_by:
            raise RecoveryDenied("Reviewer must differ from requester in this simulation")
        self._check_current(store, journal, at)
        self.reviewed_by = reviewer
        self.evidence_reference = evidence
        self.state = "REVIEWED"

    def approve(self, store: ConsentStore, journal: RevocationJournal, *,
                approved_by: str, at: datetime | None = None) -> RecoveryWorkOrder:
        if self.state != "REVIEWED":
            raise RecoveryDenied("Review must occur before approval")
        approver = _label(approved_by, "approver")
        if approver == self.requested_by:
            raise RecoveryDenied("Requester cannot approve own draft in this simulation")
        # Two checks model a possible change during final approval. Do not
        # persist APPROVED until both have succeeded: otherwise a failure in
        # the second check leaves a phantom approval in memory.
        self._check_current(store, journal, at)
        self._check_current(store, journal, at)
        order = RecoveryWorkOrder(self.plan.plan_id, self.plan.action,
                                  self.plan.participant_id, self.evidence_reference,
                                  self.reviewed_by, approver)
        self.approved_by = approver
        self.state = "APPROVED"
        return order

    def work_order(self, store: ConsentStore, journal: RevocationJournal, *,
                   at: datetime | None = None) -> RecoveryWorkOrder:
        if self.state != "APPROVED" or not self.approved_by or not self.reviewed_by:
            raise RecoveryDenied("Unapproved plans have no work order")
        self._check_current(store, journal, at)
        return RecoveryWorkOrder(self.plan.plan_id, self.plan.action,
                                 self.plan.participant_id, self.evidence_reference,
                                 self.reviewed_by, self.approved_by)

    def reject(self) -> None:
        if self.state not in ("NEW", "REVIEWED"):
            raise RecoveryDenied("Only an unapproved plan can be rejected")
        self.state = "REJECTED"
