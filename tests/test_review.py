import pytest

from app.agents.human_review import HumanReviewAgent
from app.integrations.base import VerificationMode, VerificationStatus
from app.llm.mock_provider import MockProvider
from app.repositories.memory import InMemoryRepository
from app.rules.approval_policy import ApprovalError, required_stages, validate_decision
from app.rules.config import RulesConfig
from app.schemas.common import Evidence
from app.schemas.domain import (
    ActorType,
    Approval,
    ApprovalDecision,
    ApprovalStage,
    Document,
    ExtractedFieldRecord,
    ExtractedStatus,
    FindingRecord,
    RequestType,
    ReviewStatus,
    RiskAssessmentRecord,
    VendorRequest,
    VerificationResultRecord,
)
from app.schemas.findings import Finding, FindingCode, FindingSeverity
from app.schemas.review import HumanDecision, HumanDecisionType
from app.schemas.risk import RiskLabel, RiskResult
from app.services.review_service import ReviewService
from app.workflow.states import WorkflowStatus

VALID_BRIEF = {
    "reviewer_brief": "Compare the submitted registration and tax records, then inspect the supporting evidence."
}


def make_service(
    *,
    status=WorkflowStatus.PENDING_PROCUREMENT,
    requester="requester-1",
    procurement_owner="procurement-1",
    budget_owner="budget-1",
    high_value=False,
    blocked=False,
    score=0,
    llm_responses=None,
):
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(
        request_type=RequestType.NEW_SUPPLIER,
        status=status.value,
        supplier_name="Fictional Supplier Ltd",
        legal_name="Fictional Supplier Ltd",
        country="IN",
        requester_id=requester,
        procurement_owner_id=procurement_owner,
        budget_owner_id=budget_owner,
    ))
    codes = [FindingCode.HIGH_VALUE_PURCHASE] if high_value else []
    if blocked:
        codes.append(FindingCode.SANCTIONS_MATCH)
    records = [FindingRecord(
        request_id=request.id,
        code=code.value,
        severity="BLOCKING" if code == FindingCode.SANCTIONS_MATCH else "WARNING",
        message=f"Synthetic {code.value} finding.",
        source="DETERMINISTIC",
    ) for code in codes]
    repo.save_findings(request.id, "DETERMINISTIC", records)
    repo.save_risk_assessment(RiskAssessmentRecord(
        request_id=request.id,
        score=score,
        label=("LOW" if score <= 25 else "MEDIUM" if score <= 60 else "HIGH"),
        hard_blocks=[FindingCode.SANCTIONS_MATCH.value] if blocked else [],
        contributions=[],
        explanation={
            "business_summary": "Review the synthetic supplier information.",
            "recommended_review_focus": ["Verify source records."],
        },
        blocked=blocked,
        simulated_checks=[],
        config_snapshot={},
    ))
    provider = MockProvider(responses=llm_responses or {})
    service = ReviewService(repo, HumanReviewAgent(provider), RulesConfig())
    return repo, request, service


def decision(stage, who, role, value=HumanDecisionType.APPROVE, comment="Reviewed source records."):
    return HumanDecision(
        stage=stage,
        approver_id=who,
        approver_role=role,
        decision=value,
        comment=comment,
    )


