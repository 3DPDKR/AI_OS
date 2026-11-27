"""Versioned offline SDK facade. No external actions."""
from .core import Swarm, Unit, Task
from .agent import ResearchAgent, Goal, GoalPolicy
from math import isfinite, fsum

SDK_VERSION = "0.2.0"

def _loss(value):
    """Normalize a finite nonnegative numeric loss; never accept booleans."""
    try:
        if isinstance(value, bool) or not isfinite(value) or value < 0:
            raise ValueError("invalid loss")
        result = float(value)
        if not isfinite(result) or (value > 0 and result == 0):
            raise ValueError("loss outside float range")
        return result
    except (TypeError, OverflowError, ValueError) as exc:
        raise ValueError("invalid loss") from exc


def _mean_gain(base, vals):
    differences = tuple(a-b for a,b in zip(base, vals))
    try:
        return fsum(differences)/len(base)
    except OverflowError:
        # Each difference is finite; only the unscaled sum can overflow.
        scale = max(abs(d) for d in differences)
        return (fsum(d/scale for d in differences)/len(base))*scale


def select_model(baseline, candidates, *, min_samples=100, min_gain=0.01):
    """Select an offline candidate from paired, independently held-out losses.
    Caller must establish independence; this is a screening gate, not proof.
    Never deploys or modifies any model.
    """
    if type(min_samples) is not int or min_samples < 2:
        raise ValueError("invalid screening policy")
    try:
        min_gain = _loss(min_gain)
        if min_gain <= 0:
            raise ValueError("minimum gain must be positive")
    except ValueError as exc:
        raise ValueError("invalid screening policy") from exc
    try:
        base = tuple(_loss(x) for x in baseline)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid baseline losses") from exc
    if len(base) < min_samples:
        return {"selected": "baseline", "reason": "insufficient_samples"}
    best, gain = "baseline", 0.0
    for name, values in sorted(candidates.items()):
        if name == "baseline":
            raise ValueError("reserved name")
        try:
            vals = tuple(_loss(x) for x in values)
        except (TypeError, ValueError):
            continue
        if len(vals) != len(base):
            continue
        improvement = _mean_gain(base, vals)
        if improvement >= min_gain and improvement > gain:
            best, gain = name, improvement
    return {"selected": best, "gain": gain, "samples": len(base),
            "requires_independent_confirmation": best != "baseline"}

from .adaptive import AdaptiveEngine, Policy, HealthMonitor
