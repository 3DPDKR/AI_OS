"""Read-only, fail-closed reconciliation assessment for the local consent lab.

Never authorizes writes or repairs. A clean assessment is not proof of a
cross-database atomic snapshot or permission to operate real equipment.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from .consent import ConsentStore
from .revocation_journal import RevocationJournal, JournalCorruption


@dataclass(frozen=True)
class RecoveryAssessment:
    state: str
    delivery_permitted: bool
    event_count: int
    discrepancy_count: int
    operator_action: str


def assess_recovery(store: ConsentStore, journal: RevocationJournal) -> RecoveryAssessment:
    """Inspect both local databases, without mutating either one.

    This is a deterministic safety *triage*, not an automated repair. It can
    classify a crashed withdrawal with a valid authenticated pending intent,
    while an ordinary journal open still refuses to resume delivery.
    """
    denied = lambda state, count, action, events=0: RecoveryAssessment(
        state, False, events, count, action)
    try:
        sequence = journal.verify(allow_pending=True)
        pending = journal._head()["pending_participant"]
        states = dict(store.db.execute("SELECT id, state FROM participants"))
        rows = journal.db.execute(
            "SELECT participant_id FROM journal_events ORDER BY sequence"
        ).fetchall()
        event_ids = [row["participant_id"] for row in rows]
    except (sqlite3.Error, JournalCorruption, ValueError, TypeError, KeyError):
        return denied("UNTRUSTED", 1, "restore_independently_verified_backup")

    if len(event_ids) != sequence or any(
        state not in ("active", "pending", "withdrawn") for state in states.values()
    ):
        return denied("UNTRUSTED", 1, "restore_independently_verified_backup", sequence)

    event_set = set(event_ids)
    duplicate_count = len(event_ids) - len(event_set)
    invalid_events = sum(states.get(pid) != "withdrawn" for pid in event_set)
    missing = {pid for pid, state in states.items()
               if state == "withdrawn" and pid not in event_set}

    # Pending is an authenticated intent recorded *before* authority commit.
    # At most the pending participant can be absent from the journal.
    unrelated_missing = missing - ({pending} if pending is not None else set())
    if (duplicate_count or invalid_events or unrelated_missing
            or pending is not None and (pending in event_set or pending not in states)):
        count = duplicate_count + invalid_events + len(unrelated_missing)
        if pending is not None and (pending in event_set or pending not in states):
            count += 1
        return denied("DIVERGED", count, "isolate_and_investigate_records", sequence)

    if pending is not None:
        state = states[pending]
        if state == "withdrawn" and pending in missing:
            return denied("PENDING_COMMITTED", 1,
                          "operator_verify_authority_commit_before_reconciliation", sequence)
        if state in ("active", "pending") and not missing:
            return denied("PENDING_UNCOMMITTED", 1,
                          "operator_verify_rollback_before_clearing_intent", sequence)
        return denied("DIVERGED", 1, "isolate_and_investigate_records", sequence)

    if missing:
        return denied("DIVERGED", len(missing),
                      "isolate_and_investigate_records", sequence)

    return RecoveryAssessment("CLEAN", True, sequence, 0, "none")
