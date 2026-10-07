from app.agents.po_draft import PODraftAgent
from app.agents.vendor_draft import VendorDraftAgent
from app.llm.mock_provider import MockProvider
from app.repositories.base import OnboardingRepository
from app.rules.approval_policy import required_stages
from app.rules.config import RulesConfig
from app.schemas.domain import (
    ActorType,
    Approval,
    ApprovalDecision,
    ApprovalStage,
    AuditEvent,
    PODraftRecord,
    VendorDraftRecord,
)
from app.schemas.drafts import PODraftInput, VendorDraftInput
from app.schemas.findings import Finding, FindingCode
from app.workflow.states import WorkflowStatus


class DraftGenerationError(ValueError):
    """Draft generation was refused because authoritative prerequisites are unmet."""


class DraftService:
    def __init__(
        self,
        repo: OnboardingRepository,
        vendor_agent: VendorDraftAgent | None = None,
        po_agent: PODraftAgent | None = None,
        rules_config: RulesConfig | None = None,
    ) -> None:
        self.repo = repo
        provider = MockProvider()
        self.vendor_agent = vendor_agent or VendorDraftAgent(provider)
        self.po_agent = po_agent or PODraftAgent(provider)
        self.rules_config = rules_config or RulesConfig()

    def generate_drafts(self, request_id: str):
        """Persist a new draft version only for a fully approved, unblocked request."""
        return self._generate(request_id, allow_revision=False)

    def generate_revision(self, request_id: str):
        """Create an explicitly requested next revision for an already generated draft set."""
        return self._generate(request_id, allow_revision=True)

    def _generate(self, request_id: str, *, allow_revision: bool):
        request = self.repo.get_request(request_id)
        if request is None:
            raise DraftGenerationError(f"Request not found: {request_id}")
        expected_status = (
            {WorkflowStatus.APPROVED, WorkflowStatus.DRAFTS_GENERATED}
            if allow_revision else {WorkflowStatus.APPROVED}
        )
        if WorkflowStatus(request.status) not in expected_status:
            raise DraftGenerationError(
                "Draft generation requires APPROVED status"
                + (" (or DRAFTS_GENERATED for an explicit new revision)." if allow_revision else ".")
            )
        if WorkflowStatus(request.status) in {WorkflowStatus.BLOCKED, WorkflowStatus.REJECTED}:
            raise DraftGenerationError("Blocked or rejected requests cannot generate drafts.")

        risk = self.repo.get_latest_risk_assessment(request_id)
        if risk is None:
            raise DraftGenerationError("A persisted risk assessment is required before draft generation.")
        if risk.blocked or risk.hard_blocks:
            raise DraftGenerationError("Hard-blocked requests cannot generate drafts.")
        findings = self.repo.list_findings(request_id)
        finding_models = [
            Finding(
                id=item.id,
                code=FindingCode(item.code),
                severity=item.severity,
                message=item.message,
                source=item.source,
            )
            for item in findings
        ]
        stages = required_stages(request, _risk_result(risk), finding_models, self.rules_config)
        approvals = self.repo.list_approvals(request_id)
        self._validate_approvals(request, approvals, stages)

        vendor_history = self.repo.list_vendor_drafts(request_id)
        po_history = self.repo.list_po_drafts(request_id)
        if len(vendor_history) != len(po_history):
            raise DraftGenerationError("Vendor and PO draft version histories are inconsistent.")
        version = max((item.version for item in vendor_history), default=0) + 1
        if version != max((item.version for item in po_history), default=0) + 1:
            raise DraftGenerationError("Vendor and PO draft versions are inconsistent.")

        fields = self.repo.list_extracted_fields(request_id)
        verifications = self.repo.list_verification_results(request_id)
        vendor_result = self.vendor_agent.run(VendorDraftInput(
            request=request,
            fields=fields,
            verifications=verifications,
            approvals=approvals,
            findings=findings,
            version=version,
        ))
        po_result = self.po_agent.run(PODraftInput(
            request=request,
            fields=fields,
            approvals=approvals,
            findings=findings,
            version=version,
        ))
        if vendor_result.data is None or po_result.data is None:
            raise DraftGenerationError("Draft agent did not return both structured drafts.")
        vendor_draft = vendor_result.data
        po_draft = po_result.data
        vendor_record = VendorDraftRecord(
            request_id=request_id,
            draft=vendor_draft.model_dump(mode="json"),
            version=version,
        )
        po_record = PODraftRecord(
            request_id=request_id,
            draft=po_draft.model_dump(mode="json"),
            version=version,
        )

        # Build and validate both models before writes. Transition only after both saves.
        self.repo.save_vendor_draft(vendor_record)
        self.repo.save_po_draft(po_record)
        self.repo.append_audit_event(AuditEvent(
            request_id=request_id,
            actor="draft_service",
            actor_type=ActorType.SYSTEM,
            event_type="VENDOR_DRAFT_GENERATED",
            details={"draft_id": vendor_record.id, "version": version, "status": "DRAFT"},
        ))
        self.repo.append_audit_event(AuditEvent(
            request_id=request_id,
            actor="draft_service",
            actor_type=ActorType.SYSTEM,
            event_type="PO_DRAFT_GENERATED",
            details={"draft_id": po_record.id, "version": version, "status": "DRAFT"},
        ))
        if not allow_revision:
            self.repo.set_request_status(
                request_id,
                WorkflowStatus.DRAFTS_GENERATED,
                "draft_service",
                "Vendor and PO drafts were generated after all required human approvals.",
            )
        return vendor_draft, po_draft

    @staticmethod
    def _validate_approvals(request, approvals: list[Approval], stages: list[ApprovalStage]) -> None:
        by_stage: dict[ApprovalStage, list[Approval]] = {}
        for approval in approvals:
            by_stage.setdefault(approval.stage, []).append(approval)
        expected_roles = {
            ApprovalStage.PROCUREMENT: ("PROCUREMENT", request.procurement_owner_id),
            ApprovalStage.BUDGET_OWNER: ("BUDGET_OWNER", request.budget_owner_id),
            ApprovalStage.FINANCE_HEAD: ("FINANCE_HEAD", None),
        }
        approvers: set[str] = set()
        for stage in stages:
            stage_approvals = by_stage.get(stage, [])
            if len(stage_approvals) != 1:
                raise DraftGenerationError(f"Required approval is missing or duplicated: {stage.value}.")
            approval = stage_approvals[0]
            expected_role, expected_owner = expected_roles[stage]
            if approval.decision != ApprovalDecision.APPROVE:
                raise DraftGenerationError(f"Required approval is not approved: {stage.value}.")
            if not approval.comment or not approval.comment.strip():
                raise DraftGenerationError(f"Required approval comment is missing: {stage.value}.")
            if not approval.approver_id.strip() or approval.approver_role != expected_role:
                raise DraftGenerationError(f"Required approval role is invalid: {stage.value}.")
            if stage in {ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER} and (
                not expected_owner or approval.approver_id != expected_owner
            ):
                raise DraftGenerationError(f"Required approval owner is invalid: {stage.value}.")
            if approval.approver_id == request.requester_id:
                raise DraftGenerationError("The requester cannot approve their own request.")
            if approval.approver_id in approvers:
                raise DraftGenerationError("The same person cannot approve two required stages.")
            approvers.add(approval.approver_id)
        approved_order = [
            item.stage
            for item in sorted(approvals, key=lambda row: row.created_at)
            if item.stage in stages and item.decision == ApprovalDecision.APPROVE
        ]
        if approved_order != stages:
            raise DraftGenerationError("Required approval stages were not approved in policy order.")
        if any(stage not in stages and approval.decision == ApprovalDecision.APPROVE for stage, rows in by_stage.items() for approval in rows):
            raise DraftGenerationError("An approval exists for a stage not required by the request.")


def _risk_result(record):
    from app.schemas.risk import RiskLabel, RiskResult

    return RiskResult(
        score=record.score,
        label=RiskLabel(record.label),
        hard_blocks=[FindingCode(value) for value in record.hard_blocks],
        blocked=bool(record.blocked or record.hard_blocks),
        contributions=[],
        simulated_checks=record.simulated_checks,
        config_snapshot=record.config_snapshot,
    )
