# Task 3 Report

## Status
- Implemented the delivered contribution economics engine and its domain contract.
- Added focused unit tests and Hypothesis property tests before implementation, then drove the implementation to green.

## Files Changed
- `pyproject.toml`
- `src/thinc_v5/domain/economics.py`
- `src/thinc_v5/domain/engines.py`
- `src/thinc_v5/engines/__init__.py`
- `src/thinc_v5/engines/economics.py`
- `tests/unit/engines/test_economics.py`
- `tests/property/test_economics_properties.py`

## TDD Evidence
1. Wrote focused unit and property tests for:
   - delivered contribution profit formula
   - missing financial inputs staying `None` with per-field reasons
   - zero delivered orders yielding `None` per-order profit with a reason
   - negative financial input rejection
   - monotonic cost and exact-profit invariants
   - Decimal serialization round-trip
2. Ran the focused suite before implementation and observed failure because `thinc_v5.domain.economics` and `thinc_v5.engines.economics` did not exist.
3. Implemented the minimum domain models and engine behavior needed to satisfy the tests.
4. Re-ran focused and broader verification until green.

## Verification
- `pytest tests/unit/engines/test_economics.py tests/property/test_economics_properties.py -v` -> 7 passed
- `ruff check src tests` -> passed
- `pytest -v` -> 19 passed

## Concerns
- The machine only had Python `3.14` available, while the project declares `>=3.12,<3.13`. To run verification locally, I used a task-local `.venv` and had to install a newer local `pydantic` wheel that supports Python `3.14`; the repository dependency constraints were not changed beyond adding `hypothesis` to dev dependencies.
- `mypy` did not return in a reasonable time on this environment, so the final verification evidence is `pytest` plus `ruff`, not a completed `mypy` run.
