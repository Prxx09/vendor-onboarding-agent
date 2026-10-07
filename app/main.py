from __future__ import annotations

from pathlib import Path
from typing import Any
import json
from urllib.parse import quote
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.data import (
    APPROVAL_THRESHOLD,
    add_audit,
    create_case_from_intake,
    find_case,
    list_audit,
    list_cases,
)
from app.workflow import simulate_document_extraction
from app.extraction import SUPPORTED_EXTENSIONS, extract_documents
from app import storage

load_dotenv()
LOCAL_FILES: dict[tuple[str, str], tuple[bytes, str, str]] = {}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_SIZE = 30 * 1024 * 1024
MAX_DOCUMENTS = 8

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Vendor Onboarding Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class IntakePayload(BaseModel):
    legal_name: str
    tax_id: str
    pan: str
    bank_account: str
    ifsc: str
    registered_address: str
    contact_email: str
    category: str = "General"
    region: str = "India"
    submitted_by: str = "Portal User"
    document_name: str = "uploaded-vendor-document.pdf"
    compliance_confirmed: bool = True
    extraction_confidence: int | None = None


class DecisionPayload(BaseModel):
    decision: str
    reviewer: str = "Reviewer"
    notes: str = ""


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "vendor-onboarding-agent",
        "storage": "supabase" if storage.configured() else "local-memory",
    }


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "approval_threshold": APPROVAL_THRESHOLD,
        "upload_limits": {
            "max_documents": MAX_DOCUMENTS,
            "max_file_size_bytes": MAX_FILE_SIZE,
            "max_total_size_bytes": MAX_TOTAL_SIZE,
        },
        "workflow": [
            "Upload document",
            "Extract text and OCR",
            "Auto-populate form with confidence",
            "Manual correction",
            "Submit intake",
            "Validation scoring",
            "Auto approve or human review",
            "Audit logging",
        ],
        "storage": {
            "active": "supabase" if storage.configured() else "local-memory",
            "migration_ready": True,
            "supabase_tables": [
                "onboarding_cases",
                "case_documents",
                "validation_checks",
                "approval_steps",
                "audit_events",
            ],
        },
    }


@app.get("/api/storage/status")
def storage_status() -> dict[str, Any]:
    return {
        "active": "supabase" if storage.configured() else "local-memory",
        "message": "Supabase persistence is enabled." if storage.configured() else
                   "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to enable Supabase persistence.",
    }


@app.get("/api/demo-cases")
def demo_cases() -> list[dict[str, Any]]:
    cases = list_cases()
    if storage.configured():
        try:
            known = {item["id"] for item in cases}
            cases.extend(item for item in storage.list_cases() if item["id"] not in known)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return sorted(cases, key=lambda item: item["submitted_at"], reverse=True)


