# Task 7 Report

Date: 2026-08-25
Branch: `feature/thinc-v5-foundation`
Scope: governance docs, README, docs tests, and small deferred items allowed by
the brief.

## Status

- Implemented a Research Preview governance packet:
  - `README.md`
  - `docs/governance/model-card.md`
  - `docs/governance/datasheet.md`
  - `docs/governance/pilot-protocol.md`
  - `docs/governance/release-checklist.md`
- Added executable disclosure coverage in
  `tests/docs/test_required_disclosures.py`.
- Added the direct negative `delivered_orders` test in
  `tests/unit/engines/test_economics.py`.
- Added `.hypothesis/` to `.gitignore`.

## Required Disclosures Reflected

- Product posture stays `Research Preview`.
- README was created because the branch had no `README.md`.
- Startup is documented as synthetic-only.
- Production authentication is explicitly absent.
- Live PostgreSQL verification was not run locally.
- No validated, field-tested, causal, or predictive claim is made.
- The exact seven gates and the delivered-profit equation are documented.
- Follow-up phases, scientific methodology, pilot consent, withdrawal, and
  legal/privacy review are documented.

## Verification Evidence

Initial required failure:

- `.\.venv\Scripts\python.exe -m pytest tests/docs/test_required_disclosures.py -v`
  failed before the docs existed with `FileNotFoundError` for the governance
  files.

Focused passes after implementation:

- `.\.venv\Scripts\python.exe -m pytest tests/docs/test_required_disclosures.py -v`
  -> passed (`3 passed`).
- `.\.venv\Scripts\python.exe -m pytest tests/unit/engines/test_economics.py -v`
  -> passed (`5 passed`).
- `.\.venv\Scripts\python.exe -m ruff check .`
  -> passed, with a `.ruff_cache` access warning.
- `.\.venv\Scripts\python.exe -m pip_audit`
  -> passed (`No known vulnerabilities found`).

Verification that did not pass cleanly in this environment:

- `.\.venv\Scripts\python.exe -m ruff format --check .`
  -> failed because 8 existing repository files would be reformatted:
  `alembic/versions/0003_engine_output_records.py`,
  `src/thinc_v5/db/models.py`,
  `src/thinc_v5/decision/service.py`,
  `tests/contract/test_assessment_api_openapi.py`,
  `tests/integration/api/test_assessments.py`,
  `tests/integration/db/test_tenant_isolation.py`,
  `tests/security/test_high_impact_actions.py`,
  `tests/unit/decision/test_service_repository.py`.
- `.\.venv\Scripts\python.exe -m mypy src`
  -> failed because the current `.venv` lacks `fastapi` / `starlette` imports
  and reported 15 errors.
- `.\.venv\Scripts\python.exe -m pytest --cov=thinc_v5 --cov-fail-under=90`
  -> failed during collection with `ModuleNotFoundError: No module named 'fastapi'`.
- `.\.venv\Scripts\python.exe -m bandit -r src`
  -> exited 0 but skipped 19 files after internal scanner errors tied to the
  current Python 3.14 environment (`ast.Num` no longer present).

Manual / static checks:

- `git grep -nE '(api[_-]?key|token|secret|password)\s*[:=]\s*[^$<]'`
  returned matches for internal names such as `owner_token`,
  `hide_password=False`, and test fixtures. It did not produce a clean zero-hit
  result.
- Static route / contract inspection still shows only:
  - `/v1/assessments`
  - `/v1/assessments/{assessment_id}`
  - `/v1/assessments/{assessment_id}/approvals`

## Concerns And Release Blockers

- The checked-in project targets Python `>=3.12,<3.13`, but the current local
  `.venv` used for verification is Python `3.14.4`.
- Python 3.12 CI verification remains a release blocker.
- Live PostgreSQL verification remains a release blocker.
- Production authentication remains unimplemented by design in Foundation.
- Full repo formatting is not clean before this docs-only task.
- The exact credential grep requested does not return a clean empty result.
