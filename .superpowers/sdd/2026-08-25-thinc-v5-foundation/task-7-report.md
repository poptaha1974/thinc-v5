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
- Full repo formatting required a mechanical follow-up on tracked Python files.
- The original broad credential grep produced false positives, so a refined
  literal-secret scan was added and run in the follow-up.

## Round 1 Follow-Up

### Additional implementation

- Added `src/thinc_v5/api/devserver.py` with a fail-closed local factory.
- The only supported local startup identity dependency is
  `HeaderTestIdentityProvider`.
- Added `tests/unit/api/test_devserver.py`.
- Tightened `tests/docs/test_required_disclosures.py` to check exact headings,
  the exact delivered-profit equation, all seven gates, time windows, split and
  baseline language, metric language, startup command, warning language, and
  release blockers.
- Updated security coverage so approvals are verified not to recompute stored
  gate results, and so absence of a `SCALE` endpoint is explicit.
- Updated README, model card, datasheet, and release checklist accordingly.

### Startup evidence

- Fail-closed startup check:
  `.\.venv\Scripts\python.exe -m uvicorn thinc_v5.api.devserver:create_dev_app --factory --host 127.0.0.1 --port 8000`
  -> failed with `InsecureTestIdentityDisabledError` until
  `THINC_ENABLE_INSECURE_TEST_IDENTITY=true` was set.
- Enabled startup check:
  `$env:THINC_ENABLE_INSECURE_TEST_IDENTITY='true'; .\.venv\Scripts\python.exe -m uvicorn thinc_v5.api.devserver:create_dev_app --factory --host 127.0.0.1 --port 8000`
  -> started successfully and listened on `http://127.0.0.1:8000`.

### Verification evidence after follow-up

- `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_devserver.py -v`
  -> passed (`3 passed`).
- `.\.venv\Scripts\python.exe -m pytest tests/docs/test_required_disclosures.py -v`
  -> passed (`3 passed`).
- `.\.venv\Scripts\python.exe -m pytest tests/security/test_high_impact_actions.py -v`
  -> passed (`10 passed`).
- `.\.venv\Scripts\python.exe -m pytest tests/contract/test_assessment_api_openapi.py -v`
  -> passed (`2 passed`).
- Combined focused suite:
  `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_devserver.py tests/docs/test_required_disclosures.py tests/security/test_high_impact_actions.py tests/contract/test_assessment_api_openapi.py -v`
  -> passed (`18 passed`).
- `.\.venv\Scripts\python.exe -m ruff format` on tracked Python files
  -> reformatted 9 files.
- `.\.venv\Scripts\python.exe -m ruff check .`
  -> passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`
  -> passed.
- `.\.venv\Scripts\python.exe -m mypy src`
  -> passed (`Success: no issues found in 21 source files`).
- Refined credential scan:
  `git grep -nP "(?i)\b(?:api[_-]?key|client[_-]?secret|secret(?:[_-]?key)?|access[_-]?token|refresh[_-]?token|password)\b\s*[:=]\s*(?:\"[^\"]+\"|'[^']+'|[^\s$<][^\r\n#;]*)" -- . ':(exclude).env.example'`
  -> returned no matches.

### Verification that still does not pass cleanly

- `.\.venv\Scripts\python.exe -m pip install -e .[dev]`
  -> failed because project metadata requires Python `<3.13`, while the active
  environment is Python `3.14.4`.
- `.\.venv\Scripts\python.exe -m pytest --cov=thinc_v5 --cov-fail-under=90`
  -> ran successfully but failed the threshold gate: `107 passed, 23 skipped`,
  total coverage `84.50%`, below the required `90%`.
- `.\.venv\Scripts\python.exe -m bandit -r src`
  -> still exits with internal scanner errors on Python 3.14 and skips 20
  source files.
- `.\.venv\Scripts\python.exe -m pip_audit`
  -> reports 6 known vulnerabilities in `starlette 0.47.3`.

### Updated blockers

- Python 3.12 full CI remains a blocker.
- Live PostgreSQL verification remains a blocker.
- Coverage remains below the required threshold in the current run.
- Bandit remains unreliable on Python 3.14 in this environment.
- `pip-audit` is currently failing because of `starlette` vulnerabilities in the
  installed environment.
