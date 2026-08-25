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

## Review round 1/5

- Added an injected `EngineRegistry` contract. The production registry still
  contains Economics only, while callers can inject future registrations.
- Each registered engine output is now written to its own tenant-owned,
  RLS-protected `engine_output_records` row in a separate transaction before
  gate evaluation. Tests cover registration order and retention of an earlier
  output when a later engine raises.
- Declared model-derived RFC 9457 responses using only
  `application/problem+json` for relevant 400/404/409/422 responses and updated
  the API-only OpenAPI snapshot. The legacy FastAPI `HTTPValidationError`
  contract is absent.
- Bounded the test-only actor ID to 255 nonblank characters and explicitly
  validates textual tenant IDs as nonblank/canonical UUID-sized input. Pydantic
  dependency failures now return RFC 9457 status 422 for create and approval.
- API/security/contract suite: `16 passed, 1 skipped`.
- Combined focused suite including registry and persistence schema:
  `27 passed, 1 skipped`.
- Full regression: `91 passed, 18 skipped`.
- Ruff: clean. Mypy: clean across 20 source files.
- The skipped live PostgreSQL tests remain unverified and are not counted as
  successful database runs.

## Review round 2/5

- Assessment POST idempotency now reserves a stable assessment ID before any
  engine runs. In-memory callers coordinate through a condition; PostgreSQL
  callers coordinate through the tenant-scoped unique key plus advisory locks.
- Reservations use `PENDING`, `COMPLETED`, and `FAILED` states with an owner
  token. Followers wait for the completed response. Ordinary executor failures
  mark the reservation retryable, and a five-minute PostgreSQL lease provides
  explicit crash-recovery semantics without changing the assessment ID.
- Successful engine outputs are reused by their declared `output_model` on a
  retry, so completed engines are not executed twice and non-deterministic
  hashes cannot poison retry. Engine outputs now have a tenant-aware foreign
  key to the reserved assessment, preventing orphan rows.
- Added a deterministic two-thread in-memory concurrency test that proves one
  assessment ID, one engine execution, and one output. Added an equivalent live
  PostgreSQL test; it skipped locally and is not counted as a successful live
  database run.
- Removed the global Pydantic `ValidationError` mapping. Raw injected test
  identity is validated inside its dependency boundary and only that custom
  boundary error maps to 422. Internal engine/persistence exceptions map to a
  safe RFC 9457 500 response without exposing exception details.
- Focused suite: `30 passed, 2 skipped`.
- Full regression: `94 passed, 19 skipped`.
- Ruff and mypy: clean.
