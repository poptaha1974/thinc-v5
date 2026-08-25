# THINC v5 Foundation final-fix report

Date: 2026-08-25
Implementation commit: `4aa21b4` (`fix: close foundation persistence and tenant gaps`)

## Outcome

- Migration `0004` now locks both assessment and engine-output tables, temporarily
  disables forced RLS for the migration owner, backfills leases/reconciles
  outputs with full row visibility, and restores forced RLS before completing.
  PostgreSQL transactional DDL restores the prior forced-RLS state if the
  migration aborts; the live conflict fixture asserts that state after rollback.
- The live `0003 -> head -> 0003` fixture now seeds a pending assessment, one
  valid output, and one orphan output. It asserts that the valid output remains,
  only the orphan is quarantined, and the lease survives upgrade/downgrade.
- Every live test row read/write/delete in the touched tenant-scoped paths now
  establishes transaction-local tenant context. Tenant fixture inserts do too.
- Migration `0005` adds forced self-tenant RLS to `tenants`. `thinc_app` has only
  SELECT on the current tenant row. A separate table-owner policy preserves
  explicit provisioning while forced RLS is active. Runtime bootstrap is
  documented to use the tenant UUID supplied by identity, never a global slug
  lookup through the app role.
- Assessment completion now writes the economics evidence record, requested and
  safe recommended decision with all gate reasons, and actor audit event in the
  same transaction as the `COMPLETED` state. Approval and its actor audit event
  are also one atomic write. In-memory and SQL repository contracts implement
  the same behavior. Failure tests assert no completed assessment without the
  governance records.
- Evidence stores validated raw/normalized representations, SHA-256 hashes, and
  source provenance. Unknown request fields are not retained. Audit payloads
  contain entity identifiers rather than the economics body.
- Assessment and engine-output hashes are verified on load and mismatches fail
  closed.
- `ApprovalInput.approved_at` uses Pydantic `AwareDatetime`; a naive RFC 3339
  value returns HTTP 422 as `application/problem+json`.
- The secret scanner detects literal `PASSWORD`, `SECRET`, `TOKEN`, and
  `API_KEY` environment assignments plus URI credentials, has behavior tests,
  and runs in CI. CI also has `contents: read`, `pip check`, and commit-pinned
  checkout/setup-python actions.
- README explicitly identifies the devserver as an in-memory, nonpersistent,
  non-SQL path. Governance documents reflect the implemented persistence and
  tenant boundaries. The API remains Research Preview and exposes no
  high-impact execution endpoint.

## Verification evidence

Baseline before fixes:

```text
.\.venv\Scripts\python.exe -m pytest -q
130 passed, 23 skipped, 1 warning
```

Final format, lint, and typing:

```text
.\.venv\Scripts\python.exe -m ruff format --check .
56 files already formatted

.\.venv\Scripts\python.exe -m ruff check .
All checks passed!

.\.venv\Scripts\python.exe -m mypy src
Success: no issues found in 21 source files
```

Final test and coverage gate:

```text
.\.venv\Scripts\python.exe -m pytest --cov=thinc_v5 --cov-report=term --cov-fail-under=90 -q
142 passed, 25 skipped, 1 warning
Total coverage: 90.68%
```

Security and dependency checks:

```text
.\.venv\Scripts\python.exe -m bandit -r src
No issues identified; 0 skipped

.\.venv\Scripts\python.exe -m pip_audit
No known vulnerabilities found
thinc-v5 skipped because the local package is not published on PyPI

.\.venv\Scripts\python.exe scripts\secret_scan.py
Secret scan passed: no literal credentials detected.
```

`pip check` was run and did not pass in the available non-target environment:

```text
thinc-v5 requires pydantic~=2.12.0, but the local Python 3.14 environment has
pydantic 2.13.4. Several installed wheels are also marked unsupported on
Python 3.14.
```

`py -3.12 --version` confirmed that Python 3.12 is not installed locally. CI
now runs `pip check` after installing the project under Python 3.12.

## Live PostgreSQL status

Live PostgreSQL verification was **not run locally**. No local LivePG success is
claimed. The final full suite skipped 25 tests because
`THINC_TEST_DATABASE_URL` and `THINC_TEST_APP_DATABASE_URL` were absent:

- 5 PostgreSQL API persistence/concurrency/fencing/rollback tests;
- 7 audit privilege/immutability tests;
- 6 role-provisioning rejection tests;
- 1 pooled tenant-context reset test;
- 6 migration/RLS/isolation tests.

The skipped suite includes the new valid-plus-orphan `0004` fixture, rollback
forced-RLS assertion, tenant metadata self-isolation, atomic SQL governance
write/approval assertions, and SQL rollback-on-audit-failure assertion. These
must run in the pinned PostgreSQL 16 CI service before release.

## Remaining release concerns

- Python 3.12 CI, including `pip check` and all 25 LivePG tests, remains the
  release gate.
- The known Starlette/httpx deprecation warning remains in the local Python 3.14
  environment.
- Production authentication and temporal/external scientific validation remain
  absent by Foundation design; status remains Research Preview.
