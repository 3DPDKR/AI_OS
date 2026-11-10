# NEXION — factory adapter design contract (no live control)
Each facility interface must be separately consented to by a verified operator.

1. An authorized operator registers the facility (no port scanning or discovery of unconsenting systems).
2. Validate identity, specific equipment scope and operator authorization documents.
3. Require endpoint authentication, isolation and least privilege.
4. First connection is to a sandbox and read-only.
5. Run digital-twin simulation with collision and process-limit checks.
6. Verify local interlocks, human oversight and emergency stops.
7. Seek separate job-specific operator approval before any future actuation.
8. Audit every command and receipt.

Proposed future adapter methods: discover_capabilities, validate_job, simulate_job, request_operator_approval, emergency_stop. Actuation is NOT implemented in v0.1.0 and must never bypass local controls.
