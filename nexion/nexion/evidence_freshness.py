"""Fail-closed, read-only laboratory verification of a witness against a high-water mark.

A trusted *external* custodian must preserve the checkpoint monotonically.
This module does not issue checkpoints, repair databases, grant consent, or prove
wall-clock freshness. Rolling back ALL evidence and the external floor together
is outside its security boundary.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

from .evidence_triage import FORMAT as WITNESS_FORMAT
from .revocation_journal import GENESIS, RevocationJournal

FLOOR_FORMAT = "nexion-external-monotonic-floor-v1"
HEX = set("0123456789abcdef")


@dataclass(frozen=True)
class FreshnessAssessment:
    classification: str
    delivery_permitted: bool
    repair_permitted: bool
    explanation: str


def _result(status: str, explanation: str) -> FreshnessAssessment:
    return FreshnessAssessment(status, False, False, explanation)


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _no_duplicates(pairs):
    obj = {}
    for key, val in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON field")
        obj[key] = val
    return obj


def _hex64(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in HEX for c in value)


def _authenticated(raw: bytes, key: bytes, fmt: str) -> dict:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 4096:
        raise ValueError("Missing or oversized document")
    doc = json.loads(raw, object_pairs_hook=_no_duplicates)
    if (not isinstance(doc, dict) or set(doc) != {"format", "state", "mac"}
            or doc["format"] != fmt or not isinstance(doc["state"], dict)
            or not _hex64(doc["mac"])):
        raise ValueError("Malformed authenticated envelope")
    signed = {"format": fmt, "state": doc["state"]}
    expected = hmac.new(key, _canonical(signed), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, doc["mac"]):
        raise ValueError("Authentication failed")
    return doc["state"]


def verify_witness_floor(journal_path: str | Path, *, witness_document: bytes,
                         witness_key: bytes, floor_document: bytes,
                         floor_key: bytes, expected_scope: str) -> FreshnessAssessment:
    """Compare signed witness and separately held minimum known journal state.

    Returns BOUNDED_CONSISTENT, REPLAY_OR_ROLLBACK, or UNTRUSTED; no status
    authorizes message delivery, modification, recovery, or consent renewal.
    The floor's custody and non-rollback property must be supplied externally.
    """
    if (not isinstance(witness_key, bytes) or len(witness_key) < 32
            or not isinstance(floor_key, bytes) or len(floor_key) < 32
            or hmac.compare_digest(witness_key, floor_key)
            or not isinstance(expected_scope, str) or not 1 <= len(expected_scope) <= 128
            or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
                   for c in expected_scope)):
        return _result("UNTRUSTED", "Invalid lab keys or stream scope")
    path = Path(journal_path)
    if not path.is_file() or path.is_symlink():
        return _result("UNTRUSTED", "Journal file missing or symbolic link")
    try:
        witness = _authenticated(witness_document, witness_key, WITNESS_FORMAT)
        floor = _authenticated(floor_document, floor_key, FLOOR_FORMAT)
        if (set(witness) != {"sequence", "digest", "withdrawn_digest", "checkpoint_digest"}
                or type(witness["sequence"]) is not int or witness["sequence"] < 0
                or any(not _hex64(witness[k]) for k in
                       ("digest", "withdrawn_digest", "checkpoint_digest"))
                or set(floor) != {"scope", "min_sequence", "min_digest"}
                or floor["scope"] != expected_scope
                or type(floor["min_sequence"]) is not int or floor["min_sequence"] < 0
                or not _hex64(floor["min_digest"])):
            return _result("UNTRUSTED", "Malformed or wrong-scope witness/floor")
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = list(db.execute("SELECT sequence,participant_id,prev_digest,digest "
                                   "FROM journal_events ORDER BY sequence"))
            heads = list(db.execute("SELECT sequence,digest FROM journal_head WHERE singleton=1"))
        digests = [GENESIS]
        participants = set()
        for index, (seq, pid, prev, digest) in enumerate(rows, 1):
            if (type(seq) is not int or seq != index or not isinstance(pid, str)
                    or pid in participants or prev != digests[-1]
                    or digest != RevocationJournal._hash(seq, pid, prev)):
                return _result("UNTRUSTED", "Journal event chain is invalid")
            participants.add(pid)
            digests.append(digest)
        if len(heads) != 1 or heads[0] != (len(rows), digests[-1]):
            return _result("UNTRUSTED", "Journal head is invalid")
        minimum = floor["min_sequence"]
        if witness["sequence"] < minimum or len(rows) < minimum:
            return _result("REPLAY_OR_ROLLBACK", "Evidence predates the trusted floor")
        if floor["min_digest"] != digests[minimum]:
            return _result("UNTRUSTED", "Floor digest is not in the current journal chain")
        if witness["sequence"] != len(rows) or witness["digest"] != digests[-1]:
            return _result("UNTRUSTED", "Witness does not describe the journal head")
        return _result("BOUNDED_CONSISTENT", "State is at/after floor; real freshness unproven")
    except (OSError, TypeError, ValueError, KeyError, IndexError,
            UnicodeError, sqlite3.Error, OverflowError):
        return _result("UNTRUSTED", "Evidence cannot be safely validated")
