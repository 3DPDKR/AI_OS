"""Offline, persistent revocation journal for restart/fault-injection experiments.

The chain is a corruption detector, NOT a cryptographic signature or consensus.
No networking or machinery control. A separate SQLite file acts as a model of a
node's durable event log; this module does not promise production durability.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Optional

from .consent import ConsentError


GENESIS = "0" * 64


class JournalCorruption(ConsentError):
    """Journal, replica cursor, or incomplete withdrawal intent is untrusted."""


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    participant_id: str
    kind: str = "withdrawn"


class RevocationJournal:
    """Single-process simulated journal, with persisted checkpoints and fail-close.

    A committed head sequence and hash detect missing, reordered, or modified
    event rows; an incomplete withdrawal intent prevents replay after a crash
    between authoritative revocation and journal recording. Not hardened
    against an attacker capable of rewriting both journal rows and metadata.
    """

    def __init__(self, db_path: str | Path):
        path = str(db_path)
        if path == ":memory:":
            raise ValueError("A persistent file path is required for the restart experiment")
        if not path:
            raise ValueError("Journal path cannot be empty")
        new_file = not Path(path).exists()
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        try:
            if not new_file:
                present = {row[0] for row in self.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                required = {"journal_head", "journal_events", "replica_checkpoints"}
                if not required.issubset(present):
                    raise JournalCorruption("Existing journal is missing required tables")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS journal_head (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    sequence INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    pending_participant TEXT
                );
                CREATE TABLE IF NOT EXISTS journal_events (
                    sequence INTEGER PRIMARY KEY,
                    participant_id TEXT NOT NULL,
                    prev_digest TEXT NOT NULL,
                    digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS replica_checkpoints (
                    node_name TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL,
                    digest TEXT NOT NULL
                );
            """)
            head = self.db.execute("SELECT * FROM journal_head WHERE singleton=1").fetchone()
            if head is None:
                if not new_file:
                    raise JournalCorruption("Existing journal lacks its committed head")
                with self.db:
                    self.db.execute("INSERT INTO journal_head VALUES (1, 0, ?, NULL)", (GENESIS,))
            self.verify()
        except BaseException:
            self.db.close()
            raise

    @staticmethod
    def _hash(sequence: int, participant_id: str, previous: str) -> str:
        canonical = json.dumps(["NEXION-revocation-v1", sequence, participant_id, previous],
                               ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _head(self) -> sqlite3.Row:
        head = self.db.execute("SELECT * FROM journal_head WHERE singleton=1").fetchone()
        if head is None:
            raise JournalCorruption("Missing journal head")
        return head

    def verify(self, *, allow_pending: bool = False) -> int:
        """Verify entire local chain AND checkpoint digests before any delivery.

        This intentionally rechecks the full short research log. Production
        systems need independent authenticated roots and bounded verification.
        """
        try:
            head = self._head()
            if head["pending_participant"] is not None and not allow_pending:
                raise JournalCorruption("Unfinished withdrawal intent; halt all operations")
            sequence = 0
            previous = GENESIS
            digests = {0: GENESIS}
            for row in self.db.execute("SELECT * FROM journal_events ORDER BY sequence"):
                sequence += 1
                expected = self._hash(sequence, row["participant_id"], previous)
                if (row["sequence"] != sequence or row["prev_digest"] != previous
                        or row["digest"] != expected):
                    raise JournalCorruption("Missing, reordered, or modified revocation event")
                previous = expected
                digests[sequence] = previous
            if head["sequence"] != sequence or head["digest"] != previous:
                raise JournalCorruption("Journal head disagrees with committed events")
            for row in self.db.execute("SELECT * FROM replica_checkpoints"):
                if (row["sequence"] not in digests
                        or row["digest"] != digests[row["sequence"]]):
                    raise JournalCorruption("Replica checkpoint not anchored in event chain")
            return sequence
        except (sqlite3.DatabaseError, TypeError, ValueError) as exc:
            raise JournalCorruption("Journal could not be validated") from exc

    def begin_withdrawal(self, participant_id: str) -> None:
        """Durably reserve an intent before the authoritative revocation.

        A crash before finish() leaves the journal blocked until reconciliation.
        """
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.verify()
            if not participant_id:
                raise ValueError("Participant identifier required")
            self.db.execute("UPDATE journal_head SET pending_participant=? WHERE singleton=1",
                            (participant_id,))

    def abort_withdrawal(self, participant_id: str) -> None:
        """Only for a known rolled-back/failed store withdrawal (not for crashes)."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            head = self._head()
            if head["pending_participant"] != participant_id:
                raise JournalCorruption("Withdrawal intent mismatch")
            self.verify(allow_pending=True)
            self.db.execute("UPDATE journal_head SET pending_participant=NULL WHERE singleton=1")

    def finish_withdrawal(self, participant_id: str) -> JournalEvent:
        """Atomically append event and clear reserved intent in journal SQLite."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            head = self._head()
            if head["pending_participant"] != participant_id:
                raise JournalCorruption("Missing or mismatched withdrawal intent")
            self.verify(allow_pending=True)
            sequence = head["sequence"] + 1
            digest = self._hash(sequence, participant_id, head["digest"])
            self.db.execute("INSERT INTO journal_events VALUES (?,?,?,?)",
                            (sequence, participant_id, head["digest"], digest))
            self.db.execute("""UPDATE journal_head SET sequence=?,digest=?,
                pending_participant=NULL WHERE singleton=1""", (sequence, digest))
        return JournalEvent(sequence, participant_id)

    def events(self, *, after: int = 0) -> tuple[JournalEvent, ...]:
        head = self.verify()
        if not isinstance(after, int) or after < 0 or after > head:
            raise JournalCorruption("Cursor outside event-log bounds")
        return tuple(JournalEvent(row["sequence"], row["participant_id"])
                     for row in self.db.execute(
                         "SELECT sequence,participant_id FROM journal_events WHERE sequence>? ORDER BY sequence",
                         (after,)))

    def checkpoint(self, node: str, sequence: int) -> None:
        """Persist last applied log cursor, including its content digest."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            head = self.verify()
            if not isinstance(sequence, int) or sequence < 0 or sequence > head:
                raise JournalCorruption("Invalid checkpoint sequence")
            row = self.db.execute("SELECT digest FROM journal_events WHERE sequence=?",
                                  (sequence,)).fetchone()
            digest = GENESIS if sequence == 0 else row["digest"]
            existing = self.db.execute("SELECT sequence FROM replica_checkpoints WHERE node_name=?",
                                       (node,)).fetchone()
            if existing and sequence < existing["sequence"]:
                raise JournalCorruption("Checkpoint cursor cannot move backwards")
            self.db.execute("""INSERT INTO replica_checkpoints VALUES (?,?,?)
                ON CONFLICT(node_name) DO UPDATE SET sequence=excluded.sequence,digest=excluded.digest""",
                (node, sequence, digest))

    def restore(self, node: str) -> tuple[int, set[str]]:
        """On restart, reconstruct acknowledged withdrawals from durable events."""
        self.verify()
        row = self.db.execute("SELECT sequence FROM replica_checkpoints WHERE node_name=?",
                              (node,)).fetchone()
        cursor = 0 if row is None else row["sequence"]
        events = self.db.execute("SELECT participant_id FROM journal_events WHERE sequence<=?",
                                 (cursor,)).fetchall()
        return cursor, {row["participant_id"] for row in events}

    def close(self) -> None:
        self.db.close()
