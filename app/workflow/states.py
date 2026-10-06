from enum import StrEnum


class WorkflowStatus(StrEnum):
    DRAFT = "DRAFT"
    DOCUMENTS_UPLOADED = "DOCUMENTS_UPLOADED"
    EXTRACTED = "EXTRACTED"
    PENDING_FIELD_REVIEW = "PENDING_FIELD_REVIEW"
    VALIDATED = "VALIDATED"
    PENDING_PROCUREMENT = "PENDING_PROCUREMENT"
    PENDING_BUDGET = "PENDING_BUDGET"
    PENDING_FINANCE_HEAD = "PENDING_FINANCE_HEAD"
    APPROVED = "APPROVED"
    DRAFTS_GENERATED = "DRAFTS_GENERATED"
    REWORK = "REWORK"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"


TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: frozenset({WorkflowStatus.DOCUMENTS_UPLOADED}),
    WorkflowStatus.DOCUMENTS_UPLOADED: frozenset(
        {WorkflowStatus.EXTRACTED, WorkflowStatus.NEEDS_MANUAL_REVIEW}
    ),
    WorkflowStatus.EXTRACTED: frozenset(
        {WorkflowStatus.PENDING_FIELD_REVIEW, WorkflowStatus.VALIDATED, WorkflowStatus.NEEDS_MANUAL_REVIEW}
    ),
    WorkflowStatus.PENDING_FIELD_REVIEW: frozenset(
        {WorkflowStatus.VALIDATED, WorkflowStatus.NEEDS_MANUAL_REVIEW}
    ),
    WorkflowStatus.VALIDATED: frozenset(
        {WorkflowStatus.PENDING_PROCUREMENT, WorkflowStatus.REWORK, WorkflowStatus.BLOCKED}
    ),
    WorkflowStatus.PENDING_PROCUREMENT: frozenset(
        {WorkflowStatus.PENDING_BUDGET, WorkflowStatus.REWORK, WorkflowStatus.REJECTED}
    ),
    WorkflowStatus.PENDING_BUDGET: frozenset(
        {
            WorkflowStatus.PENDING_FINANCE_HEAD,
            WorkflowStatus.APPROVED,
            WorkflowStatus.REWORK,
            WorkflowStatus.REJECTED,
        }
    ),
    WorkflowStatus.PENDING_FINANCE_HEAD: frozenset(
        {WorkflowStatus.APPROVED, WorkflowStatus.REWORK, WorkflowStatus.REJECTED}
    ),
    WorkflowStatus.APPROVED: frozenset({WorkflowStatus.DRAFTS_GENERATED}),
    WorkflowStatus.REWORK: frozenset({WorkflowStatus.DOCUMENTS_UPLOADED}),
    WorkflowStatus.NEEDS_MANUAL_REVIEW: frozenset(
        {WorkflowStatus.EXTRACTED, WorkflowStatus.DOCUMENTS_UPLOADED}
    ),
    WorkflowStatus.BLOCKED: frozenset({WorkflowStatus.REJECTED, WorkflowStatus.REWORK}),
    WorkflowStatus.REJECTED: frozenset(),
    WorkflowStatus.DRAFTS_GENERATED: frozenset(),
}


def can_transition(a: WorkflowStatus | str, b: WorkflowStatus | str) -> bool:
    try:
        source, target = WorkflowStatus(a), WorkflowStatus(b)
    except ValueError:
        return False
    return target in TRANSITIONS[source]


def assert_transition(a: WorkflowStatus | str, b: WorkflowStatus | str) -> None:
    if not can_transition(a, b):
        raise ValueError(f"Invalid workflow transition: {a} -> {b}")
