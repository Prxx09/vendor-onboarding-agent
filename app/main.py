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
from app import storage

load_dotenv()
LOCAL_FILES: dict[str, tuple[bytes, str]] = {}

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
        "workflow": [
            "Upload document",
            "Auto-populate form",
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
        uploaded = form.get("file")
        content = await uploaded.read() if hasattr(uploaded, "read") else b""
        mime = uploaded.content_type if hasattr(uploaded, "content_type") else "application/octet-stream"
    else:
        payload = IntakePayload.model_validate(await request.json())
        content, mime = b"", "application/octet-stream"
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Document exceeds 10 MB")
    values = payload.model_dump()
    if storage.configured():
        values["case_id"] = "VO-" + uuid4().hex[:10].upper()
    case = create_case_from_intake(values)
    if storage.configured():
        try:
            if not content:
                raise ValueError("A document is required for Supabase persistence")
            storage.save_intake(case, payload.model_dump(), content, mime)
            case["documents"] = storage.find_case(case["id"])["documents"]
        except Exception as exc:
            from app.data import DEMO_CASES, AUDIT_EVENTS
            DEMO_CASES[:] = [item for item in DEMO_CASES if item["id"] != case["id"]]
            AUDIT_EVENTS[:] = [item for item in AUDIT_EVENTS if item["case_id"] != case["id"]]
            raise HTTPException(status_code=503, detail=f"Case was not stored: {exc}") from exc
    elif content:
        LOCAL_FILES[case["id"]] = (content, mime)
        case["documents"][0]["available"] = True
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
    if case and document_id == "source-document" and case_id in LOCAL_FILES:
        content, mime = LOCAL_FILES[case_id]
        return Response(content, media_type=mime, headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(case['document'])}"})
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


@app.post("/api/upload/simulate")
async def simulate_upload(
    file: UploadFile = File(...),
    category: str = Form("General"),
) -> dict[str, Any]:
    filename = file.filename or "vendor-document.pdf"
    return simulate_document_extraction(filename, category)
