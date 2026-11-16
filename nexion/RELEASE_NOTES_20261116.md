# NEXION v0.2.6 — Authority / Journal Recovery Review (2026-11-16)

## Changes
- New read-only `assess_recovery()` detects out-of-band authority withdrawals, rollback, duplicate/orphan journal events, interrupted withdrawal before/after authority commit, and untrusted journal/anchor/authority DB states.
- `RevocationJournal.open_for_review()` opens an existing SQLite journal read-only, including an authenticated pending withdrawal intent; normal startup still refuses that state.
- In journal mode, `DistributedConsentLab` now requires a clean cross-file recovery assessment for queue, withdrawal, sync, flush and startup/restart. Mismatch latches closed until operator review and a new lab instance.
- No auto-repair, network operations, purchases or machine controls.

## Verification
- Baseline from supplied v0.2.5 package: 107/107 tests pass.
- New tests: 19, all pass; total: 126 tests. See `TEST_RESULTS_20261116.txt`.
- This is **single-process SQLite fault simulation**. No CI, real networking, hardware, cloud or production safety claim.

## Follow-on
- Explicit operator-approved resolution protocol + atomicity evidence; never automatically weaken a valid revocation.
