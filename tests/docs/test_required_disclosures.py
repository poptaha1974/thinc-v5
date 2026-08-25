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
    assert (
        "`collected_revenue - product_cost - ad_spend - shipping - "
        "collection_fees - return_cost - variable_operations_cost`"
    ) in datasheet
    for gate_name in (
        "`COMPLIANCE`",
        "`LIQUIDITY`",
        "`DELIVERED_PROFIT`",
        "`DATA_QUALITY`",
        "`SAMPLE_SIZE`",
        "`OPERATIONAL_RECENCY`",
        "`HUMAN_APPROVAL`",
    ):
        assert gate_name in datasheet
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
    for window_label in (
        "30 days",
        "60 days",
        "90 days",
        "180 days",
        "365 days",
    ):
        assert window_label in datasheet
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

    assert re.search(r"^## Release Blockers$", release_checklist, flags=re.MULTILINE)
    assert "## Safe Startup" in readme
    assert "Synthetic-only startup" in readme
    assert "Production authentication is not implemented." in readme
    assert 'THINC_ENABLE_INSECURE_TEST_IDENTITY = "true"' in readme
    assert (
        ".\\.venv\\Scripts\\python.exe -m uvicorn "
        "thinc_v5.api.devserver:create_dev_app --factory --host 127.0.0.1 "
        "--port 8000"
    ) in readme
    assert "HeaderTestIdentityProvider" in readme
    assert "There is no `SCALE` endpoint." in readme
    assert "Synthetic test data cannot establish scientific performance." in readme
    assert (
        "Approval records do not recompute or mutate stored economics outputs or stored"
        in readme
    )
    assert "gate results. There is no `SCALE` endpoint." in readme
    for blocker in (
        "Python 3.12 full CI verification pending:",
        "`ruff format --check .`, `ruff check .`, `mypy src`,",
        "`pytest --cov=thinc_v5 --cov-fail-under=90`, `bandit -r src`,",
        "and `pip-audit`.",
        "Live PostgreSQL verification pending, including live PostgreSQL tests.",
        "Refined credential scan must pass with no assigned literal secrets.",
        "Production authentication is not implemented.",
    ):
        assert blocker in release_checklist
