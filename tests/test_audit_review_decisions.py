from app.repositories.vendor_repository import _review_decision_audit_event


def test_rejected_review_maps_to_audit_event():
    event = _review_decision_audit_event(
        {
            "id": 12,
            "vendor_id": "vendor-1",
            "decision": "REJECT",
            "reviewer": "Reviewer",
            "comment": "Bank mismatch confirmed.",
            "created_at": "2026-10-07T08:00:00+00:00",
        },
        "Example Vendor",
    )

    assert event["event_type"] == "REVIEW_DECISION"
    assert event["action"] == "Vendor rejected by reviewer."
    assert event["details"]["decision"] == "REJECT"
    assert event["details"]["review_decision_id"] == 12
    assert event["verification_vendors"]["legal_name"] == "Example Vendor"


def test_information_request_maps_to_audit_event():
    event = _review_decision_audit_event(
        {
            "id": 13,
            "vendor_id": "vendor-2",
            "decision": "REQUEST_INFORMATION",
            "reviewer": "Reviewer",
            "comment": "Please provide a current tax certificate.",
            "created_at": "2026-10-07T08:01:00+00:00",
        }
    )

    assert event["action"] == "Reviewer requested additional information."
