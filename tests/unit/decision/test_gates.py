from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from thinc_v5.decision.gates import evaluate_gates
from thinc_v5.domain.common import MissingnessStatus, Provenance, Uncertainty
from thinc_v5.domain.decisions import (
    Decision,
    GateContext,
    GateName,
    GateReasonCode,
    HumanApproval,
)
from thinc_v5.domain.economics import EconomicsAssessment


def build_provenance() -> Provenance:
    return Provenance(
        schema_version="1.0.0",
        model_version="economics-engine.1",
        engine_commit="abc1234",
        generated_at=datetime.now(UTC),
        evidence_as_of=datetime.now(UTC),
        market="EG",
        source_ids=["source-1"],
    )


def build_assessment(
    *,
    delivered_profit: Decimal | None = Decimal("125"),
    missingness_status: MissingnessStatus = MissingnessStatus.COMPLETE,
) -> EconomicsAssessment:
    return EconomicsAssessment(
        delivered_contribution_profit=delivered_profit,
        profit_per_delivered_order=Decimal("12.5")
        if delivered_profit is not None
        else None,
        decision_reasons=["Economics inputs were evaluated."],
        missingness_status=missingness_status,
        uncertainty=Uncertainty(method="deterministic"),
        provenance=build_provenance(),
    )


def find_gate(results: tuple[object, ...], gate_name: GateName):
    return next(result for result in results if result.name is gate_name)


def build_scale_context(**overrides: object) -> GateContext:
    context_data: dict[str, object] = {
        "requested_decision": Decision.SCALE,
        "assessment_id": "assess-1",
        "economics_assessment": build_assessment(),
        "compliance_passed": True,
        "liquidity_passed": True,
        "data_quality_passed": True,
        "sample_size_passed": True,
        "operational_recency_passed": True,
        "stop_loss_registered": True,
        "human_approval": HumanApproval(
            approver_id="approver-1",
            approved_at=datetime.now(UTC),
            assessment_id="assess-1",
        ),
    }
    context_data.update(overrides)
    return GateContext(**context_data)


def test_scale_is_blocked_by_negative_delivered_profit() -> None:
    context = build_scale_context(
        economics_assessment=build_assessment(delivered_profit=Decimal("-1")),
    )

    results = evaluate_gates(context)

    delivered_profit_gate = find_gate(results, GateName.DELIVERED_PROFIT)

    assert delivered_profit_gate.passed is False
    assert delivered_profit_gate.blocks_decision is True
    assert all(
        result.override_allowed is False for result in results if not result.passed
    )


def test_scale_requires_human_approval_for_exact_assessment_id() -> None:
    context = build_scale_context(
        assessment_id="assess-expected",
        human_approval=HumanApproval(
            approver_id="approver-1",
            approved_at=datetime.now(UTC),
            assessment_id="assess-other",
        ),
    )

    results = evaluate_gates(context)

    approval_gate = find_gate(results, GateName.HUMAN_APPROVAL)

    assert approval_gate.passed is False
    assert approval_gate.blocks_decision is True
    assert "exact assessment" in approval_gate.reason.lower()


@pytest.mark.parametrize(
    ("gate_name", "context_kwargs"),
    [
        (GateName.COMPLIANCE, {"compliance_passed": False}),
        (GateName.LIQUIDITY, {"liquidity_passed": False}),
        (
            GateName.DELIVERED_PROFIT,
            {"economics_assessment": build_assessment(delivered_profit=Decimal("-1"))},
        ),
        (GateName.DATA_QUALITY, {"data_quality_passed": False}),
        (GateName.SAMPLE_SIZE, {"sample_size_passed": False}),
        (
            GateName.OPERATIONAL_RECENCY,
            {"operational_recency_passed": False},
        ),
        (GateName.HUMAN_APPROVAL, {"human_approval": None}),
    ],
)
def test_scale_blocks_each_failed_gate_independently(
    gate_name: GateName,
    context_kwargs: dict[str, object],
) -> None:
    results = evaluate_gates(build_scale_context(**context_kwargs))

    targeted_gate = find_gate(results, gate_name)

    assert targeted_gate.passed is False
    assert targeted_gate.blocks_decision is True
    assert targeted_gate.override_allowed is False


