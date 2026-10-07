from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from supabase import Client, create_client

from app.core.config import get_settings
from app.domain.models import DocumentExtraction, HumanReviewRequest, VendorProcessResult


CHECK_SCORES = {
    "VERIFIED": 100.0,
    "REVIEW_REQUIRED": 50.0,
    "MISMATCH": 0.0,
    "NOT_FOUND": 0.0,
    "ERROR": 0.0,
}


class VendorRepository:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.db: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )

    def _audit(
        self,
        vendor_id: str,
        event_type: str,
        action: str,
        actor: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.db.table("verification_audit_events").insert(
                {
                    "vendor_id": vendor_id,
                    "event_type": event_type,
                    "actor": actor,
                    "action": action,
                    "details": details or {},
                }
            ).execute()
        except Exception:
            # Audit logging must not break the verification result. The API
            # exposes missing audit data honestly if the migration is absent.
            pass

    def _upload_file(self, vendor_id: str, item: dict) -> str | None:
        bucket = self.settings.DOCUMENT_STORAGE_BUCKET
        filename = Path(item.get("filename") or "document").name
        storage_path = f"{vendor_id}/{uuid4()}-{filename}"
        try:
            self.db.storage.from_(bucket).upload(
                storage_path,
                item["content"],
                {
                    "content-type": item.get("mime_type") or "application/octet-stream",
                    "upsert": "false",
                },
            )
            return storage_path
        except Exception:
            return None

    def _signed_url(self, storage_path: str | None) -> str | None:
        if not storage_path:
            return None
        try:
            value = self.db.storage.from_(
                self.settings.DOCUMENT_STORAGE_BUCKET
            ).create_signed_url(storage_path, 600)
            if isinstance(value, dict):
                return (
                    value.get("signedURL")
                    or value.get("signedUrl")
                    or value.get("signed_url")
                )
        except Exception:
            return None
        return None

    @staticmethod
    def _risk_level(run: dict | None) -> str | None:
        checks = (run or {}).get("checks") or []
        if not checks:
            return None
        flagged = [
            check for check in checks
            if isinstance(check, dict)
            and check.get("status") in {"REVIEW_REQUIRED", "MISMATCH", "NOT_FOUND", "ERROR"}
        ]
        if not flagged:
            return "LOW"
        if any(
            "sanctions" in str(check.get("source") or "").lower()
            and check.get("status") != "VERIFIED"
            for check in flagged
        ):
            return "HIGH"
        return "MEDIUM"

    @staticmethod
    def _derived_confidence(run: dict | None, documents: list[dict]) -> float | None:
        if run and run.get("confidence_score") is not None:
            try:
                return float(run["confidence_score"])
            except (TypeError, ValueError):
                pass

        components: list[float] = []
        confidences = [
            float(doc["confidence"]) * 100.0
            for doc in documents
            if doc.get("confidence") is not None
        ]
        if confidences:
            components.append(sum(confidences) / len(confidences))

        checks = (run or {}).get("checks") or []
        check_scores = [
            CHECK_SCORES.get(check.get("status"), 0.0)
            for check in checks
            if isinstance(check, dict)
        ]
        if check_scores:
            components.append(sum(check_scores) / len(check_scores))

        if not components:
            return None
        return round(sum(components) / len(components), 1)

    async def save_result(
        self,
        result: VendorProcessResult,
        documents: list[DocumentExtraction] | None = None,
        file_payloads: list[dict] | None = None,
        submitted_data: dict[str, Any] | None = None,
    ) -> None:
        submitted = dict(submitted_data or result.submitted_data or {})
        now = datetime.now(timezone.utc).isoformat()

        self.db.table("verification_vendors").upsert(
            {
                "id": result.vendor_id,
                "legal_name": result.vendor_name,
                "status": result.overall_status,
                "agent_recommendation": result.recommendation,
                "human_decision": None,
                "reasons": result.reasons,
                "region": submitted.get("region") or None,
                "category": submitted.get("category") or None,
                "contact_email": submitted.get("contact_email") or None,
                "compliance_confirmed": submitted.get("compliance_confirmed"),
                "submitted_by": submitted.get("submitted_by") or None,
                "submitted_data": submitted,
                "updated_at": now,
            }
        ).execute()

        run = self.db.table("verification_agent_runs").insert(
            {
                "vendor_id": result.vendor_id,
                "status": result.overall_status,
                "recommendation": result.recommendation,
                "missing_documents": result.missing_documents,
                "checks": [c.model_dump(mode="json") for c in result.checks],
                "events": [e.model_dump(mode="json") for e in result.events],
                "confidence_score": result.confidence_score,
                "scorecard": [item.model_dump(mode="json") for item in result.scorecard],
            }
        ).execute()

        payload_by_name = {
            item.get("filename"): item for item in (file_payloads or [])
        }
        documents_to_save = result.extractions if documents is None else documents
        if documents_to_save:
            rows = []
            for item in documents_to_save:
                payload = payload_by_name.get(item.filename)
                storage_path = (
                    self._upload_file(result.vendor_id, payload)
                    if payload
                    else None
                )
                rows.append(
                    {
                        "vendor_id": result.vendor_id,
                        "filename": item.filename,
                        "document_type": item.document_type,
                        "confidence": item.confidence,
                        "extracted_data": item.model_dump(mode="json"),
                        "mime_type": payload.get("mime_type") if payload else None,
                        "size_bytes": len(payload.get("content", b"")) if payload else None,
                        "storage_path": storage_path,
                    }
                )
            self.db.table("verification_vendor_documents").insert(rows).execute()

        actor = submitted.get("submitted_by") or "verification_agent"
        self._audit(
            result.vendor_id,
            "VERIFICATION_RUN",
            (
                f"Verification completed with status {result.overall_status} "
                f"and recommendation {result.recommendation}."
            ),
            actor=str(actor),
            details={
                "status": result.overall_status,
                "recommendation": result.recommendation,
                "confidence_score": result.confidence_score,
                "missing_documents": result.missing_documents,
                "agent_run_id": (run.data or [{}])[0].get("id") if run else None,
            },
        )

    async def list_vendors(
        self,
        status: str | None = None,
        query: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        vendor_query = (
            self.db.table("verification_vendors")
            .select("*")
            .order("updated_at", desc=True)
            .limit(limit)
        )
        if status:
            vendor_query = vendor_query.eq("status", status)
        vendors = vendor_query.execute().data or []

        if query:
            needle = query.strip().lower()
            vendors = [
                item
                for item in vendors
                if needle in str(item.get("legal_name") or "").lower()
                or needle in str(item.get("id") or "").lower()
            ]

        if not vendors:
            return []

        ids = [item["id"] for item in vendors]
        runs = (
            self.db.table("verification_agent_runs")
            .select("*")
            .in_("vendor_id", ids)
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
        docs = (
            self.db.table("verification_vendor_documents")
            .select("vendor_id,confidence")
            .in_("vendor_id", ids)
            .execute()
            .data
            or []
        )

        latest_run: dict[str, dict] = {}
        docs_by_vendor: dict[str, list[dict]] = {}
        for run in runs:
            latest_run.setdefault(run["vendor_id"], run)
        for doc in docs:
            docs_by_vendor.setdefault(doc["vendor_id"], []).append(doc)

        output = []
        for vendor in vendors:
            run = latest_run.get(vendor["id"])
            output.append(
                {
                    **vendor,
                    "confidence_score": self._derived_confidence(
                        run, docs_by_vendor.get(vendor["id"], [])
                    ),
                    "risk_level": self._risk_level(run),
                    "latest_run": run,
                }
            )
        return output

    async def dashboard(self) -> dict:
        vendors = await self.list_vendors(limit=1000)
        total = len(vendors)
        counts = {
            "APPROVED": 0,
            "REVIEW_REQUIRED": 0,
            "ACTION_REQUIRED": 0,
            "REJECTED": 0,
        }
        scores: list[float] = []
        latest = None

        for vendor in vendors:
            status = vendor.get("status")
            if status in counts:
                counts[status] += 1
            if vendor.get("confidence_score") is not None:
                scores.append(float(vendor["confidence_score"]))
            updated = vendor.get("updated_at")
            if updated and (latest is None or updated > latest):
                latest = updated

        threshold = self.settings.AUTO_APPROVAL_THRESHOLD
        if threshold is not None and threshold <= 1:
            threshold *= 100.0

        return {
            "total_cases": total,
            "approved_cases": counts["APPROVED"],
            "review_required_cases": counts["REVIEW_REQUIRED"],
            "action_required_cases": counts["ACTION_REQUIRED"],
            "rejected_cases": counts["REJECTED"],
            "average_confidence_score": (
                round(sum(scores) / len(scores), 1) if scores else None
            ),
            "approval_rate": (
                round(counts["APPROVED"] / total * 100.0, 1) if total else None
            ),
            "auto_approval_threshold": threshold,
            "recently_updated_at": latest,
        }

    async def list_review_queue(self) -> list[dict]:
        return await self.list_vendors(status="REVIEW_REQUIRED")

    async def list_audit_events(
        self,
        query: str | None = None,
        event_type: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        try:
            db_query = (
                self.db.table("verification_audit_events")
                .select("*,verification_vendors(legal_name)")
                .order("created_at", desc=True)
                .limit(limit)
            )
            if event_type:
                db_query = db_query.eq("event_type", event_type)
            rows = db_query.execute().data or []
        except Exception:
            return []

        if query:
            needle = query.strip().lower()
            rows = [
                row
                for row in rows
                if needle in str(row.get("vendor_id") or "").lower()
                or needle in str(row.get("actor") or "").lower()
                or needle in str(row.get("action") or "").lower()
                or needle
                in str(
                    (row.get("verification_vendors") or {}).get("legal_name") or ""
                ).lower()
            ]
        return rows

    async def get_vendor(self, vendor_id: str) -> dict | None:
        vendor = (
            self.db.table("verification_vendors")
            .select("*")
            .eq("id", vendor_id)
            .limit(1)
            .execute()
        )
        if not vendor.data:
            return None

        docs = (
            self.db.table("verification_vendor_documents")
            .select("*")
            .eq("vendor_id", vendor_id)
            .order("created_at")
            .execute()
        )
        runs = (
            self.db.table("verification_agent_runs")
            .select("*")
            .eq("vendor_id", vendor_id)
            .order("created_at", desc=True)
            .execute()
        )
        reviews = (
            self.db.table("verification_review_decisions")
            .select("*")
            .eq("vendor_id", vendor_id)
            .order("created_at", desc=True)
            .execute()
        )
        try:
            audit = (
                self.db.table("verification_audit_events")
                .select("*")
                .eq("vendor_id", vendor_id)
                .order("created_at", desc=True)
                .execute()
            )
            audit_rows = audit.data or []
        except Exception:
            audit_rows = []

        document_rows = docs.data or []
        for document in document_rows:
            document["document_url"] = self._signed_url(document.get("storage_path"))
            document["available"] = bool(document["document_url"])

        run_rows = runs.data or []
        if run_rows:
            run_rows[0]["confidence_score"] = self._derived_confidence(
                run_rows[0], document_rows
            )

        vendor_row = vendor.data[0]
        vendor_row["risk_level"] = self._risk_level(run_rows[0] if run_rows else None)
        vendor_row["last_reviewer"] = (
            (reviews.data or [{}])[0].get("reviewer")
            if reviews.data
            else None
        )

        return {
            "vendor": vendor_row,
            "documents": document_rows,
            "agent_runs": run_rows,
            "reviews": reviews.data or [],
            "audit_events": audit_rows,
        }

    async def get_document(self, vendor_id: str, document_id: int) -> dict | None:
        result = (
            self.db.table("verification_vendor_documents")
            .select("*")
            .eq("vendor_id", vendor_id)
            .eq("id", document_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None

        document = result.data[0]
        document["document_url"] = self._signed_url(document.get("storage_path"))
        document["available"] = bool(document["document_url"])
        return document

    async def save_review(
        self,
        vendor_id: str,
        review: HumanReviewRequest,
    ) -> dict:
        if review.decision == "APPROVE":
            final_status = "APPROVED"
        elif review.decision == "REQUEST_INFORMATION":
            final_status = "ACTION_REQUIRED"
        else:
            final_status = "REJECTED"

        self.db.table("verification_review_decisions").insert(
            {
                "vendor_id": vendor_id,
                "decision": review.decision,
                "reviewer": review.reviewer,
                "comment": review.comment,
            }
        ).execute()

        updated = (
            self.db.table("verification_vendors")
            .update(
                {
                    "status": final_status,
                    "human_decision": review.decision,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", vendor_id)
            .execute()
        )

        self._audit(
            vendor_id,
            "HUMAN_REVIEW",
            f"Reviewer decision: {review.decision}.",
            actor=review.reviewer,
            details={"decision": review.decision, "comment": review.comment},
        )

        return updated.data[0] if updated.data else {
            "id": vendor_id,
            "status": final_status,
        }
