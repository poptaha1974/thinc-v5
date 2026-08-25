# Task 2 Report: Provenance, Missingness, and Uncertainty Contracts

## Scope and decisions

- Implemented a stable common result envelope only, per the task note that API-specific snapshotting belongs to Task 6.
- Added `MissingnessStatus`, `DataQualityStatus`, and `ReviewStatus` as frozen string enums with the exact brief values.
- Added `Uncertainty` with `method`, optional decimal bounds, and default-empty `notes`.
- Added `Provenance` with validators for:
  - non-empty `source_ids`
  - timezone-aware `generated_at` and `evidence_as_of`
  - `market == "EG"`
  - semantic `schema_version` matching `x.y.z`
- Added `ResearchPreviewResult[T]` as the common envelope with:
  - `data`
  - `missingness_status`
  - `data_quality_status`
  - `review_status`
  - `uncertainty`
  - `provenance`
- Froze the generated schema in `docs/contracts/assessment-v1.json` and added a contract test that compares exact JSON schema equality.

## TDD log

### Red

Added failing tests first in:

- `tests/unit/domain/test_common.py`
- `tests/contract/test_assessment_schema.py`

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\domain\test_common.py -v
```

Observed failure:

```text
E   ModuleNotFoundError: No module named 'thinc_v5.domain'
```

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\contract\test_assessment_schema.py -v
```

Observed failure:

```text
E       AssertionError: assert {'$defs': ...} == {}
```

### Green

Implemented:

- `src/thinc_v5/domain/common.py`
- `src/thinc_v5/domain/__init__.py`

Generated and committed the frozen schema at:

- `docs/contracts/assessment-v1.json`

Focused verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\domain\test_common.py tests\contract\test_assessment_schema.py -v
```

Output:

```text
============================== 7 passed in 1.11s ==============================
```

### Refactor / hardening

- Switched `ResearchPreviewResult` to Python 3.12 type-parameter syntax for Ruff compliance.
- Tightened tests so they remain valid under `mypy --strict`.
- Kept the common envelope minimal to avoid leaking future API-specific shape into the frozen contract.

## Final verification

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Output:

```text
============================== 9 passed in 0.52s ==============================
```

Command:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

Output:

```text
All checks passed!
```

Command:

```powershell
.\.venv\Scripts\python.exe -m mypy src tests
```

Output:

```text
Success: no issues found in 7 source files
```

## Files added or changed

- `src/thinc_v5/domain/__init__.py`
- `src/thinc_v5/domain/common.py`
- `tests/unit/domain/test_common.py`
- `tests/contract/test_assessment_schema.py`
- `docs/contracts/assessment-v1.json`
