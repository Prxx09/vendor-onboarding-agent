import hashlib

from app.agents.document_understanding import DocumentInput, DocumentUnderstandingAgent
from app.repositories.base import OnboardingRepository
from app.repositories.storage import DocumentStorage
from app.rules.document_fields import DocumentType
from app.schemas.common import AgentResult
from app.schemas.domain import (
    ActorType,
    AgentRun,
    AuditEvent,
    Document,
    ExtractedFieldRecord,
    ExtractedStatus,
    ReviewStatus,
)
from app.schemas.extraction import ExtractedField, ExtractionResult
from app.tools.pdf_text import assess_text_quality, extract_tables_text, extract_text
from app.tools.text_cleaning import clean_text


class ExtractionService:
    def __init__(
        self,
        repo: OnboardingRepository,
        agent: DocumentUnderstandingAgent,
        storage: DocumentStorage,
    ) -> None:
        self.repo = repo
        self.agent = agent
        self.storage = storage

    def extract_document(self, document_id: str) -> AgentResult[ExtractionResult]:
        document = self._get_document(document_id)
        text = document.text_content
        quality = document.text_quality
        if not text:
            raw = self.storage.download(document.storage_path)
            extracted = extract_text(raw)
            text = extracted.text
            quality_obj = extracted.quality
            if (
                not quality_obj.usable
                and document.doc_type.upper() in {"BANK_DOCUMENT", "QUOTATION"}
                and document.file_name.lower().endswith(".pdf")
            ):
                table_text = extract_tables_text(raw)
                if table_text:
                    combined = clean_text(f"{text}\n\n{table_text}")
                    table_quality = assess_text_quality(combined)
                    if table_quality.label_hits > quality_obj.label_hits:
                        text, quality_obj = combined, table_quality
            quality = quality_obj.model_dump(mode="json") | {"needs_ocr": not quality_obj.usable}
            self.repo.update_document_text(document.id, text, quality)

        text = clean_text(text)
        if quality is None:
            quality = assess_text_quality(text).model_dump(mode="json")
            self.repo.update_document_text(document.id, text, quality)
        try:
            declared_type = DocumentType(document.doc_type.upper())
        except ValueError:
            declared_type = None
        if declared_type == DocumentType.UNKNOWN:
            declared_type = None
        result = self.agent.run(
            DocumentInput(
                document_id=document.id,
                file_name=document.file_name,
                text=text,
                declared_type=declared_type,
            )
        )
        extracted_fields = self._to_records(document, result.data)
        if result.data is not None:
            self.repo.save_extracted_fields(document.request_id, document.id, extracted_fields)

        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.repo.save_agent_run(
            AgentRun(
                request_id=document.request_id,
                agent_name=result.agent_name,
                status=result.status.value,
                input_hash=digest,
                output=result.data.model_dump(mode="json") if result.data else None,
                error=result.error,
                duration_ms=result.duration_ms,
            )
        )
        self.repo.append_audit_event(
            AuditEvent(
                request_id=document.request_id,
                actor=self.agent.name,
                actor_type=ActorType.AGENT,
                event_type="DOCUMENT_EXTRACTION_COMPLETED",
                details={
                    "document_id": document.id,
                    "status": result.status.value,
                    "field_count": len(extracted_fields),
                    "text_quality": quality,
                    "error": result.error,
                },
            )
        )
        return result

    def _get_document(self, document_id: str) -> Document:
        document = self.repo.get_document(document_id)
        if document is None:
            raise KeyError(f"Document not found: {document_id}")
        return document

    @staticmethod
    def _to_records(
        document: Document, result: ExtractionResult | None
    ) -> list[ExtractedFieldRecord]:
        if result is None:
            return []
        fields: list[ExtractedField] = list(result.fields)
        for index, item in enumerate(result.line_items):
            fields.extend(
                (
                    item.description.model_copy(update={"name": f"line_items[{index}].description"}),
                    item.quantity.model_copy(update={"name": f"line_items[{index}].quantity"}),
                    item.unit_price.model_copy(update={"name": f"line_items[{index}].unit_price"}),
                    item.tax.model_copy(update={"name": f"line_items[{index}].tax"}),
                )
            )
        return [
            ExtractedFieldRecord(
                request_id=document.request_id,
                document_id=document.id,
                field_name=field.name,
                value=field.value,
                confidence=field.confidence,
                status=ExtractedStatus(field.status.value),
                evidence=field.evidence.model_dump(mode="json") if field.evidence else None,
                review_status=ReviewStatus.PENDING,
            )
            for field in fields
        ]
