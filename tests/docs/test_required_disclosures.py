from pathlib import Path


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_model_card_has_required_research_preview_headings() -> None:
    text = read_text("docs/governance/model-card.md")

    required_headings = (
        "## Status",
        "## Intended Use",
        "## Prohibited Use",
        "## Egyptian-Market Scope",
        "## Missing-Data Behavior",
        "## Uncertainty",
        "## Human Approval",
        "## Validation Status",
        "## Subgroup Risks",
        "## Rollback",
        "## Known Limitations",
    )

    for heading in required_headings:
        assert heading in text

    assert "Research Preview" in text
    assert "Validated Release" not in text
    assert "Production authentication is not implemented." in text
    assert (
        "No predictive, causal, or field-tested performance claim is permitted "
        "before temporal and external validation."
    ) in text


def test_datasheet_and_pilot_protocol_disclose_governance_constraints() -> None:
    datasheet = read_text("docs/governance/datasheet.md")
    protocol = read_text("docs/governance/pilot-protocol.md")

    assert "## Data Lineage Fields" in datasheet
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

    for heading in (
        "## Preregistration",
        "## Consent",
        "## Withdrawal",
        "## Stop-Loss",
        "## Deviations Log",
        "## Legal and Privacy Review",
    ):
        assert heading in protocol

    assert "No student data collection starts before legal and privacy review." in (
        protocol
    )


def test_release_checklist_and_readme_disclose_known_blockers() -> None:
    release_checklist = read_text("docs/governance/release-checklist.md")
    readme = read_text("README.md")

    assert "## Release Blockers" in release_checklist
    assert "Python 3.12 CI verification pending." in release_checklist
    assert "Live PostgreSQL verification pending." in release_checklist
    assert "## Safe Startup" in readme
    assert "Synthetic-only startup" in readme
    assert "Production authentication is not implemented." in readme
    assert "Synthetic test data cannot establish scientific performance." in readme
