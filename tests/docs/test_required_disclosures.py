import re
from pathlib import Path


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_model_card_has_required_research_preview_headings() -> None:
    text = read_text("docs/governance/model-card.md")

    required_headings = (
        r"^## Status$",
        r"^## Intended Use$",
        r"^## Prohibited Use$",
        r"^## Egyptian-Market Scope$",
        r"^## Missing-Data Behavior$",
        r"^## Uncertainty$",
        r"^## Human Approval$",
        r"^## Validation Status$",
        r"^## Subgroup Risks$",
        r"^## Rollback$",
        r"^## Known Limitations$",
    )

    for heading in required_headings:
        assert re.search(heading, text, flags=re.MULTILINE)

    assert "Research Preview" in text
    assert "Validated Release" not in text
    assert "Production authentication is not implemented." in text
    assert (
        "No predictive, causal, or field-tested performance claim is permitted "
        "before temporal and external validation."
    ) in text
    assert (
        "Approval records do not recompute stored economics outputs or stored" in text
    )
    assert (
        "gate results. Production authentication is not implemented, and there is no"
        in text
    )
    assert "`SCALE` endpoint." in text


def test_datasheet_and_pilot_protocol_disclose_governance_constraints() -> None:
    datasheet = read_text("docs/governance/datasheet.md")
    protocol = read_text("docs/governance/pilot-protocol.md")
    delivered_profit_equation = (
        "`collected_revenue - product_cost - ad_spend - shipping - "
        "collection_fees - return_cost - variable_operations_cost`"
    )
    ordered_gates = (
        r"The exact seven gates are:\n\n"
        r"1\. `COMPLIANCE`\n"
        r"2\. `LIQUIDITY`\n"
        r"3\. `DELIVERED_PROFIT`\n"
        r"4\. `DATA_QUALITY`\n"
        r"5\. `SAMPLE_SIZE`\n"
        r"6\. `OPERATIONAL_RECENCY`\n"
        r"7\. `HUMAN_APPROVAL`"
    )
    mapped_windows = (
        r"- Intermediate outcomes at 30 days: early operational recency, approval\n"
        r"  latency, evidence completeness, and stop-loss triggers\.\n"
        r"- Primary delivered contribution outcomes at 60 days: delivered "
        r"contribution\n"
        r"  profit and profit per delivered order\.\n"
        r"- Intermediate outcomes at 90 days: persistence of delivered contribution,\n"
        r"  operational stability, and evidence quality\.\n"
        r"- Primary delivered contribution outcomes at 180 days: delivered "
        r"contribution\n"
        r"  profit, profit per delivered order, and cash recovery behavior\.\n"
        r"- Follow-up outcomes at 365 days: persistence, retention, repeat "
        r"purchase, and\n"
        r"  medium-term operational durability\."
    )

    assert re.search(r"^## Delivered Profit Equation$", datasheet, flags=re.MULTILINE)
    assert re.search(r"^## Decision Gates$", datasheet, flags=re.MULTILINE)
    assert re.search(r"^## Data Lineage Fields$", datasheet, flags=re.MULTILINE)
    assert re.search(
        r"^## Outcomes For Future Validation$", datasheet, flags=re.MULTILINE
    )
    assert re.search(
        r"^## Scientific Methodology For Later Releases$",
        datasheet,
        flags=re.MULTILINE,
    )
    assert delivered_profit_equation in datasheet
    assert re.search(ordered_gates, datasheet)
    for field_name in (
        "schema_version",
        "model_version",
        "engine_commit",
        "generated_at",
        "evidence_as_of",
        "market",
        "data_quality_status",
        "missingness_status",
        "uncertainty",
        "source_ids",
        "review_status",
        "decision_reasons",
    ):
        assert field_name in datasheet
    assert re.search(mapped_windows, datasheet)
    for phrase in (
        "Baseline comparison against manual review and simpler rule baselines.",
        "Group-aware and time-aware train, validation, and holdout splits.",
        "including Brier score.",
        "PR-AUC and ROC-AUC",
        "Decision-curve analysis",
    ):
        assert phrase in datasheet

    for heading in (
        r"^## Preregistration$",
        r"^## Consent$",
        r"^## Withdrawal$",
        r"^## Stop-Loss$",
        r"^## Deviations Log$",
        r"^## Legal and Privacy Review$",
    ):
        assert re.search(heading, protocol, flags=re.MULTILINE)

    assert "No student data collection starts before legal and privacy review." in (
        protocol
    )


def test_release_checklist_and_readme_disclose_known_blockers() -> None:
    release_checklist = read_text("docs/governance/release-checklist.md")
    readme = read_text("README.md")
    startup_command = (
        ".\\.venv\\Scripts\\python.exe -m uvicorn "
        "thinc_v5.api.devserver:create_dev_app --factory --host 127.0.0.1 "
        "--port 8000"
    )
    credential_pattern_prefix = (
        "$pattern = "
        "'(?i)\\b(?:api[_-]?key|client[_-]?secret|secret(?:[_-]?key)?|"
        "access[_-]?token|refresh[_-]?token|password)\\b"
    )
    exact_status_lines = (
        "Credential scan current status: PASSED "
        "(literal-secret scan returned no matches on 2026-08-25).",
        "Coverage current status: PASSED (90.13% on 2026-08-25 local full suite).",
        "Bandit current status: PASSED "
        "(0 issues, 0 skipped on 2026-08-25 local Python 3.14.4 scan).",
        "pip-audit current status: PASSED "
        "(No known vulnerabilities found on 2026-08-25; local package "
        "`thinc-v5` was skipped because it is not published on PyPI).",
        "Live PostgreSQL verification status: PENDING.",
        "Python 3.12 CI verification status: PENDING.",
        "Production authentication status: ABSENT.",
        "Python 3.12 full CI verification remains pending:",
        "Live PostgreSQL verification remains pending, including live "
        "PostgreSQL tests.",
        "Production authentication remains absent.",
    )

    assert re.search(r"^## Release Blockers$", release_checklist, flags=re.MULTILINE)
    assert re.search(
        r"^## Current Verification Status$",
        release_checklist,
        flags=re.MULTILINE,
    )
    assert "## Safe Startup" in readme
    assert "Synthetic-only startup" in readme
    assert "Production authentication is not implemented." in readme
    assert 'THINC_ENABLE_INSECURE_TEST_IDENTITY = "true"' in readme
    assert startup_command in readme
    assert "HeaderTestIdentityProvider" in readme
    assert "There is no `SCALE` endpoint." in readme
    assert credential_pattern_prefix in readme
    assert "git grep -nP -- \"$pattern\" -- . ':(exclude).env.example'" in readme
    assert "Synthetic test data cannot establish scientific performance." in readme
    assert (
        "Approval records do not recompute or mutate stored economics outputs or stored"
        in readme
    )
    assert "gate results. There is no `SCALE` endpoint." in readme
    for status_line in exact_status_lines:
        assert status_line in release_checklist
