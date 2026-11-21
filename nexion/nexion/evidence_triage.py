"""Offline, read-only forensic triage of an authenticated anchor mismatch.

A separately retained HMAC witness is INPUT evidence, never an authority to
repair, send messages, or reactivate anyone. No witness signer is provided here.
This module is not a production cryptographic attestation or a snapshot protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

from .journal_anchor import JournalAnchor
from .revocation_journal import GENESIS, RevocationJournal


FORMAT = "nexion-external-review-witness-v1"


@dataclass(frozen=True)
class EvidenceTriage:
    classification: str
    delivery_permitted: bool
    repair_permitted: bool
    explanation: str


def _canonical(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _digest_ids(ids: list[str]) -> str:
    return hashlib.sha256(_canonical(sorted(ids))).hexdigest()


def _fail(reason: str) -> EvidenceTriage:
    return EvidenceTriage("UNTRUSTED", False, False, reason)


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Repeated key in evidence document")
        result[key] = value
    return result


def triage_anchor_mismatch(authority_path: str | Path,
                           journal_path: str | Path,
                           anchor_path: str | Path, *,
                           anchor_key: bytes,
                           witness_document: bytes,
                           witness_key: bytes) -> EvidenceTriage:
    """Read files and authenticated witness; ALWAYS deny service and repair.

    The witness must have been retained independently before this inspection.
    Authentication proves possession of a key, not signer identity, freshness,
    hardware monotonicity, or independent custody. A positive classification is
    only a crash-pattern candidate and NEVER an automatic repair instruction.
    """
    if (not isinstance(anchor_key, bytes) or len(anchor_key) < 32
            or not isinstance(witness_key, bytes) or len(witness_key) < 32
            or hmac.compare_digest(anchor_key, witness_key)):
        return _fail("Invalid or non-independent laboratory key configuration")
    if not isinstance(witness_document, bytes) or len(witness_document) > 4096:
        return _fail("Missing or oversized external witness")
    paths = [Path(authority_path), Path(journal_path), Path(anchor_path)]
    if any(not p.is_file() or p.is_symlink() for p in paths):
        return _fail("Missing or symbolic-link evidence path")
    if len({p.resolve() for p in paths}) != len(paths):
        return _fail("Evidence files must be separate")
    try:
        doc = json.loads(witness_document, object_pairs_hook=_strict_pairs)
        if (not isinstance(doc, dict) or set(doc) != {"format", "state", "mac"}
                or doc["format"] != FORMAT or not isinstance(doc["state"], dict)
                or set(doc["state"]) != {"sequence", "digest", "withdrawn_digest",
                                         "checkpoint_digest"}
                or not isinstance(doc["mac"], str)
                or len(doc["mac"]) != 64):
            return _fail("External witness has an invalid schema")
        state = doc["state"]
        if (type(state["sequence"]) is not int or state["sequence"] < 0
                or any(not isinstance(state[key], str) or len(state[key]) != 64
                       or any(c not in "0123456789abcdef" for c in state[key])
                       for key in ("digest", "withdrawn_digest", "checkpoint_digest"))):
            return _fail("External witness state is malformed")
        expected = hmac.new(witness_key, _canonical({"format": FORMAT, "state": state}),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, doc["mac"]):
            return _fail("External witness authentication failed")
        # Authenticate the existing old anchor without auto-updating it.
        old = JournalAnchor(anchor_path, anchor_key)._read()
        if (set(old) != {"sequence", "digest", "pending", "checkpoint_digest"}
                or type(old["sequence"]) is not int or old["sequence"] < 0):
            return _fail("Malformed journal anchor state")

        # SQLite mode=ro: no schema creation, no migrations, no writes.
        with closing(sqlite3.connect(paths[0].resolve().as_uri() + "?mode=ro", uri=True)) as authority, \
             closing(sqlite3.connect(paths[1].resolve().as_uri() + "?mode=ro", uri=True)) as journal:
            authority.execute("PRAGMA query_only=ON")
            journal.execute("PRAGMA query_only=ON")
            rows = list(authority.execute("SELECT id, state FROM participants"))
            if len(rows) != len({r[0] for r in rows}):
                return _fail("Duplicate participants in authority")
            withdrawn = {pid for pid, st in rows if st == "withdrawn"}
            if any(st not in ("active", "pending", "withdrawn") for _, st in rows):
                return _fail("Invalid authority state")
            head_rows = list(journal.execute("SELECT sequence,digest,pending_participant "
                                             "FROM journal_head WHERE singleton=1"))
            if len(head_rows) != 1:
                return _fail("Journal head missing or ambiguous")
            sequence, digest, pending = head_rows[0]
            history = list(journal.execute(
                "SELECT sequence,participant_id,prev_digest,digest FROM journal_events "
                "ORDER BY sequence"))
            previous = GENESIS
            seen = set()
            for index, (n, pid, prev, current) in enumerate(history, 1):
                if (type(n) is not int or n != index or pid in seen or prev != previous
                        or current != RevocationJournal._hash(n, pid, previous)):
                    return _fail("Journal event chain is invalid")
                seen.add(pid)
                previous = current
            if sequence != len(history) or digest != previous:
                return _fail("Journal head does not match events")
            checkpoints = list(journal.execute("SELECT node_name,sequence,digest "
                                               "FROM replica_checkpoints ORDER BY node_name"))
            digests = [GENESIS] + [event[3] for event in history]
            if any(type(n) is not int or n < 0 or n > sequence or d != digests[n]
                   for _, n, d in checkpoints):
                return _fail("Replica checkpoint is invalid")
            checkpoint_digest = hashlib.sha256(_canonical(
                [list(x) for x in checkpoints])).hexdigest()
            actual = {"sequence": sequence, "digest": digest, "pending": pending,
                      "checkpoint_digest": checkpoint_digest}
            if pending is not None:
                if old != actual or pending not in {pid for pid, _ in rows}:
                    return _fail("Pending intent conflicts with authenticated anchor")
                return EvidenceTriage("INCOMPLETE_INTENT", False, False,
                                      "Authenticated pending intent requires manual review")
            if seen != withdrawn:
                return _fail("Authority and journal revocation states diverge")
            if state != {"sequence": sequence, "digest": digest,
                         "withdrawn_digest": _digest_ids(list(withdrawn)),
                         "checkpoint_digest": checkpoint_digest}:
                return _fail("External witness does not attest the current logical state")
            if old == actual:
                return EvidenceTriage("MATCHED_BUT_NOT_AUTHORIZED", False, False,
                                      "Evidence matches, but this is not permission to operate")
            if (sequence >= 1 and old["sequence"] == sequence - 1
                    and old["digest"] == digests[sequence - 1]
                    and old["pending"] == history[-1][1]
                    and old["checkpoint_digest"] == checkpoint_digest):
                return EvidenceTriage("POSSIBLE_POST_COMMIT_ANCHOR_LAG", False, False,
                                      "Matches a crash window; cause is not proven")
            return _fail("Anchor and journal differ outside the narrowly modelled crash window")
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error,
            UnicodeError, IndexError, OverflowError):
        return _fail("Evidence could not be safely validated")
