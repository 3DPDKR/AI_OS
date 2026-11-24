"""Versioned offline SDK facade. No external actions."""
from .core import Swarm, Unit, Task
from .agent import ResearchAgent, Goal, GoalPolicy
from math import isfinite

SDK_VERSION = "0.1.0"

def select_model(baseline, candidates, *, min_samples=100, min_gain=0.01):
    """Select an offline candidate from paired, independently held-out losses.
    Caller must establish independence; this is a screening gate, not proof.
    Never deploys or modifies any model.
    """
    if min_samples < 2 or not isfinite(min_gain) or min_gain <= 0:
        raise ValueError("invalid screening policy")
    base = tuple(baseline)
    if any(not isfinite(x) or x < 0 for x in base):
        raise ValueError("invalid baseline losses")
    if len(base) < min_samples:
        return {"selected": "baseline", "reason": "insufficient_samples"}
    best, gain = "baseline", 0.0
    for name, values in sorted(candidates.items()):
        if name == "baseline":
            raise ValueError("reserved name")
        vals = tuple(values)
        if len(vals) != len(base) or any(not isfinite(x) or x < 0 for x in vals):
            continue
        improvement = sum(a-b for a,b in zip(base, vals))/len(base)
        if improvement >= min_gain and improvement > gain:
            best, gain = name, improvement
    return {"selected": best, "gain": gain, "samples": len(base),
            "requires_independent_confirmation": best != "baseline"}
