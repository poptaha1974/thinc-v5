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

## Fix Round 1

### Requested fixes

- Added required `decision_reasons` to the common `ResearchPreviewResult[T]` envelope.
- Strengthened `Provenance.source_ids` so schema now expresses:
  - `minItems: 1`
  - non-empty / non-blank string items
- Strengthened contract tests so they explicitly fail if:
  - `decision_reasons` disappears
  - `decision_reasons` stops being required
  - `source_ids` loses `minItems`
  - `source_ids` items lose non-empty string constraints
- Made `Uncertainty.method` and `Uncertainty.notes[]` expose non-empty / non-blank constraints in schema.

### Red

Expanded tests first in:

- `tests/unit/domain/test_common.py`
- `tests/contract/test_assessment_schema.py`

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\domain\test_common.py tests\contract\test_assessment_schema.py -v
```

Observed failures:

```text
FAILED tests/unit/domain/test_common.py::test_research_preview_result_requires_decision_reasons
FAILED tests/unit/domain/test_common.py::test_research_preview_result_wraps_payload_and_contract_metadata
FAILED tests/contract/test_assessment_schema.py::test_assessment_schema_matches_committed_contract
```

Key failure signals:

- `decision_reasons must be required`
- `KeyError: 'decision_reasons'`
- schema missing `decision_reasons`

### Green

Updated `src/thinc_v5/domain/common.py` to move these constraints into the model types themselves using schema-visible string constraints and list cardinality.

Updated frozen contract:

- `docs/contracts/assessment-v1.json`

Focused verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\domain\test_common.py tests\contract\test_assessment_schema.py -v
```

Output:

```text
============================= 10 passed in 0.41s ==============================
```

### Static verification

Command:

```powershell
.\.venv\Scripts\python.exe -m ruff check src\thinc_v5\domain tests\unit\domain tests\contract
```

Output:

```text
All checks passed!
```

Command:

```powershell
.\.venv\Scripts\python.exe -m mypy src\thinc_v5\domain tests\unit\domain tests\contract
```

Output:

```text
Success: no issues found in 4 source files
```

### Regression check

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Output:

```text
============================= 12 passed in 0.40s ==============================
```
