from app.agents.human_review import HumanReviewAgent
from app.orchestration.decision import decide_next_action
from app.repositories.base import OnboardingRepository
from app.rules.approval_policy import ApprovalError, required_stages, validate_decision
from app.rules.config import RulesConfig
from app.rules.document_fields import REQUIRED_FIELDS, DocumentType
from app.schemas.assessment import ExtractionOutcome, NextAction
from app.schemas.common import Evidence
from app.schemas.domain import (
    ActorType,
    Approval,
    ApprovalDecision,
    ApprovalStage,
    AuditEvent,
    ExtractedFieldRecord,
    ReviewStatus,
)
from app.schemas.findings import Finding, FindingCode
from app.schemas.review import (
    HumanDecision,
    HumanDecisionType,
    NextRecommendation,
    ReviewExtractedField,
    ReviewHistoryEntry,
    ReviewPackage,
    ReviewSupplierSummary,
    ReviewVerificationSummary,
)
from app.schemas.risk import RiskContribution, RiskLabel, RiskResult
from app.utils.masking import mask_account_number
from app.workflow.states import WorkflowStatus, can_transition


class ReviewService:
    def __init__(
        self,
        repo: OnboardingRepository,
        agent: HumanReviewAgent,
        rules_config: RulesConfig | None = None,
    ) -> None:
        self.repo = repo
        self.agent = agent
        self.rules_config = rules_config or RulesConfig()

    def get_review_package(self, request_id: str) -> ReviewPackage:
        request = self.repo.get_request(request_id)
        if request is None:
            raise KeyError(f"Request not found: {request_id}")
        risk_record = self.repo.get_latest_risk_assessment(request_id)
        if risk_record is None:
            raise KeyError(f"Risk assessment not found: {request_id}")
        risk = self._risk_result(risk_record)
        findings = [self._finding(record) for record in self.repo.list_findings(request_id)]
        documents = self.repo.list_documents(request_id)
        document_types = self._document_types(documents)
        extracted = [
            self._safe_field(record, document_types.get(record.document_id, DocumentType.UNKNOWN))
            for record in self.repo.list_extracted_fields(request_id)
        ]
        verifications = [
            ReviewVerificationSummary(
                capability=record.capability,
                provider_name=record.provider_name,
                mode=record.mode,
                status=record.status,
            )
            for record in self.repo.list_verification_results(request_id)
        ]
        approvals = self.repo.list_approvals(request_id)
        stages = required_stages(request, risk, findings, self.rules_config)
        completed = self._completed_stages(approvals)
        supplier = ReviewSupplierSummary(
            request_type=request.request_type.value,
            supplier_name=request.supplier_name,
            legal_name=request.legal_name,
            country=request.country,
            estimated_annual_spend=(
                str(request.estimated_annual_spend)
                if request.estimated_annual_spend is not None else None
            ),
            request_status=WorkflowStatus(request.status),
        )
        evidence = self._all_evidence(extracted, findings)
        risk_explanation = risk_record.explanation
        explanation = _mask_labeled_accounts(
            str(risk_explanation.get("business_summary") or "Deterministic risk assessment is available.")
        )
        recommended_actions = risk_explanation.get("recommended_review_focus", [])
        if not isinstance(recommended_actions, list):
            recommended_actions = []
        action = self._recommended_action(request_id, request.status, findings, risk, extracted)
        recommendation = self._next_recommendation(request.status, stages, completed, risk.blocked)
        allowed_decisions = self._allowed_decisions(request.status, risk.blocked)
        audit_history = [
            self._history(item)
            for item in self.repo.list_audit_events(request_id)
        ]
        package = ReviewPackage(
            request_id=request_id,
            request_status=supplier.request_status,
            supplier_summary=supplier,
            extracted_fields=extracted,
            evidence=evidence,
            validation_findings=findings,
            risk_score=risk.score,
            risk_label=risk.label,
            hard_blocks=risk.hard_blocks,
            explanation=explanation,
            verification_summary=verifications,
            recommended_next_action=action,
            required_stages=stages,
            completed_stages=completed,
            reviewer_brief="",
            recommended_review_actions=[_mask_labeled_accounts(str(item)) for item in recommended_actions],
            next_recommendation=recommendation,
            allowed_decisions=allowed_decisions,
            history=audit_history,
        )
        result = self.agent.run(package)
        if result.data is not None:
            return result.data
        return package.model_copy(
            update={
                "reviewer_brief": (
                    f"Review the submitted information for {supplier.legal_name or supplier.supplier_name or 'this supplier'}. "
                    "Inspect the deterministic findings and source evidence."
                )
            }
        )

    def submit_decision(
        self, request_id: str, decision: HumanDecision
    ) -> NextRecommendation:
        request = self.repo.get_request(request_id)
        if request is None:
            raise ApprovalError(f"Request not found: {request_id}")
        risk_record = self.repo.get_latest_risk_assessment(request_id)
        if risk_record is None:
            raise ApprovalError("A persisted risk assessment is required before approvals.")
        risk = self._risk_result(risk_record)
        findings = [self._finding(record) for record in self.repo.list_findings(request_id)]
        stages = required_stages(request, risk, findings, self.rules_config)
        if decision.stage not in stages:
            raise ApprovalError(f"Approval stage {decision.stage.value} is not required for this request.")
        if risk.blocked and decision.decision == HumanDecisionType.APPROVE:
            raise ApprovalError("A request with authoritative hard blocks cannot be approved.")
        existing = self.repo.list_approvals(request_id)
        validate_decision(
            request,
            existing,
            decision.stage,
            decision.approver_id,
            decision.approver_role.value,
            ApprovalDecision(decision.decision.value),
            decision.comment,
            required_stage_list=stages,
        )
        target = self._target_status(request.status, decision.decision, decision.stage, stages)
        if not can_transition(request.status, target):
            raise ApprovalError(f"Workflow transition {request.status} -> {target.value} is not allowed.")

        approval = Approval(
            request_id=request_id,
            stage=decision.stage,
            approver_id=decision.approver_id.strip(),
            approver_role=decision.approver_role.value,
            decision=ApprovalDecision(decision.decision.value),
            comment=_mask_labeled_accounts(decision.comment.strip()),
        )
        self.repo.add_approval(approval)
        self.repo.append_audit_event(
            AuditEvent(
                request_id=request_id,
                actor=decision.approver_id.strip(),
                actor_type=ActorType.HUMAN,
                event_type="HUMAN_APPROVAL_DECISION_SUBMITTED",
                details={
                    "stage": decision.stage.value,
                    "approver_role": decision.approver_role.value,
                    "decision": decision.decision.value,
                    "comment": _mask_labeled_accounts(decision.comment.strip()),
                    "from_status": request.status,
                    "to_status": target.value,
                },
            )
        )
        self.repo.set_request_status(
            request_id,
            target,
            decision.approver_id.strip(),
            f"Human {decision.decision.value.lower()} decision at {decision.stage.value}.",
        )
        next_stage = self._stage_for_status(target)
        message = (
            f"Awaiting {next_stage.value} human approval."
            if next_stage
            else f"Human decision recorded; request status is {target.value}."
        )
        return NextRecommendation(status=target, next_stage=next_stage, message=message)

    @staticmethod
    def _risk_result(record) -> RiskResult:
        hard_blocks = [FindingCode(value) for value in record.hard_blocks]
        contributions = [RiskContribution.model_validate(value) for value in record.contributions]
        return RiskResult(
            score=record.score,
            label=RiskLabel(record.label),
            hard_blocks=hard_blocks,
            blocked=bool(record.blocked or hard_blocks),
            contributions=contributions,
            simulated_checks=record.simulated_checks,
            config_snapshot=record.config_snapshot,
        )

    @staticmethod
    def _finding(record) -> Finding:
        evidence = record.evidence or []
        if isinstance(evidence, dict):
            evidence = [evidence]
        safe_evidence = [
            Evidence.model_validate({**item, "quote": _mask_labeled_accounts(str(item.get("quote", "")))})
            for item in evidence if isinstance(item, dict)
        ]
        return Finding(
            id=record.id,
            code=record.code,
            severity=record.severity,
            message=_mask_labeled_accounts(record.message),
            evidence=safe_evidence,
            source=record.source,
        )

    @staticmethod
    def _document_types(documents) -> dict[str, DocumentType]:
        result = {}
        for document in documents:
            try:
                result[document.id] = DocumentType(document.doc_type.upper())
            except ValueError:
                result[document.id] = DocumentType.UNKNOWN
        return result

    @staticmethod
    def _safe_field(record: ExtractedFieldRecord, document_type: DocumentType) -> ReviewExtractedField:
        value = record.value
        if "account" in record.field_name.casefold() or "iban" in record.field_name.casefold():
            value = mask_account_number(str(value)) if value is not None else None
        evidence = record.evidence or []
        if isinstance(evidence, dict):
            evidence = [evidence]
        safe_evidence = [
            Evidence.model_validate({**item, "quote": _mask_labeled_accounts(str(item.get("quote", "")))})
            for item in evidence if isinstance(item, dict)
        ]
        return ReviewExtractedField(
            document_id=record.document_id,
            document_type=document_type,
            field_name=record.field_name,
            value=value,
            confidence=float(record.confidence) if record.confidence is not None else None,
            status=record.status,
            review_status=record.review_status,
            evidence=safe_evidence,
        )

    @staticmethod
    def _all_evidence(fields: list[ReviewExtractedField], findings: list[Finding]) -> list[Evidence]:
        unique = {}
        for item in [evidence for field in fields for evidence in field.evidence] + [
            evidence for finding in findings for evidence in finding.evidence
        ]:
            key = (item.document_id, item.field_name, item.quote, item.page, item.verification_mode)
            unique[key] = item
        return [unique[key] for key in sorted(unique, key=lambda value: tuple(str(part) for part in value))]

    @staticmethod
    def _completed_stages(approvals: list[Approval]) -> list[ApprovalStage]:
        approved = {item.stage for item in approvals if item.decision == ApprovalDecision.APPROVE}
        return [stage for stage in ApprovalStage if stage in approved]

    @staticmethod
    def _history(event: AuditEvent) -> ReviewHistoryEntry:
        details = event.details
        if event.event_type == "HUMAN_APPROVAL_DECISION_SUBMITTED":
            summary = (
                f"{details.get('decision', 'Decision')} submitted for "
                f"{details.get('stage', 'approval')} stage."
            )
        elif event.event_type == "REQUEST_STATUS_CHANGED":
            summary = (
                f"Request status changed from {details.get('from', 'unknown')} "
                f"to {details.get('to', 'unknown')}."
            )
        else:
            summary = event.event_type.replace("_", " ").capitalize() + "."
        return ReviewHistoryEntry(
            created_at=event.created_at,
            event_type=event.event_type,
            actor=event.actor,
            actor_type=event.actor_type.value,
            summary=summary,
        )

    @staticmethod
    def _stage_for_status(status: WorkflowStatus) -> ApprovalStage | None:
        return {
            WorkflowStatus.PENDING_PROCUREMENT: ApprovalStage.PROCUREMENT,
            WorkflowStatus.PENDING_BUDGET: ApprovalStage.BUDGET_OWNER,
            WorkflowStatus.PENDING_FINANCE_HEAD: ApprovalStage.FINANCE_HEAD,
        }.get(WorkflowStatus(status))

    def _next_recommendation(
        self,
        status_value: str,
        required: list[ApprovalStage],
        completed: list[ApprovalStage],
        blocked: bool,
    ) -> NextRecommendation:
        status = WorkflowStatus(status_value)
        if status == WorkflowStatus.BLOCKED:
            next_stage = next((stage for stage in required if stage not in completed), None)
            return NextRecommendation(
                status=status,
                next_stage=next_stage,
                message=(
                    f"A blocked request may be rejected or returned for rework at {next_stage.value}; approval is prohibited."
                    if next_stage else "A blocked request has no uncompleted stage available for closure."
                ),
            )
        stage = self._stage_for_status(status)
        if stage:
            return NextRecommendation(status=status, next_stage=stage, message=f"Awaiting {stage.value} human decision.")
        next_uncompleted = next((stage for stage in required if stage not in completed), None)
        if blocked:
            return NextRecommendation(
                status=status,
                next_stage=next_uncompleted,
                message="Hard blocks prohibit approval; an authorized reviewer must reject or request rework.",
            )
        terminal_messages = {
            WorkflowStatus.APPROVED: "All required human approvals are complete.",
            WorkflowStatus.REJECTED: "The request was rejected by a human reviewer.",
            WorkflowStatus.REWORK: "The request was returned for rework.",
            WorkflowStatus.DRAFTS_GENERATED: "Approval is complete and onboarding drafts have been generated.",
        }
        if status in terminal_messages:
            return NextRecommendation(
                status=status,
                next_stage=None,
                message=terminal_messages[status],
            )
        return NextRecommendation(
            status=status,
            next_stage=next_uncompleted,
            message=(f"Eligible for {next_uncompleted.value} human review." if next_uncompleted else f"No approval stage is pending; status is {status.value}."),
        )

    @staticmethod
    def _allowed_decisions(status_value: str, blocked: bool) -> list[HumanDecisionType]:
        status = WorkflowStatus(status_value)
        awaiting = status in {
            WorkflowStatus.PENDING_PROCUREMENT,
            WorkflowStatus.PENDING_BUDGET,
            WorkflowStatus.PENDING_FINANCE_HEAD,
            WorkflowStatus.BLOCKED,
        }
        if not awaiting:
            return []
        if blocked or status == WorkflowStatus.BLOCKED:
            return [HumanDecisionType.REJECT, HumanDecisionType.REQUEST_REWORK]
        return [HumanDecisionType.APPROVE, HumanDecisionType.REJECT, HumanDecisionType.REQUEST_REWORK]

    def _recommended_action(self, request_id, status, findings, risk, fields) -> NextAction | None:
        workflow_status = WorkflowStatus(status)
        if workflow_status in {
            WorkflowStatus.APPROVED,
            WorkflowStatus.REJECTED,
            WorkflowStatus.DRAFTS_GENERATED,
            WorkflowStatus.REWORK,
        }:
            return None
        if workflow_status == WorkflowStatus.BLOCKED:
            return NextAction.BLOCKED
        events = self.repo.list_audit_events(request_id)
        for event in reversed(events):
            if event.event_type == "ONBOARDING_ASSESSMENT_COMPLETED":
                try:
                    return NextAction(event.details["recommended_next_action"])
                except (KeyError, ValueError):
                    break
        doc_types = {item.document_id: item.document_type for item in fields}
        missing = []
        for item in fields:
            if item.field_name in REQUIRED_FIELDS.get(doc_types.get(item.document_id, DocumentType.UNKNOWN), ()) and item.status.value != "FOUND":
                missing.append(item.field_name)
        pending = any(
            item.review_status == ReviewStatus.PENDING
            and (item.status.value == "UNVERIFIED" or item.confidence is None or item.confidence < self.rules_config.low_confidence_threshold)
            for item in fields
        )
        return decide_next_action(
            self._extraction_outcome(request_id), findings, risk, pending,
            missing_required_fields=missing,
        )[0]

    def _extraction_outcome(self, request_id: str):
        for event in reversed(self.repo.list_audit_events(request_id)):
            if event.event_type == "ONBOARDING_ASSESSMENT_COMPLETED":
                try:
                    return ExtractionOutcome(event.details["extraction_status"])
                except (KeyError, ValueError):
                    break
        documents = self.repo.list_documents(request_id)
        if not documents:
            return ExtractionOutcome.NOT_RUN
        return ExtractionOutcome.UNUSABLE if any(
            document.text_quality and document.text_quality.get("usable") is False
            for document in documents
        ) else ExtractionOutcome.COMPLETED

    @staticmethod
    def _target_status(
        current_status: str,
        decision: HumanDecisionType,
        stage: ApprovalStage,
        stages: list[ApprovalStage],
    ) -> WorkflowStatus:
        if decision == HumanDecisionType.REJECT:
            return WorkflowStatus.REJECTED
        if decision == HumanDecisionType.REQUEST_REWORK:
            return WorkflowStatus.REWORK
        if stage == ApprovalStage.PROCUREMENT:
            return WorkflowStatus.PENDING_BUDGET
        if stage == ApprovalStage.BUDGET_OWNER and ApprovalStage.FINANCE_HEAD in stages:
            return WorkflowStatus.PENDING_FINANCE_HEAD
        return WorkflowStatus.APPROVED


def _mask_labeled_accounts(value: str) -> str:
    import re

    pattern = re.compile(
        r"(?i)(\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#)|iban)\s*[:#-]?)"
        r"((?:\d[ -]?){7,30}\d|[A-Z0-9][A-Z0-9-]{7,33})"
    )
    return pattern.sub(
        lambda match: f"{match.group(1)}{mask_account_number(match.group(2))}", value
    )
