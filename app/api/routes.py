import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.agent.vendor_agent import REQUIRED_DOCUMENTS, VendorVerificationAgent
from app.core.config import get_settings
from app.domain.models import DocumentExtraction, HumanReviewRequest, VendorProcessResult
from app.ocr.factory import get_ocr_provider
from app.providers.factory import get_verification_provider
from app.repositories.vendor_repository import VendorRepository
from app.services.document_processor import DocumentProcessor
from app.services.groq_extractor import GroqDocumentExtractor


router = APIRouter(prefix="/api/v1", tags=["vendor-onboarding"])


def _repository() -> VendorRepository:
    return VendorRepository()


def _agent() -> VendorVerificationAgent:
    return VendorVerificationAgent(
        document_processor=DocumentProcessor(get_ocr_provider()),
        extractor=GroqDocumentExtractor(),
        provider=get_verification_provider(),
        repository=_repository(),
    )


def _csv_values(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _upload_policy() -> dict[str, Any]:
    settings = get_settings()
    return {
        "supported_mime_types": [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
        ],
        "supported_extensions": [".pdf", ".png", ".jpg", ".jpeg", ".webp"],
        "max_files": settings.MAX_UPLOAD_FILES,
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "max_combined_size_mb": settings.MAX_COMBINED_UPLOAD_MB,
    }


async def _read_uploads(files: list[UploadFile]) -> list[dict]:
    settings = get_settings()
    policy = _upload_policy()

    if not files:
        raise HTTPException(status_code=400, detail="At least one document is required.")
    if len(files) > settings.MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {settings.MAX_UPLOAD_FILES} documents are allowed per request.",
        )

    payloads: list[dict] = []
    combined = 0
    max_file_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    max_combined_bytes = settings.MAX_COMBINED_UPLOAD_MB * 1024 * 1024

    for upload in files:
        mime_type = upload.content_type or "application/octet-stream"
        if mime_type not in policy["supported_mime_types"]:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type for {upload.filename}: {mime_type}",
            )

        content = await upload.read()
        combined += len(content)
        if len(content) > max_file_bytes:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{upload.filename} exceeds the configured "
                    f"{settings.MAX_FILE_SIZE_MB} MB file limit."
                ),
            )
        if combined > max_combined_bytes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Combined upload size exceeds the configured "
                    f"{settings.MAX_COMBINED_UPLOAD_MB} MB limit."
                ),
            )

        payloads.append(
            {
                "filename": upload.filename or "document",
                "mime_type": mime_type,
                "content": content,
            }
        )

    return payloads


def _clean_submitted_data(**values: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, str):
            value = value.strip()
            if value:
                data[key] = value
        elif value is not None:
            data[key] = value
    return data


@router.get("/config")
async def frontend_config():
    settings = get_settings()
    threshold = settings.AUTO_APPROVAL_THRESHOLD
    if threshold is not None and threshold <= 1:
        threshold *= 100.0
    return {
        "upload": _upload_policy(),
        "verification": {
            "required_documents": REQUIRED_DOCUMENTS,
            "required_intake_fields": _csv_values(settings.REQUIRED_INTAKE_FIELDS),
            "auto_approval_threshold": threshold,
        },
        "intake": {
            "regions": _csv_values(settings.VENDOR_REGIONS),
            "categories": _csv_values(settings.VENDOR_CATEGORIES),
        },
    }


@router.get("/dashboard")
async def dashboard():
    return await _repository().dashboard()


@router.get("/vendors")
async def list_vendors(
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
):
    return await _repository().list_vendors(status=status, query=query)


@router.get("/audit-events")
async def audit_events(
    query: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
):
    return await _repository().list_audit_events(query=query, event_type=event_type)


