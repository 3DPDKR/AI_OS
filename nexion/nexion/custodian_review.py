"""Offline unanimous floor review; not a consensus or authorization protocol."""
from .evidence_freshness import (
    FLOOR_FORMAT, FreshnessAssessment, _authenticated, _hex64, verify_witness_floor,
)


def review_custodians(journal_path, *, witness_document, witness_key,
                      custodian_keys, floor_documents, expected_scope):
    """Require every pinned custodian to authenticate exactly the same floor.

    A missing/conflicting reply never reduces the configured membership.
    Distinct keys do not establish independent custody or temporal freshness.
    All outcomes are diagnostic only; no permission is ever granted.
    """
    def reject(status, explanation):
        return FreshnessAssessment(status, False, False, explanation)

    try:
        if (type(custodian_keys) is not dict or type(floor_documents) is not dict
                or not 2 <= len(custodian_keys) <= 16
                or not isinstance(witness_key, bytes) or len(witness_key) < 32
                or any(type(name) is not str or not 1 <= len(name) <= 64
                       or type(key) is not bytes or len(key) < 32
                       for name, key in custodian_keys.items())
                or len(set(custodian_keys.values()) | {witness_key}) != len(custodian_keys) + 1):
            return reject("UNTRUSTED", "Invalid pinned membership or reused key")
        if set(floor_documents) - set(custodian_keys):
            return reject("UNTRUSTED", "Unexpected custodian")
        if set(custodian_keys) - set(floor_documents):
            return reject("CUSTODIAN_UNAVAILABLE", "Required floor reply missing")
        floors = []
        for name, key in custodian_keys.items():
            state = _authenticated(floor_documents[name], key, FLOOR_FORMAT)
            if (set(state) != {"scope", "min_sequence", "min_digest"}
                    or state["scope"] != expected_scope
                    or type(state["min_sequence"]) is not int or state["min_sequence"] < 0
                    or not _hex64(state["min_digest"])):
                return reject("UNTRUSTED", "Invalid floor or scope")
            floors.append(state)
        if any(floor != floors[0] for floor in floors[1:]):
            return reject("CUSTODIAN_DISAGREEMENT", "Authenticated floors differ")
        # Check the agreed floor against the existing read-only journal verifier once.
        name = next(iter(custodian_keys))
        return verify_witness_floor(
            journal_path, witness_document=witness_document, witness_key=witness_key,
            floor_document=floor_documents[name], floor_key=custodian_keys[name],
            expected_scope=expected_scope)
    except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError):
        return reject("UNTRUSTED", "Custodian review failed")
