import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.rules.config import RulesConfig
from app.rules.document_fields import DocumentType
from app.schemas.domain import Document, ExtractedFieldRecord, SanctionsEntry, Vendor, VendorRequest

_BANK_REFERENCE_PATH = Path(__file__).resolve().parents[3] / "data" / "reference" / "banks.json"
with _BANK_REFERENCE_PATH.open(encoding="utf-8") as reference_file:
    BANK_REFERENCE: dict[str, Any] = json.load(reference_file)


@dataclass
class ValidationContext:
    request: VendorRequest
    extracted_fields: dict[DocumentType, list[ExtractedFieldRecord]]
    existing_vendors: list[Vendor]
    sanctions_entries: list[SanctionsEntry]
    rules_config: RulesConfig = field(default_factory=RulesConfig)
    today: date = field(default_factory=date.today)
    documents: list[Document] = field(default_factory=list)
    bank_reference: dict[str, Any] = field(default_factory=lambda: BANK_REFERENCE)

    def fields(self, document_type: DocumentType, field_name: str) -> list[ExtractedFieldRecord]:
        return [
            item
            for item in self.extracted_fields.get(document_type, [])
            if item.field_name == field_name
        ]

    def field(self, document_type: DocumentType, field_name: str) -> ExtractedFieldRecord | None:
        fields = self.fields(document_type, field_name)
        return fields[-1] if fields else None

    def doc(self, document_type: DocumentType) -> Document | None:
        return next(
            (doc for doc in self.documents if doc.doc_type.upper() == document_type.value),
            None,
        )