@pytest.mark.parametrize(
    ("context_kwargs", "expected_reason_code"),
    [
        (
            {"compliance_passed": False, "stop_loss_registered": True},
            GateReasonCode.COMPLIANCE_REVIEW_FAILED,
        ),
        (
            {
                "requested_decision": Decision.TEST,
                "compliance_passed": True,
                "stop_loss_registered": False,
            },
            GateReasonCode.STOP_LOSS_NOT_REGISTERED,
        ),
    ],
)
def test_compliance_reason_code_distinguishes_review_failure_from_missing_stop_loss(
    context_kwargs: dict[str, object],
    expected_reason_code: GateReasonCode,
) -> None:
    context_data: dict[str, object] = {
        "requested_decision": Decision.TEST,
        "assessment_id": "assess-1",
        "economics_assessment": build_assessment(),
        "compliance_passed": True,
        "liquidity_passed": True,
        "data_quality_passed": True,
        "sample_size_passed": True,
        "operational_recency_passed": True,
        "stop_loss_registered": True,
        "human_approval": None,
    }
    context_data.update(context_kwargs)

    results = evaluate_gates(GateContext(**context_data))

    compliance_gate = find_gate(results, GateName.COMPLIANCE)

    assert compliance_gate.passed is False
    assert compliance_gate.blocks_decision is True
    assert compliance_gate.reason_code is expected_reason_code


@pytest.mark.parametrize(
    ("decision", "context_kwargs", "gate_name", "expected_blocking"),
    [
        (
            Decision.RESEARCH,
            {
                "economics_assessment": build_assessment(
                    delivered_profit=None,
                    missingness_status=MissingnessStatus.NOT_COLLECTED,
                ),
                "data_quality_passed": False,
                "sample_size_passed": False,
            },
            GateName.DELIVERED_PROFIT,
            False,
        ),
        (
            Decision.TEST,
            {
                "stop_loss_registered": False,
            },
            GateName.COMPLIANCE,
            True,
        ),
        (
            Decision.FIX,
            {
                "economics_assessment": build_assessment(
                    delivered_profit=Decimal("-5")
                ),
            },
            GateName.DELIVERED_PROFIT,
            False,
        ),
        (
            Decision.HOLD,
            {
                "liquidity_passed": False,
            },
            GateName.LIQUIDITY,
            False,
        ),
        (
            Decision.REPOSITION,
            {
                "data_quality_passed": False,
            },
            GateName.DATA_QUALITY,
            False,
        ),
        (
            Decision.SCALE,
            {
                "liquidity_passed": False,
            },
            GateName.LIQUIDITY,
            True,
        ),
        (
            Decision.KILL,
            {
                "operational_recency_passed": False,
            },
            GateName.OPERATIONAL_RECENCY,
            False,
        ),
    ],
)
def test_decision_matrix_marks_blocking_gates_per_decision(
    decision: Decision,
    context_kwargs: dict[str, object],
    gate_name: GateName,
    expected_blocking: bool,
) -> None:
    context_data: dict[str, object] = {
        "requested_decision": decision,
        "assessment_id": "assess-1",
        "economics_assessment": build_assessment(),
        "compliance_passed": True,
        "liquidity_passed": True,
        "data_quality_passed": True,
        "sample_size_passed": True,
        "operational_recency_passed": True,
        "stop_loss_registered": True,
        "human_approval": None,
    }
    context_data.update(context_kwargs)

    results = evaluate_gates(GateContext(**context_data))

    targeted_gate = find_gate(results, gate_name)

    assert len(results) == len(GateName)
    assert targeted_gate.passed is False
    assert targeted_gate.blocks_decision is expected_blocking
    if decision is Decision.RESEARCH:
        assert "missing" in targeted_gate.reason.lower() or "incomplete" in (
            targeted_gate.reason.lower()
        )
    if decision is Decision.TEST:
        assert "stop-loss" in targeted_gate.reason.lower()


def test_gate_api_never_exposes_numeric_engine_score() -> None:
    context = GateContext(
        requested_decision=Decision.RESEARCH,
        assessment_id="assess-1",
        economics_assessment=build_assessment(),
        compliance_passed=True,
        liquidity_passed=False,
        data_quality_passed=False,
        sample_size_passed=False,
        operational_recency_passed=False,
        stop_loss_registered=False,
        human_approval=None,
    )

    results = evaluate_gates(context)

    dumped_results = [result.model_dump() for result in results]

    assert "engine_score" not in GateContext.model_fields
    assert all("engine_score" not in dumped for dumped in dumped_results)
