from __future__ import annotations

from decimal import Decimal

from thinc_v5.domain.common import MissingnessStatus
from thinc_v5.domain.decisions import (
    Decision,
    GateContext,
    GateName,
    GateResult,
)


def evaluate_gates(context: GateContext) -> tuple[GateResult, ...]:
    return tuple(_evaluate_gate(context, gate_name) for gate_name in GateName)


def _evaluate_gate(context: GateContext, gate_name: GateName) -> GateResult:
    if gate_name is GateName.COMPLIANCE:
        passed, reason = _evaluate_compliance_gate(context)
    elif gate_name is GateName.LIQUIDITY:
        passed = context.liquidity_passed
        reason = (
            "Liquidity safeguards passed."
            if passed
            else "Liquidity safeguards are not yet satisfied."
        )
    elif gate_name is GateName.DELIVERED_PROFIT:
        passed, reason = _evaluate_delivered_profit_gate(context)
    elif gate_name is GateName.DATA_QUALITY:
        passed = context.data_quality_passed
        reason = (
            "Data quality gate passed."
            if passed
            else "Data quality evidence is incomplete or below threshold."
        )
    elif gate_name is GateName.SAMPLE_SIZE:
        passed = context.sample_size_passed
        reason = (
            "Sample size gate passed."
            if passed
            else "Sample size evidence is incomplete or below threshold."
        )
    elif gate_name is GateName.OPERATIONAL_RECENCY:
        passed = context.operational_recency_passed
        reason = (
            "Operational recency gate passed."
            if passed
            else "Operational recency evidence is stale or unavailable."
        )
    else:
        passed, reason = _evaluate_human_approval_gate(context)

    return GateResult(
        name=gate_name,
        passed=passed,
        blocks_decision=_gate_blocks_decision(context.requested_decision, gate_name),
        reason=reason,
    )


def _evaluate_compliance_gate(context: GateContext) -> tuple[bool, str]:
    if not context.compliance_passed:
        return False, "Compliance review has not passed."
    if context.requested_decision is Decision.TEST and not context.stop_loss_registered:
        return False, "Compliance gate requires a registered stop-loss for TEST."
    return True, "Compliance gate passed."


def _evaluate_delivered_profit_gate(context: GateContext) -> tuple[bool, str]:
    assessment = context.economics_assessment
    delivered_profit = assessment.delivered_contribution_profit

    if delivered_profit is None:
        return False, "Delivered profit is missing because evidence is incomplete."
    if assessment.missingness_status is not MissingnessStatus.COMPLETE:
        return (
            False,
            "Delivered profit is incomplete because economics evidence is incomplete.",
        )
    if delivered_profit <= Decimal("0"):
        return False, "Delivered profit must be positive to clear this gate."
    return True, "Delivered profit gate passed."


def _evaluate_human_approval_gate(context: GateContext) -> tuple[bool, str]:
    approval = context.human_approval
    if approval is None:
        return False, "Human approval is missing for this assessment."
    if approval.assessment_id != context.assessment_id:
        return False, "Human approval must reference the exact assessment ID."
    return True, "Human approval gate passed."


def _gate_blocks_decision(decision: Decision, gate_name: GateName) -> bool:
    if decision is Decision.SCALE:
        return True
    if decision is Decision.TEST and gate_name is GateName.COMPLIANCE:
        return True
    return False
