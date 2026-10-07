from datetime import datetime, timezone

from supabase import Client, create_client

from app.core.config import get_settings
from app.domain.models import DocumentExtraction, HumanReviewRequest, VendorProcessResult


class VendorRepository:
    def __init__(self) -> None:
        settings = get_settings()
        self.db: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )

    async def save_result(
        self,
        result: VendorProcessResult,
        documents: list[DocumentExtraction] | None = None,
    ) -> None:
        self.db.table("verification_vendors").upsert(
            {
                "id": result.vendor_id,
                "legal_name": result.vendor_name,
                "status": result.overall_status,
                "agent_recommendation": result.recommendation,
                "reasons": result.reasons,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

        self.db.table("verification_agent_runs").insert(
            {
                "vendor_id": result.vendor_id,
                "status": result.overall_status,
                "recommendation": result.recommendation,
                "missing_documents": result.missing_documents,
                "checks": [c.model_dump(mode="json") for c in result.checks],
                "events": [e.model_dump(mode="json") for e in result.events],
            }
        ).execute()

        documents_to_save = result.extractions if documents is None else documents
        if documents_to_save:
            rows = [
                {
                    "vendor_id": result.vendor_id,
                    "filename": item.filename,
                    "document_type": item.document_type,
                    "confidence": item.confidence,
                    "extracted_data": item.model_dump(mode="json"),
                }
                for item in documents_to_save
            ]
            self.db.table("verification_vendor_documents").insert(rows).execute()

    async def list_review_queue(self) -> list[dict]:
        result = (
            self.db.table("verification_vendors")
            .select("*")
            .eq("status", "REVIEW_REQUIRED")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

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
        return {
            "vendor": vendor.data[0],
            "documents": docs.data or [],
            "agent_runs": runs.data or [],
        }

    async def save_review(
        self,
        vendor_id: str,
        review: HumanReviewRequest,
    ) -> dict:
        final_status = "APPROVED" if review.decision == "APPROVE" else "REJECTED"

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

        return updated.data[0] if updated.data else {
            "id": vendor_id,
            "status": final_status,
        }
