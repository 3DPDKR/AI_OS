# NEXION CORE SDK 0.2.0 experimental
Adds bounded chronological paired-loss screening and in-memory circuit breaker.
Use one AdaptiveEngine per candidate and app. Inputs must be out-of-sample paired
losses on the same observations; do not reuse screening data for confirmation.
An independent review proposal is not evidence of statistical significance.
No automatic deployment, retry, rollback, live hardware, or authenticated
approval is implemented. Sequence watermark is session-local; durable replay
protection and signed model registry are future work.
HealthMonitor requests fallback and review; host owns actual fallback and
authorization. No network, new runtime dependencies or signing changes.
Run: python -m unittest discover -s tests -q (from nexion directory).
Existing research and recovery policy remain unchanged.
