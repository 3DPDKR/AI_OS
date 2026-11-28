"""Experimental single-writer, offline checkpoint for adaptation and health.

Only trusted local files: SHA-256 detects corruption, not malicious changes.
Callers must serialize access, supply the expected scope/policy/limit, and
maintain any trusted anti-rollback watermark outside the checkpoint.
"""
import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from .adaptive import AdaptiveEngine, HealthMonitor

MAX_BYTES = 1024 * 1024


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False, ensure_ascii=True).encode('ascii')


def _restore(state, policy, limit, scope, min_sequence):
    if (type(scope) is not str or not scope or type(min_sequence) is not int
            or min_sequence < -1):
        raise ValueError('invalid checkpoint context')
    if (state['version'] != 1 or type(state['version']) is not int
            or state['scope'] != scope or _encode(state['policy']) != _encode(asdict(policy))):
        raise ValueError('checkpoint context mismatch')
    last, pairs = state['last'], state['pairs']
    if (type(last) is not int or last < min_sequence or type(pairs) is not list
            or len(pairs) > policy.window or len(pairs) > last + 1):
        raise ValueError('invalid checkpoint history')
    engine = AdaptiveEngine(policy)
    for seq, pair in enumerate(pairs, last - len(pairs) + 1):
        if type(pair) is not list or len(pair) != 2:
            raise ValueError('invalid checkpoint pair')
        engine.observe(seq, *pair)
    engine._last = last
    health = HealthMonitor(limit)
    h = state['health']
    if (type(h['limit']) is not int or h['limit'] != limit
            or type(h['failures']) is not int or not 0 <= h['failures'] <= limit
            or type(h['open']) is not bool or h['open'] != (h['failures'] == limit)):
        raise ValueError('invalid checkpoint circuit state')
    health.failures, health.open = h['failures'], h['open']
    return engine, health


def save_checkpoint(path, engine, health, *, scope):
    """Flush a validated checkpoint then atomically replace the target file."""
    state = dict(version=1, scope=scope, policy=asdict(engine.policy),
                 last=engine._last, pairs=[list(p) for p in engine._pairs],
                 health=dict(limit=health.limit, failures=health.failures, open=health.open))
    _restore(state, engine.policy, health.limit, scope, -1)
    raw = _encode(dict(state=state, sha256=hashlib.sha256(_encode(state)).hexdigest()))
    if len(raw) > MAX_BYTES:
        raise ValueError('checkpoint too large')
    path = Path(path)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temp = stream.name
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass


def load_checkpoint(path, *, policy, limit, scope, min_sequence=-1):
    """Return new objects; corrupt or missing state never silently resets."""
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('checkpoint too large')
    try:
        doc = json.loads(raw)
        state = doc['state']
        if not hmac.compare_digest(doc['sha256'], hashlib.sha256(_encode(state)).hexdigest()):
            raise ValueError('checkpoint checksum mismatch')
        return _restore(state, policy, limit, scope, min_sequence)
    except (TypeError, KeyError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError('invalid checkpoint') from exc
