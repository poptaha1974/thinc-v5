from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError

from thinc_v5.domain.common import (
    DataQualityStatus,
    MissingnessStatus,
    Provenance,
    ResearchPreviewResult,
    ReviewStatus,
    Uncertainty,
)


def test_missingness_status_marks_not_collected_distinctly() -> None:
    zero = "0"

    assert MissingnessStatus.NOT_COLLECTED.value == "NOT_COLLECTED"
    assert MissingnessStatus.NOT_COLLECTED.value != zero


def test_status_enums_expose_frozen_contract_values() -> None:
    assert [status.value for status in MissingnessStatus] == [
        "NOT_COLLECTED",
        "PARTIAL",
        "COMPLETE",
    ]
    assert [status.value for status in DataQualityStatus] == [
        "POOR",
        "ACCEPTABLE",
        "GOOD",
    ]
    assert [status.value for status in ReviewStatus] == [
        "PENDING",
        "APPROVED",
        "REJECTED",
    ]


def test_provenance_requires_source_ids() -> None:
    try:
        Provenance(
            schema_version="1.0.0",
            model_version="research-preview.1",
            engine_commit="abc1234",
            generated_at=datetime.now(UTC),
            evidence_as_of=datetime.now(UTC),
            market="EG",
            source_ids=[],
        )
    except ValidationError as exc:
        assert "source_ids" in str(exc)
    else:
        raise AssertionError("source_ids must not be empty")


def test_provenance_requires_timezone_aware_dates_semver_and_eg_market() -> None:
    try:
        Provenance.model_validate(
            {
                "schema_version": "1",
                "model_version": "research-preview.1",
                "engine_commit": "abc1234",
                "generated_at": datetime(2026, 8, 25, 10, 0, 0),
                "evidence_as_of": datetime.now(UTC),
                "market": "US",
                "source_ids": ["source-1"],
            }
        )
    except ValidationError as exc:
        message = str(exc)
        assert "schema_version" in message
        assert "generated_at" in message
        assert "market" in message
    else:
        raise AssertionError("invalid provenance inputs must be rejected")


def test_uncertainty_defaults_notes_and_supports_bounds() -> None:
    uncertainty = Uncertainty(
        method="credible_interval",
        lower=Decimal("1.25"),
        upper=Decimal("2.50"),
    )

    assert uncertainty.method == "credible_interval"
    assert uncertainty.lower == Decimal("1.25")
    assert uncertainty.upper == Decimal("2.50")
    assert uncertainty.notes == []


def test_research_preview_result_wraps_payload_and_contract_metadata() -> None:
    result = ResearchPreviewResult[dict[str, str]](
        data={"symbol": "EGX30"},
        missingness_status=MissingnessStatus.COMPLETE,
        data_quality_status=DataQualityStatus.GOOD,
        review_status=ReviewStatus.PENDING,
        uncertainty=Uncertainty(
            method="range",
            lower=Decimal("10.0"),
            upper=Decimal("12.0"),
            notes=["Estimated from incomplete inputs"],
        ),
        provenance=Provenance(
            schema_version="1.0.0",
            model_version="research-preview.1",
            engine_commit="abc1234",
            generated_at=datetime.now(UTC),
            evidence_as_of=datetime.now(UTC),
            market="EG",
            source_ids=["source-1"],
        ),
    )

    dumped = result.model_dump(mode="json")

    data = dumped["data"]
    uncertainty = dumped["uncertainty"]
    provenance = dumped["provenance"]

    assert data == {"symbol": "EGX30"}
    assert dumped["missingness_status"] == "COMPLETE"
    assert dumped["data_quality_status"] == "GOOD"
    assert dumped["review_status"] == "PENDING"
    assert isinstance(uncertainty, dict)
    assert uncertainty["notes"] == ["Estimated from incomplete inputs"]
    assert isinstance(provenance, dict)
    assert provenance["schema_version"] == "1.0.0"
