"""Offline human-review workflow demonstration using fictional records."""

from app.agents.human_review import HumanReviewAgent
from app.integrations.base import VerificationMode, VerificationStatus
from app.llm.mock_provider import MockProvider
from app.repositories.memory import InMemoryRepository
from app.rules.approval_policy import ApprovalError
from app.schemas.domain import (
    ApprovalStage,
    FindingRecord,
    RequestType,
    RiskAssessmentRecord,
    VendorRequest,
    VerificationResultRecord,
)
from app.schemas.findings import FindingCode
from app.schemas.review import HumanDecision, HumanDecisionType
from app.services.review_service import ReviewService
from app.workflow.states import WorkflowStatus

BRIEF = {
    "reviewer_brief": "Compare the submitted supplier records and review the cited validation evidence."
}


def make_case(label, *, high_value=False, blocked=False, status=WorkflowStatus.PENDING_PROCUREMENT,
              requester="synthetic-requester", procurement_owner="synthetic-procurement",
              budget_owner="synthetic-budget", fail_llm=False):
    repo = InMemoryRepository()
    request = repo.create_request(VendorRequest(
        request_type=RequestType.NEW_SUPPLIER,
        status=status.value,
        supplier_name="Fictional Example Supplier Ltd",
        legal_name="Fictional Example Supplier Ltd",
        country="IN",
        requester_id=requester,
        procurement_owner_id=procurement_owner,
        budget_owner_id=budget_owner,
        is_demo=True,
    ))
    codes = ([FindingCode.HIGH_VALUE_PURCHASE] if high_value else [])
    if blocked:
        codes.append(FindingCode.SANCTIONS_MATCH)
    repo.save_findings(request.id, "DETERMINISTIC", [FindingRecord(
        request_id=request.id,
        code=code.value,
        severity="BLOCKING" if code == FindingCode.SANCTIONS_MATCH else "WARNING",
        message=f"Synthetic finding: {code.value}.",
        source="DETERMINISTIC",
    ) for code in codes])
    score = 60 if blocked else (10 if high_value else 0)
    repo.save_risk_assessment(RiskAssessmentRecord(
        request_id=request.id,
        score=score,
        label="MEDIUM" if score > 25 else "LOW",
        hard_blocks=[FindingCode.SANCTIONS_MATCH.value] if blocked else [],
        blocked=blocked,
        explanation={"business_summary": "Synthetic risk information for review.",
                     "recommended_review_focus": ["Review source documents."]},
    ))
    repo.save_verification_results(request.id, [VerificationResultRecord(
        request_id=request.id,
        capability="company_registry",
        provider_name="fictional_local_registry",
        mode=VerificationMode.LOCAL_SIMULATED.value,
        status=VerificationStatus.VERIFIED.value,
    )])
    responses = {} if fail_llm else {"reviewer_brief": BRIEF}
    service = ReviewService(repo, HumanReviewAgent(MockProvider(responses=responses)))
    print(f"\n{label}")
    show_package(service.get_review_package(request.id))
    return repo, request, service


def decision(stage, actor, role, value=HumanDecisionType.APPROVE):
    return HumanDecision(
        stage=stage,
        approver_id=actor,
        approver_role=role,
        decision=value,
        comment="Synthetic reviewer inspected the source package.",
    )


def show_package(package):
    print(f"  request: {package.request_id}")
    print(f"  current status: {package.request_status.value}")
    print(f"  required stages: {[stage.value for stage in package.required_stages]}")
    print(f"  completed stages: {[stage.value for stage in package.completed_stages]}")
    next_stage = package.next_recommendation.next_stage
    print(f"  next stage: {next_stage.value if next_stage else None}")
    action = package.recommended_next_action
    print(f"  recommended next action: {action.value if action else None}")
    print(f"  risk: {package.risk_score} / {package.risk_label.value}; hard blocks={[code.value for code in package.hard_blocks]}")
    print(f"  reviewer brief: {package.reviewer_brief}")
    for item in package.verification_summary:
        print(f"  verification: {item.capability} | {item.provider_name} | {item.mode.value} | {item.status.value}")


