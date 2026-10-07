from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.agent.vendor_agent import VendorVerificationAgent
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


async def _read_uploads(files: list[UploadFile]) -> list[dict]:
    if not files:
        raise HTTPException(status_code=400, detail="At least one document is required.")

    payloads: list[dict] = []
    supported = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
    }

    for upload in files:
        mime_type = upload.content_type or "application/octet-stream"
        if mime_type not in supported:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type for {upload.filename}: {mime_type}",
            )

        content = await upload.read()
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename} exceeds the 20 MB prototype limit.",
            )

        payloads.append(
            {
                "filename": upload.filename or "document",
                "mime_type": mime_type,
                "content": content,
            }
        )

    return payloads


@router.post("/vendors/process", response_model=VendorProcessResult)
async def process_vendor(
    legal_name: str = Form(default=""),
    files: list[UploadFile] = File(...),
):
    payloads = await _read_uploads(files)
    return await _agent().run(legal_name=legal_name, files=payloads)


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

    return await _agent().run(
        legal_name=detail["vendor"].get("legal_name", ""),
        files=payloads,
        vendor_id=vendor_id,
        existing_extractions=existing_extractions,
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

    return await _repository().save_review(vendor_id, review)
