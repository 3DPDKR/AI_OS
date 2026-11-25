"""Bounded offline adaptation, with human-reviewed promotion proposals."""
from dataclasses import dataclass
from math import isfinite, fsum
from collections import deque

@dataclass(frozen=True)
class Policy:
    window: int = 128
    min_samples: int = 64
    min_gain: float = 0.02
    max_loss: float = 1.0
    def __post_init__(self):
        if (type(self.min_samples) is not int or type(self.window) is not int or
                not 2 <= self.min_samples <= self.window <= 10000):
            raise ValueError("invalid sample bounds")
        if not (isfinite(self.max_loss) and 0 < self.max_loss <= 1e6 and
                isfinite(self.min_gain) and 0 < self.min_gain <= self.max_loss):
            raise ValueError("invalid loss bounds")

class AdaptiveEngine:
    """One app, one candidate, chronological paired observations.
    The caller is responsible for data provenance and independent holdout.
    This class never activates a model or executes external actions.
    """
    def __init__(self, policy=Policy()):
        self.policy = policy
        self._pairs = deque(maxlen=policy.window)
        self._last = -1
    def observe(self, sequence, baseline_loss, candidate_loss):
        if type(sequence) is not int or sequence <= self._last:
            raise ValueError("sequence must increase")
        losses = []
        for value in (baseline_loss, candidate_loss):
            try:
                if (isinstance(value, bool) or not isfinite(value) or
                        not 0 <= value <= self.policy.max_loss):
                    raise ValueError("loss outside bounds")
                losses.append(float(value))
            except (TypeError, OverflowError, ValueError) as exc:
                raise ValueError("loss outside bounds") from exc
        self._pairs.append(tuple(losses))
        self._last = sequence
    def assess(self):
        n = len(self._pairs)
        gain = fsum(a-b for a,b in self._pairs)/n if n else 0.0
        eligible = n >= self.policy.min_samples and gain >= self.policy.min_gain
        return {"samples": n, "mean_gain": gain,
                "proposal": "independent_review" if eligible else "retain_baseline",
                "automatic_activation": False}
    def reset(self):
        self._pairs.clear()
        # Retain sequence watermark to prevent replay in the same session.

class HealthMonitor:
    """In-memory consecutive failure circuit breaker; no automatic retry."""
    def __init__(self, limit=3):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("invalid failure limit")
        self.limit = limit
        self.failures = 0
        self.open = False
    def record(self, success):
        if type(success) is not bool:
            raise ValueError("expected boolean")
        if not self.open:
            self.failures = 0 if success else self.failures + 1
            self.open = self.failures >= self.limit
        return self.status()
    def status(self):
        return {"failures": self.failures, "circuit_open": self.open,
                "recommendation": "fallback_and_review" if self.open else "normal"}
    def reset_after_review(self):
        """Caller must verify authorization and health before invoking."""
        self.failures = 0
        self.open = False