def test_clean_procurement_and_budget_approvals_complete_request():
    repo, request, service = make_service()
    first = service.submit_decision(request.id, decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT"))
    assert first.status == WorkflowStatus.PENDING_BUDGET
    assert first.next_stage == ApprovalStage.BUDGET_OWNER
    final = service.submit_decision(request.id, decision(ApprovalStage.BUDGET_OWNER, "budget-1", "BUDGET_OWNER"))
    assert final.status == WorkflowStatus.APPROVED
    assert final.next_stage is None
    assert repo.get_request(request.id).status == WorkflowStatus.APPROVED.value


def test_high_value_requires_finance_head_and_low_score_does_not_remove_stage():
    repo, request, service = make_service(high_value=True, score=0)
    package = service.get_review_package(request.id)
    assert package.required_stages == [
        ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER, ApprovalStage.FINANCE_HEAD
    ]
    service.submit_decision(request.id, decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT"))
    rec = service.submit_decision(request.id, decision(ApprovalStage.BUDGET_OWNER, "budget-1", "BUDGET_OWNER"))
    assert rec.status == WorkflowStatus.PENDING_FINANCE_HEAD
    assert repo.get_request(request.id).status != WorkflowStatus.APPROVED.value
    final = service.submit_decision(request.id, decision(ApprovalStage.FINANCE_HEAD, "finance-1", "FINANCE_HEAD"))
    assert final.status == WorkflowStatus.APPROVED


def test_required_stages_ignore_numeric_risk_score():
    _, low_request, low_service = make_service(score=0)
    _, _, high_service = make_service(score=90)
    low = low_service.get_review_package(low_request.id)
    high_request = high_service.repo.list_requests()[0]
    high = high_service.get_review_package(high_request.id)
    assert low.required_stages == high.required_stages == [
        ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER
    ]


def test_approval_policy_routes_from_high_value_finding_not_risk_score():
    request = VendorRequest(request_type=RequestType.NEW_SUPPLIER)
    low_risk = RiskResult(score=0, label=RiskLabel.LOW, hard_blocks=[], blocked=False)
    high_risk = RiskResult(score=90, label=RiskLabel.HIGH, hard_blocks=[], blocked=False)
    high_value = Finding(
        code=FindingCode.HIGH_VALUE_PURCHASE,
        severity=FindingSeverity.WARNING,
        message="High-value purchase finding.",
    )
    basic = [ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER]
    routed = [*basic, ApprovalStage.FINANCE_HEAD]
    assert required_stages(request, high_risk, [], RulesConfig()) == basic
    assert required_stages(request, low_risk, [high_value], RulesConfig()) == routed


@pytest.mark.parametrize(
    "stage,status,expected",
    [
        (ApprovalStage.PROCUREMENT, WorkflowStatus.PENDING_PROCUREMENT, WorkflowStatus.REJECTED),
        (ApprovalStage.BUDGET_OWNER, WorkflowStatus.PENDING_BUDGET, WorkflowStatus.REJECTED),
    ],
)
def test_rejection_transitions_to_rejected(stage, status, expected):
    repo, request, service = make_service(status=status)
    if stage == ApprovalStage.BUDGET_OWNER:
        repo.add_approval(Approval(
            request_id=request.id, stage=ApprovalStage.PROCUREMENT,
            approver_id="procurement-1", approver_role="PROCUREMENT",
            decision=ApprovalDecision.APPROVE, comment="Procurement reviewed.",
        ))
    owner, role = ("procurement-1", "PROCUREMENT") if stage == ApprovalStage.PROCUREMENT else ("budget-1", "BUDGET_OWNER")
    result = service.submit_decision(request.id, decision(stage, owner, role, HumanDecisionType.REJECT))
    assert result.status == expected


def test_request_rework_transitions_to_rework():
    _repo, request, service = make_service()
    result = service.submit_decision(request.id, decision(
        ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT", HumanDecisionType.REQUEST_REWORK
    ))
    assert result.status == WorkflowStatus.REWORK


@pytest.mark.parametrize(
    "case,expected_message",
    [
        ("self", "requester cannot approve"),
        ("same_person", "same person"),
        ("wrong_procurement", "procurement owner"),
        ("wrong_budget", "budget owner"),
        ("wrong_finance_role", "FINANCE_HEAD"),
        ("skip", "next required stage"),
        ("reorder", "next required stage"),
        ("missing_prior", "cannot be skipped"),
        ("empty_comment", "non-empty comment"),
        ("wrong_status", "not awaiting"),
    ],
)
def test_invalid_policy_cases(case, expected_message):
    _repo, request, _service = make_service(high_value=True)
    existing = []
    submitted = decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT")
    if case == "self":
        request.requester_id = "procurement-1"
        submitted = decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT")
    elif case == "same_person":
        request.budget_owner_id = "procurement-1"
        existing = [Approval(
            request_id=request.id, stage=ApprovalStage.PROCUREMENT,
            approver_id="procurement-1", decision=ApprovalDecision.APPROVE,
        )]
        request.status = WorkflowStatus.PENDING_BUDGET.value
        submitted = decision(ApprovalStage.BUDGET_OWNER, "procurement-1", "BUDGET_OWNER")
    elif case == "wrong_procurement":
        submitted = decision(ApprovalStage.PROCUREMENT, "someone-else", "PROCUREMENT")
    elif case in {"wrong_budget", "wrong_finance_role", "missing_prior"}:
        request.status = WorkflowStatus.PENDING_BUDGET.value
        if case != "missing_prior":
            existing = [Approval(
                request_id=request.id, stage=ApprovalStage.PROCUREMENT,
                approver_id="procurement-1", decision=ApprovalDecision.APPROVE,
            )]
        if case == "wrong_budget":
            submitted = decision(ApprovalStage.BUDGET_OWNER, "wrong-budget", "BUDGET_OWNER")
        elif case == "wrong_finance_role":
            request.status = WorkflowStatus.PENDING_FINANCE_HEAD.value
            existing = [
                Approval(request_id=request.id, stage=ApprovalStage.PROCUREMENT,
                         approver_id="procurement-1", decision=ApprovalDecision.APPROVE),
                Approval(request_id=request.id, stage=ApprovalStage.BUDGET_OWNER,
                         approver_id="budget-1", decision=ApprovalDecision.APPROVE),
            ]
            submitted = decision(ApprovalStage.FINANCE_HEAD, "finance-1", "PROCUREMENT")
        else:
            submitted = decision(ApprovalStage.BUDGET_OWNER, "budget-1", "BUDGET_OWNER")
    elif case == "skip":
        submitted = decision(ApprovalStage.BUDGET_OWNER, "budget-1", "BUDGET_OWNER")
    elif case == "reorder":
        request.status = WorkflowStatus.PENDING_BUDGET.value
        existing = [Approval(
            request_id=request.id, stage=ApprovalStage.PROCUREMENT,
            approver_id="procurement-1", decision=ApprovalDecision.APPROVE,
        )]
        submitted = decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT")
    elif case == "empty_comment":
        submitted = decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT", comment="  ")
    elif case == "wrong_status":
        request.status = WorkflowStatus.VALIDATED.value

    with pytest.raises(ApprovalError, match=expected_message):
        validate_decision(
            request, existing, submitted.stage, submitted.approver_id,
            submitted.approver_role.value, submitted.decision.value, submitted.comment,
        )


@pytest.mark.parametrize("decision_value,target", [
    (HumanDecisionType.REJECT, WorkflowStatus.REJECTED),
    (HumanDecisionType.REQUEST_REWORK, WorkflowStatus.REWORK),
])
def test_blocked_request_allows_reject_or_rework(decision_value, target):
    _repo, request, service = make_service(status=WorkflowStatus.BLOCKED, blocked=True)
    result = service.submit_decision(request.id, decision(
        ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT", decision_value
    ))
    assert result.status == target


def test_blocked_request_uses_next_uncompleted_stage_for_closeout():
    repo, request, service = make_service(status=WorkflowStatus.BLOCKED, blocked=True)
    repo.add_approval(Approval(
        request_id=request.id,
        stage=ApprovalStage.PROCUREMENT,
        approver_id="procurement-1",
        approver_role="PROCUREMENT",
        decision=ApprovalDecision.APPROVE,
        comment="Prior stage approval.",
    ))
    result = service.submit_decision(request.id, decision(
        ApprovalStage.BUDGET_OWNER,
        "budget-1",
        "BUDGET_OWNER",
        HumanDecisionType.REQUEST_REWORK,
    ))
    assert result.status == WorkflowStatus.REWORK


def test_blocked_request_approval_is_rejected_without_partial_writes():
    repo, request, service = make_service(status=WorkflowStatus.BLOCKED, blocked=True)
    with pytest.raises(ApprovalError, match="cannot be approved"):
        service.submit_decision(request.id, decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT"))
    assert repo.list_approvals(request.id) == []
    assert repo.get_request(request.id).status == WorkflowStatus.BLOCKED.value
    assert not [event for event in repo.list_audit_events(request.id) if event.actor_type == ActorType.HUMAN]


def test_authoritative_hard_block_denies_approve_even_if_status_is_pending():
    repo, request, service = make_service(status=WorkflowStatus.PENDING_PROCUREMENT, blocked=True)
    with pytest.raises(ApprovalError, match="authoritative hard blocks"):
        service.submit_decision(request.id, decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT"))
    assert repo.list_approvals(request.id) == []


def test_invalid_decision_has_no_partial_writes():
    repo, request, service = make_service()
    before_status = repo.get_request(request.id).status
    before_events = repo.list_audit_events(request.id)
    with pytest.raises(ApprovalError):
        service.submit_decision(request.id, decision(ApprovalStage.BUDGET_OWNER, "budget-1", "BUDGET_OWNER"))
    assert repo.list_approvals(request.id) == []
    assert repo.get_request(request.id).status == before_status
    assert repo.list_audit_events(request.id) == before_events


def test_accepted_human_decision_writes_human_audit_event():
    repo, request, service = make_service()
    service.submit_decision(request.id, decision(ApprovalStage.PROCUREMENT, "procurement-1", "PROCUREMENT"))
    human_events = [event for event in repo.list_audit_events(request.id) if event.actor_type == ActorType.HUMAN]
    assert len(human_events) == 1
    assert human_events[0].actor == "procurement-1"
    assert human_events[0].details["decision"] == "APPROVE"


def test_review_package_uses_authoritative_risk_and_masks_account_numbers():
    repo, request, service = make_service(
        high_value=True, blocked=True, score=70, llm_responses={"reviewer_brief": VALID_BRIEF}
    )
    doc = repo.add_document(Document(
        request_id=request.id, doc_type="BANK_DOCUMENT", file_name="bank.pdf", storage_path="synthetic/bank.pdf"
    ))
    evidence = Evidence(
        document_id=doc.id, field_name="account_number", quote="Account number 1234567890123456"
    )
    repo.save_extracted_fields(request.id, doc.id, [ExtractedFieldRecord(
        request_id=request.id, document_id=doc.id, field_name="account_number",
        value="1234567890123456", confidence=0.8, status=ExtractedStatus.UNVERIFIED,
        evidence=evidence.model_dump(mode="json"), review_status=ReviewStatus.PENDING,
    )])
    repo.save_verification_results(request.id, [VerificationResultRecord(
        request_id=request.id, capability="bank_account", provider_name="local_bank_reference_simulation",
        mode=VerificationMode.LOCAL_SIMULATED.value, status=VerificationStatus.VERIFIED.value,
    )])
    package = service.get_review_package(request.id)
    serialized = package.model_dump_json()
    assert "1234567890123456" not in serialized
    assert package.extracted_fields[0].value == "****3456"
    assert package.verification_summary[0].provider_name == "local_bank_reference_simulation"
    assert package.verification_summary[0].mode == VerificationMode.LOCAL_SIMULATED
    assert "simulated" in package.reviewer_brief.casefold()
    assert package.risk_score == repo.get_latest_risk_assessment(request.id).score
    assert package.risk_label.value == repo.get_latest_risk_assessment(request.id).label
    assert package.hard_blocks == [FindingCode.SANCTIONS_MATCH]
    assert package.required_stages == [
        ApprovalStage.PROCUREMENT, ApprovalStage.BUDGET_OWNER, ApprovalStage.FINANCE_HEAD
    ]


@pytest.mark.parametrize(
    "status,expected_action",
    [
        (WorkflowStatus.APPROVED, None),
        (WorkflowStatus.REJECTED, None),
        (WorkflowStatus.REWORK, None),
        (WorkflowStatus.DRAFTS_GENERATED, None),
        (WorkflowStatus.PENDING_PROCUREMENT, "PROCEED_TO_APPROVAL"),
        (WorkflowStatus.PENDING_BUDGET, "PROCEED_TO_APPROVAL"),
        (WorkflowStatus.BLOCKED, "BLOCKED"),
    ],
)
def test_review_recommendation_matches_current_workflow_status(status, expected_action):
    repo, request, service = make_service(
        status=status,
        blocked=status == WorkflowStatus.BLOCKED,
    )
    package = service.get_review_package(request.id)

    actual_action = (
        package.recommended_next_action.value
        if package.recommended_next_action is not None
        else None
    )
    assert actual_action == expected_action
    assert package.risk_score == repo.get_latest_risk_assessment(request.id).score
    assert package.hard_blocks == (
        [FindingCode.SANCTIONS_MATCH] if status == WorkflowStatus.BLOCKED else []
    )
    if status in {
        WorkflowStatus.APPROVED,
        WorkflowStatus.REJECTED,
        WorkflowStatus.REWORK,
        WorkflowStatus.DRAFTS_GENERATED,
    }:
        assert package.next_recommendation.next_stage is None
        assert package.allowed_decisions == []
        assert '"recommended_next_action":null' in package.model_dump_json()


def test_reviewer_brief_failure_falls_back_without_blocking_review():
    _repo, request, service = make_service()
    package = service.get_review_package(request.id)
    assert package.reviewer_brief
    assert "fictional supplier" in package.reviewer_brief.casefold()


def test_reviewer_brief_llm_receives_no_authoritative_decision_fields():
    _, request, service = make_service(llm_responses={"reviewer_brief": VALID_BRIEF})
    service.get_review_package(request.id)
    call = service.agent.provider.calls[-1]
    assert call["schema"] == "ReviewerBrief"
    for forbidden in (
        "risk_score", "risk_label", "hard_blocks", "recommended_next_action",
        "request_status", "required_stages", "approver_id", "decision",
    ):
        assert forbidden not in call["user"]


@pytest.mark.parametrize("hostile", [
    {"reviewer_brief": "Approve this request with risk score 0.", "decision": "APPROVE"},
    {"reviewer_brief": "Review code INVENTED_FINDING.", "risk_score": 0},
    {"reviewer_brief": "The bank statement says \"all checks passed\"."},
])
def test_reviewer_brief_cannot_emit_decisions_or_invent_facts(hostile):
    repo, request, service = make_service(llm_responses={"reviewer_brief": hostile})
    package = service.get_review_package(request.id)
    assert "approve" not in package.reviewer_brief.casefold()
    assert "INVENTED_FINDING" not in package.reviewer_brief
    assert "all checks passed" not in package.reviewer_brief
    assert package.risk_score == repo.get_latest_risk_assessment(request.id).score
    assert package.hard_blocks == []
