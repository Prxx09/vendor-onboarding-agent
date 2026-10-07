from collections.abc import Iterable

from app.rules.config import RulesConfig
from app.schemas.domain import (
    Approval,
    ApprovalDecision,
    ApprovalStage,
    VendorRequest,
)
from app.schemas.findings import Finding, FindingCode
from app.schemas.risk import RiskResult
from app.workflow.states import WorkflowStatus


class ApprovalError(ValueError):
    """A human decision violates deterministic approval policy."""


def required_stages(
    request: VendorRequest,
    risk_result: RiskResult,
    findings: Iterable[Finding],
    config: RulesConfig,
) -> list[ApprovalStage]:
    """Return required human stages in fixed order, independent of numeric risk."""
    # These inputs are part of the stable policy API. Routing is intentionally based on
    # the deterministic HIGH_VALUE_PURCHASE finding, never the risk score or request spend.
    del request, risk_result, config
    codes = {finding.code for finding in findings}
    stages = [ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER]
    if FindingCode.HIGH_VALUE_PURCHASE in codes:
        stages.append(ApprovalStage.FINANCE_HEAD)
    return stages


def validate_decision(
    request: VendorRequest,
    existing_approvals: list[Approval],
    stage: ApprovalStage | str,
    approver_id: str,
    approver_role: str,
    decision: ApprovalDecision | str,
    comment: str,
    *,
    required_stage_list: list[ApprovalStage] | None = None,
) -> None:
    """Validate a submitted human action without mutating request or approval state."""
    try:
        submitted_stage = ApprovalStage(stage)
    except ValueError as exc:
        raise ApprovalError(f"Unknown approval stage: {stage}") from exc
    try:
        submitted_decision = ApprovalDecision(decision)
    except ValueError as exc:
        raise ApprovalError(f"Unknown human decision: {decision}") from exc

    if not approver_id or not approver_id.strip():
        raise ApprovalError("Approver identity must be non-empty.")
    if not comment or not comment.strip():
        raise ApprovalError("A non-empty comment is required for every human decision.")
    if (
        submitted_decision == ApprovalDecision.APPROVE
        and request.requester_id
        and approver_id.strip() == request.requester_id
    ):
        raise ApprovalError("The requester cannot approve their own request.")
    if request.status == WorkflowStatus.BLOCKED.value:
        if submitted_decision == ApprovalDecision.APPROVE:
            raise ApprovalError("A blocked request cannot be approved.")
        approved = {item.stage for item in existing_approvals if item.decision == ApprovalDecision.APPROVE}
        stage_order = required_stage_list or [ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER]
        expected_stage = next((item for item in stage_order if item not in approved), None)
        if expected_stage is None:
            raise ApprovalError("No uncompleted required stage is available to close this blocked request.")
        if submitted_stage != expected_stage:
            raise ApprovalError(
                f"The next required stage is {expected_stage.value}; a blocked request cannot skip stages."
            )
        _require_prior_approvals(submitted_stage, existing_approvals)
    else:
        status_stage = {
            WorkflowStatus.PENDING_PROCUREMENT.value: ApprovalStage.PROCUREMENT,
            WorkflowStatus.PENDING_BUDGET.value: ApprovalStage.BUDGET_OWNER,
            WorkflowStatus.PENDING_FINANCE_HEAD.value: ApprovalStage.FINANCE_HEAD,
        }.get(request.status)
        if status_stage is None:
            raise ApprovalError(
                f"Request status {request.status} is not awaiting an approval decision."
            )
        if submitted_stage != status_stage:
            raise ApprovalError(
                f"The next required stage is {status_stage.value}; {submitted_stage.value} cannot act now."
            )
        _require_prior_approvals(submitted_stage, existing_approvals)

    if any(approval.stage == submitted_stage for approval in existing_approvals):
        raise ApprovalError(f"Stage {submitted_stage.value} already has a persisted decision.")

    if submitted_stage == ApprovalStage.PROCUREMENT:
        if not request.procurement_owner_id or approver_id.strip() != request.procurement_owner_id:
            raise ApprovalError("PROCUREMENT decision must be submitted by the assigned procurement owner.")
    elif submitted_stage == ApprovalStage.BUDGET_OWNER:
        if not request.budget_owner_id or approver_id.strip() != request.budget_owner_id:
            raise ApprovalError("BUDGET_OWNER decision must be submitted by the assigned budget owner.")
    elif submitted_stage == ApprovalStage.FINANCE_HEAD and approver_role != ApprovalStage.FINANCE_HEAD.value:
        raise ApprovalError("FINANCE_HEAD stage requires approver_role FINANCE_HEAD.")

    if submitted_decision == ApprovalDecision.APPROVE:
        for approval in existing_approvals:
            if (
                approval.decision == ApprovalDecision.APPROVE
                and approval.stage != submitted_stage
                and approval.approver_id == approver_id.strip()
            ):
                raise ApprovalError("The same person cannot approve two required stages.")


def _require_prior_approvals(stage: ApprovalStage, approvals: list[Approval]) -> None:
    approved = {item.stage for item in approvals if item.decision == ApprovalDecision.APPROVE}
    expected_prior = {
        ApprovalStage.PROCUREMENT: set(),
        ApprovalStage.BUDGET_OWNER: {ApprovalStage.PROCUREMENT},
        ApprovalStage.FINANCE_HEAD: {ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER},
    }[stage]
    missing = expected_prior - approved
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        raise ApprovalError(f"Approval stages cannot be skipped; prior approval is missing: {names}.")