@app.get("/api/demo-cases/{case_id}")
def demo_case(case_id: str) -> dict[str, Any]:
    case = find_case(case_id)
    if case and not case.get("submitted_form"):
        case = next(item for item in list_cases() if item["id"] == case_id)
    if case and storage.configured():
        try:
            stored = storage.find_case(case_id)
            if stored:
                case = {**case, "submitted_form": stored["submitted_form"],
                        "documents": stored["documents"]}
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not case and storage.configured():
        try:
            case = storage.find_case(case_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.get("/api/audit-events")
def audit_events(case_id: str | None = None) -> list[dict[str, Any]]:
    return list_audit(case_id)


@app.post("/api/intake/submit")
async def submit_intake(request: Request) -> dict[str, Any]:
    if "multipart/form-data" in request.headers.get("content-type", ""):
        form = await request.form()
        try:
            payload = IntakePayload.model_validate(json.loads(str(form["payload"])))
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Invalid intake form") from exc
        uploads = [item for item in form.getlist("files") if hasattr(item, "read")]
        # Backwards compatibility for clients using the original single-file field.
        if not uploads and hasattr(form.get("file"), "read"):
            uploads = [form.get("file")]
        documents = [(
            upload.filename or "vendor-document.pdf",
            await upload.read(),
            upload.content_type or "application/octet-stream",
        ) for upload in uploads]
    else:
        payload = IntakePayload.model_validate(await request.json())
        documents = []
    _validate_documents(documents, required=storage.configured())
    values = payload.model_dump()
    values["document_names"] = [name for name, _, _ in documents]
    if documents:
        values["document_name"] = documents[0][0]
    if storage.configured():
        values["case_id"] = "VO-" + uuid4().hex[:10].upper()
    case = create_case_from_intake(values)
    if storage.configured():
        try:
            storage.save_intake(case, payload.model_dump(), documents)
            case["documents"] = storage.find_case(case["id"])["documents"]
        except Exception as exc:
            from app.data import DEMO_CASES, AUDIT_EVENTS
            DEMO_CASES[:] = [item for item in DEMO_CASES if item["id"] != case["id"]]
            AUDIT_EVENTS[:] = [item for item in AUDIT_EVENTS if item["case_id"] != case["id"]]
            raise HTTPException(status_code=503, detail=f"Case was not stored: {exc}") from exc
    elif documents:
        for index, (name, content, mime) in enumerate(documents):
            document_id = f"source-document-{index + 1}"
            LOCAL_FILES[(case["id"], document_id)] = (content, mime, name)
        for document in case["documents"]:
            document["available"] = True
        find_case(case["id"])["documents"] = case["documents"]
    return case


@app.get("/api/demo-cases/{case_id}/documents/{document_id}")
def open_document(case_id: str, document_id: str):
    if storage.configured():
        try:
            key = case_id[3:] if case_id.startswith("SD-") else case_id
            url = storage.document_url(key, document_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if url:
            return RedirectResponse(url)
    case = find_case(case_id)
    local_document = LOCAL_FILES.get((case_id, document_id))
    if case and local_document:
        content, mime, name = local_document
        return Response(content, media_type=mime, headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}"})
    raise HTTPException(status_code=404, detail="Document file is not available")


@app.post("/api/demo-cases/{case_id}/decision")
def decide_case(case_id: str, payload: DecisionPayload) -> dict[str, Any]:
    case = find_case(case_id)
    normalized = payload.decision.upper()
    if normalized not in {"APPROVED", "REJECTED", "NEEDS_INFO"}:
        raise HTTPException(status_code=400, detail="Decision must be APPROVED, REJECTED, or NEEDS_INFO")
    if not case and storage.configured():
        try:
            updated = storage.save_decision(case_id, normalized, payload.reviewer)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if updated:
            add_audit(case_id, payload.reviewer, f"HUMAN_{normalized}",
                      payload.notes or f"Reviewer marked case as {normalized}.")
            return updated
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if storage.configured():
        try:
            storage.save_decision(case_id, normalized, payload.reviewer)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    case["status"] = normalized
    case["assigned_to"] = payload.reviewer
    add_audit(
        case_id,
        payload.reviewer,
        f"HUMAN_{normalized}",
        payload.notes or f"Reviewer marked case as {normalized}.",
    )
    return case


def _validate_documents(documents: list[tuple[str, bytes, str]], required: bool = True) -> None:
    if required and not documents:
        raise HTTPException(status_code=422, detail="Upload at least one vendor document")
    if len(documents) > MAX_DOCUMENTS:
        raise HTTPException(status_code=413, detail=f"A maximum of {MAX_DOCUMENTS} documents is allowed")
    if sum(len(content) for _, content, _ in documents) > MAX_TOTAL_SIZE:
        raise HTTPException(status_code=413, detail="Combined documents exceed 30 MB")
    for name, content, _ in documents:
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"{name} exceeds 10 MB")
        if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported document type: {name}")


@app.post("/api/upload/extract")
async def extract_uploads(
    files: list[UploadFile] = File(...),
    category: str = Form("General"),
) -> dict[str, Any]:
    documents = [(
        upload.filename or "vendor-document.pdf",
        await upload.read(),
        upload.content_type or "application/octet-stream",
    ) for upload in files]
    _validate_documents(documents)
    try:
        result = extract_documents([(name, content) for name, content, _ in documents])
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **result,
        "category": category,
        "message": "Document extraction completed. Review low-confidence or missing fields before submission.",
    }


@app.post("/api/upload/simulate", deprecated=True)
async def simulate_upload(file: UploadFile = File(...), category: str = Form("General")) -> dict[str, Any]:
    """Compatibility endpoint retained for older frontend builds."""
    content = await file.read()
    try:
        result = extract_documents([(file.filename or "vendor-document.pdf", content)])
        return {**result, "document_name": file.filename, "category": category}
    except Exception:
        return simulate_document_extraction(file.filename or "vendor-document.pdf", category)