@router.post("/documents/extract")
async def extract_documents(files: list[UploadFile] = File(...)):
    payloads = await _read_uploads(files)
    processor = DocumentProcessor(get_ocr_provider())
    extractor = GroqDocumentExtractor()

    async def extract_one(item: dict):
        document_text = await processor.extract_text(
            filename=item["filename"],
            mime_type=item["mime_type"],
            content=item["content"],
        )
        structured = await extractor.extract(
            filename=item["filename"],
            raw_text=document_text.text,
        )
        return structured, document_text

    results = await asyncio.gather(
        *(extract_one(item) for item in payloads),
        return_exceptions=True,
    )

    extractions: list[DocumentExtraction] = []
    errors: list[dict] = []
    for item, result in zip(payloads, results):
        if isinstance(result, Exception):
            errors.append({"filename": item["filename"], "message": str(result)})
        else:
            extraction, document_text = result
            payload = extraction.model_dump(mode="json")
            payload["extraction_method"] = document_text.method
            payload["page_count"] = document_text.page_count
            extractions.append(extraction)

    field_map = {
        "legal_name": "legal_name",
        "tax_id": "tax_id",
        "pan": "pan",
        "bank_account": "bank_account_number",
        "ifsc": "ifsc_swift",
        "registered_address": "registered_address",
    }
    suggestions: dict[str, dict[str, Any]] = {}

    for output in extractions:
        for target, source_field in field_map.items():
            value = getattr(output, source_field, None)
            if value and target not in suggestions:
                suggestions[target] = {
                    "value": value,
                    "confidence": output.field_confidence.get(
                        source_field, output.confidence
                    ),
                    "source": output.filename,
                }

    settings = get_settings()
    required_fields = _csv_values(settings.REQUIRED_INTAKE_FIELDS)
    missing_required_fields = [
        field
        for field in required_fields
        if field != "compliance_confirmed" and not suggestions.get(field)
    ]

    return {
        "documents": [
            output.model_dump(mode="json") for output in extractions
        ],
        "field_suggestions": suggestions,
        "missing_required_fields": missing_required_fields,
        "errors": errors,
    }


@router.post("/vendors/process", response_model=VendorProcessResult)
async def process_vendor(
    files: list[UploadFile] = File(...),
    legal_name: str = Form(default=""),
    tax_id: str = Form(default=""),
    pan: str = Form(default=""),
    bank_account: str = Form(default=""),
    ifsc: str = Form(default=""),
    registered_address: str = Form(default=""),
    contact_email: str = Form(default=""),
    category: str = Form(default=""),
    region: str = Form(default=""),
    submitted_by: str = Form(default=""),
    compliance_confirmed: bool | None = Form(default=None),
):
    payloads = await _read_uploads(files)
    submitted_data = _clean_submitted_data(
        legal_name=legal_name,
        tax_id=tax_id,
        pan=pan,
        bank_account=bank_account,
        ifsc=ifsc,
        registered_address=registered_address,
        contact_email=contact_email,
        category=category,
        region=region,
        submitted_by=submitted_by,
        compliance_confirmed=compliance_confirmed,
    )
    return await _agent().run(
        legal_name=legal_name,
        files=payloads,
        submitted_data=submitted_data,
    )


@router.post("/vendors/{vendor_id}/documents", response_model=VendorProcessResult)
async def add_vendor_documents(
    vendor_id: str,
    files: list[UploadFile] = File(...),
):
    repository = _repository()
    detail = await repository.get_vendor(vendor_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Vendor not found.")

    current_status = detail["vendor"].get("status")
    if current_status != "ACTION_REQUIRED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Documents can only be added to an ACTION_REQUIRED vendor. "
                f"Current status: {current_status}"
            ),
        )

    payloads = await _read_uploads(files)
    existing_extractions = [
        DocumentExtraction.model_validate(document["extracted_data"])
        for document in detail.get("documents", [])
    ]

    submitted_data = detail["vendor"].get("submitted_data") or {}
    return await _agent().run(
        legal_name=detail["vendor"].get("legal_name", ""),
        files=payloads,
        vendor_id=vendor_id,
        existing_extractions=existing_extractions,
        submitted_data=submitted_data,
    )


@router.get("/vendors/review-queue")
async def review_queue():
    return await _repository().list_review_queue()


@router.get("/vendors/{vendor_id}")
async def vendor_detail(vendor_id: str):
    result = await _repository().get_vendor(vendor_id)
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return result


@router.post("/vendors/{vendor_id}/review")
async def review_vendor(vendor_id: str, review: HumanReviewRequest):
    vendor = await _repository().get_vendor(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found.")

    current_status = vendor["vendor"].get("status")
    if current_status != "REVIEW_REQUIRED":
        raise HTTPException(
            status_code=409,
            detail=f"Vendor is not in review queue. Current status: {current_status}",
        )

    if review.decision in {"REJECT", "REQUEST_INFORMATION"} and not review.comment.strip():
        raise HTTPException(
            status_code=422,
            detail="Reviewer notes are required for rejection or information requests.",
        )
    if not review.reviewer.strip():
        raise HTTPException(status_code=422, detail="Reviewer name is required.")

    return await _repository().save_review(vendor_id, review)
