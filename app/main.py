from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
        "storage": "local-memory",
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
            "active": "local-memory",
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
        "active": "local-memory",
        "message": "Frontend and backend run together locally. Supabase migrations are included for hosted persistence.",
    }


@app.get("/api/demo-cases")
def demo_cases() -> list[dict[str, Any]]:
    return list_cases()


@app.get("/api/demo-cases/{case_id}")
def demo_case(case_id: str) -> dict[str, Any]:
    case = find_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.get("/api/audit-events")
def audit_events(case_id: str | None = None) -> list[dict[str, Any]]:
    return list_audit(case_id)


@app.post("/api/intake/submit")
def submit_intake(payload: IntakePayload) -> dict[str, Any]:
    return create_case_from_intake(payload.model_dump())


@app.post("/api/demo-cases/{case_id}/decision")
def decide_case(case_id: str, payload: DecisionPayload) -> dict[str, Any]:
    case = find_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    normalized = payload.decision.upper()
    if normalized not in {"APPROVED", "REJECTED", "NEEDS_INFO"}:
        raise HTTPException(status_code=400, detail="Decision must be APPROVED, REJECTED, or NEEDS_INFO")

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