def submit_and_show(repo, request, service, submitted, label):
    recommendation = service.submit_decision(request.id, submitted)
    print(f"  {label} decision: {submitted.decision.value}; status -> {recommendation.status.value}; next_stage={recommendation.next_stage}")
    show_package(service.get_review_package(request.id))


def main():
    repo, request, service = make_case("clean supplier")
    submit_and_show(repo, request, service, decision(ApprovalStage.PROCUREMENT, "synthetic-procurement", "PROCUREMENT"), "procurement approve")
    submit_and_show(repo, request, service, decision(ApprovalStage.BUDGET_OWNER, "synthetic-budget", "BUDGET_OWNER"), "budget approve")

    repo, request, service = make_case("high-value supplier", high_value=True)
    submit_and_show(repo, request, service, decision(ApprovalStage.PROCUREMENT, "synthetic-procurement", "PROCUREMENT"), "procurement approve")
    submit_and_show(repo, request, service, decision(ApprovalStage.BUDGET_OWNER, "synthetic-budget", "BUDGET_OWNER"), "budget approve")
    submit_and_show(repo, request, service, decision(ApprovalStage.FINANCE_HEAD, "synthetic-finance", "FINANCE_HEAD"), "finance-head approve")

    repo, request, service = make_case("rejected supplier")
    submit_and_show(repo, request, service, decision(ApprovalStage.PROCUREMENT, "synthetic-procurement", "PROCUREMENT", HumanDecisionType.REJECT), "reject")

    repo, request, service = make_case("request-rework scenario")
    submit_and_show(repo, request, service, decision(ApprovalStage.PROCUREMENT, "synthetic-procurement", "PROCUREMENT", HumanDecisionType.REQUEST_REWORK), "request rework")

    repo, request, service = make_case(
        "self-approval attempt", requester="synthetic-procurement"
    )
    attempt = decision(ApprovalStage.PROCUREMENT, "synthetic-procurement", "PROCUREMENT")
    print(f"  decision submitted: {attempt.decision.value} at {attempt.stage.value}")
    try:
        service.submit_decision(request.id, attempt)
    except ApprovalError as exc:
        print(f"  denied without writes: {exc}")
    print(f"  resulting status: {repo.get_request(request.id).status}; next stage={ApprovalStage.PROCUREMENT.value}")

    repo, request, service = make_case(
        "same-person-two-stages attempt", procurement_owner="same-reviewer", budget_owner="same-reviewer"
    )
    submit_and_show(repo, request, service, decision(ApprovalStage.PROCUREMENT, "same-reviewer", "PROCUREMENT"), "procurement approve")
    attempt = decision(ApprovalStage.BUDGET_OWNER, "same-reviewer", "BUDGET_OWNER")
    print(f"  decision submitted: {attempt.decision.value} at {attempt.stage.value}")
    try:
        service.submit_decision(request.id, attempt)
    except ApprovalError as exc:
        print(f"  denied without writes: {exc}")
    print(f"  resulting status: {repo.get_request(request.id).status}; next stage={ApprovalStage.BUDGET_OWNER.value}")

    repo, request, service = make_case("blocked supplier attempting approval", blocked=True, status=WorkflowStatus.BLOCKED)
    attempt = decision(ApprovalStage.PROCUREMENT, "synthetic-procurement", "PROCUREMENT")
    print(f"  decision submitted: {attempt.decision.value} at {attempt.stage.value}")
    try:
        service.submit_decision(request.id, attempt)
    except ApprovalError as exc:
        print(f"  denied without writes: {exc}")
    print(f"  resulting status: {repo.get_request(request.id).status}; next stage={ApprovalStage.PROCUREMENT.value}")

    _, request, service = make_case("reviewer LLM failure fallback", fail_llm=True)
    package = service.get_review_package(request.id)
    print(f"  decision submitted: none; resulting status: {package.request_status.value}; next stage={package.next_recommendation.next_stage}")


if __name__ == "__main__":
    main()
