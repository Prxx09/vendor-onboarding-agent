from __future__ import annotations

import sys
from uuid import uuid4

from app.config import get_settings
from app.repositories.supabase_repo import SupabaseRepository
from app.schemas.domain import RequestType, VendorRequest

EXPECTED_TABLES = (
    "vendor_requests",
    "documents",
    "extracted_fields",
    "validation_findings",
    "risk_assessments",
    "approvals",
    "audit_events",
    "agent_runs",
    "vendors",
    "sanctions_entries",
    "vendor_drafts",
    "po_drafts",
)


def report(label: str, passed: bool, detail: str = "") -> bool:
    print(f"{'PASS' if passed else 'FAIL'}: {label}{': ' + detail if detail else ''}")
    return passed


def main() -> int:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        report("configuration", False, "set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        return 1
    try:
        repository = SupabaseRepository(settings)
    except Exception as exc:  # noqa: BLE001 - report SDK/configuration failure without secrets
        report("client configuration", False, type(exc).__name__)
        return 1

    passed = True
    for table in EXPECTED_TABLES:
        try:
            repository.client.table(table).select("id").limit(1).execute()
            result = report(f"table {table}", True)
        except Exception as exc:  # noqa: BLE001 - each failed table check is reported
            result = report(f"table {table}", False, type(exc).__name__)
        passed = result and passed

    try:
        buckets = repository.client.storage.list_buckets()
        bucket_by_name = {
            bucket.get("name") if isinstance(bucket, dict) else getattr(bucket, "name", None): bucket
            for bucket in buckets
        }
        target_bucket = bucket_by_name.get("vendor-documents")
        is_private = (
            target_bucket.get("public") is False
            if isinstance(target_bucket, dict)
            else target_bucket is not None and getattr(target_bucket, "public", None) is False
        )
        result = report(
            "private vendor-documents bucket",
            target_bucket is not None and is_private,
            "bucket is absent, public, or inaccessible" if not is_private else "",
        )
    except Exception as exc:  # noqa: BLE001 - report storage SDK failure
        result = report("private vendor-documents bucket", False, type(exc).__name__)
    passed = result and passed

    request_id = None
    try:
        request = repository.create_request(
            VendorRequest(
                id=str(uuid4()),
                request_type=RequestType.NEW_SUPPLIER,
                supplier_name="Synthetic Supabase connectivity check",
                is_demo=True,
            )
        )
        request_id = request.id
        report("create request", True)
        updated = repository.set_request_status(
            request.id,
            "DOCUMENTS_UPLOADED",
            "check_supabase.py",
            "connectivity round trip",
        )
        result = report("status transition", updated.status == "DOCUMENTS_UPLOADED")
        passed = result and passed
        audit_events = repository.list_audit_events(request.id)
        status_event = next(
            (event for event in audit_events if event.event_type == "REQUEST_STATUS_CHANGED"),
            None,
        )
        result = report("audit event round trip", status_event is not None)
        passed = result and passed
        deletion_blocked = False
        if status_event is not None:
            try:
                repository.client.table("audit_events").delete().eq("id", status_event.id).execute()
            except Exception:  # noqa: BLE001 - a database trigger rejection is expected here
                deletion_blocked = True
            still_there = any(
                event.id == status_event.id for event in repository.list_audit_events(request.id)
            )
            deletion_blocked = deletion_blocked and still_there
        result = report("audit events cannot be deleted", deletion_blocked)
        passed = result and passed
    except Exception as exc:  # noqa: BLE001 - report round-trip failure without response details
        result = report("request/audit round trip", False, type(exc).__name__)
        passed = result and passed
    finally:
        # audit_events are intentionally append-only. Because the audit event
        # references vendor_requests with ON DELETE SET NULL, deleting the
        # temporary request would require mutating the audit row and is therefore
        # correctly rejected by the append-only trigger.
        if request_id:
            report(
                "temporary request cleanup",
                True,
                "skipped: audit trail is append-only",
            )

    print("Supabase check: PASS" if passed else "Supabase check: FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
