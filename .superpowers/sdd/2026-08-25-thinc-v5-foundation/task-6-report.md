# Task 6 report — Unified Research Preview assessment API

## Status

Implemented the Foundation-only assessment API and its orchestration layer:

- `POST /v1/assessments`
- `GET /v1/assessments/{assessment_id}`
- `POST /v1/assessments/{assessment_id}/approvals`
- Tenant-scoped idempotency for both POST routes, including durable PostgreSQL
  uniqueness and advisory locking.
- RFC 9457 problem details for request validation, not-found, and idempotency
  conflicts.
- Economics execution, provenance, gate results with `GateReasonCode`, and the
  unchanged common Research Preview envelope fields.
- A separate `assessment-api-v1.json` OpenAPI snapshot; the common
  `assessment-v1.json` snapshot was not changed.
- Tenant-isolated in-memory test repository and PostgreSQL repository using
  transaction-local `app.tenant_id` RLS context.
- Approval binding to the exact tenant, assessment, approver, and idempotency
  request without mutating stored engine output.
- No high-impact action endpoints.

## Verification

- Task suite: `11 passed, 1 skipped`.
- Full regression: `83 passed, 18 skipped`.
- The Task 6 live PostgreSQL API test skipped because the required test database
  URLs were not provided. It is not counted as a successful live database run.
- The other live PostgreSQL role/RLS tests also skipped for the same environment
  prerequisite; offline migration and repository-context tests passed.
- Ruff and mypy are run as final pre-commit gates.

## Deployment concern

Production authentication is intentionally outside Foundation. `create_app`
requires an injected identity provider and has no default; the included
`TestIdentity` mechanism is test-only. This API is explicitly not ready for
deployment until production authentication and authorization are supplied.

The local interpreter was Python 3.14.4 while the project declares Python 3.12.
FastAPI emitted an upstream `asyncio.iscoroutinefunction` deprecation warning on
3.14; this does not represent a passing test on the declared Python 3.12 runtime.
