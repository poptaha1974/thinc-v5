# THINC v5 Foundation

THINC v5 Foundation is a synthetic-only Research Preview for evaluating
delivered contribution economics and decision gates in the Egyptian market
(`EG`). It exposes assessment and approval APIs, but it does not execute
budgets, campaigns, publishing, or scaling actions.

## Safe Startup

Synthetic-only startup

- Project target runtime: Python 3.12.
- Production authentication is not implemented.
- Synthetic test data cannot establish scientific performance.
- Live PostgreSQL verification has not been run locally for this release packet.

### 1. Create a Python 3.12 environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

If `.venv` was created with another Python version, remove it and recreate it
with Python 3.12 before release verification.

### 2. Configure local environment variables

```powershell
Copy-Item .env.example .env
```

`.env.example` contains synthetic local credentials only. Review the
`THINC_*DATABASE_URL` values before connecting to any database.

### 3. Start local PostgreSQL

```powershell
docker compose up -d postgres
docker compose ps
```

The compose stack starts PostgreSQL 16 and seeds local roles from
`docker/postgres/init`.

### 4. Run database migrations

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Use `THINC_MIGRATION_DATABASE_URL` for non-test Alembic commands. Keep test and
non-test URLs separate.

### 5. Run the test and quality commands

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest --cov=thinc_v5 --cov-fail-under=90
.\.venv\Scripts\python.exe -m bandit -r src
.\.venv\Scripts\python.exe -m pip_audit
```

The research-preview docs test is:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/docs/test_required_disclosures.py -v
```

### 6. Start the API

This application factory requires an injected repository and a test identity
provider. Production deployment wiring is intentionally absent.

```powershell
.\.venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; print('Use create_app(...) from thinc_v5.api.app with explicit repository and test identity injection.')"
```

Available paths in this Foundation release:

- `POST /v1/assessments`
- `GET /v1/assessments/{assessment_id}`
- `POST /v1/assessments/{assessment_id}/approvals`

## Research Preview Guardrails

- Scope is `EG` only. No cross-market calibration or transfer claim is allowed.
- Missing evidence remains `NOT_COLLECTED` or `PARTIAL`; it is never coerced to
  zero.
- Every assessment stays in `Research Preview` status until temporal and
  external validation are complete.
- No predictive, causal, validated, or field-tested claim is supported by
  synthetic startup data.
