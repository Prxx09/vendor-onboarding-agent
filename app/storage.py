"""Supabase-backed case and document access. Server-side credentials only."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


BUCKET = "vendor-documents"


def configured() -> bool:
    return bool(
        os.getenv("SUPABASE_URL")
        and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )


def _request(path: str, method: str = "GET", payload=None, headers=None):
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    base = os.environ["SUPABASE_URL"].rstrip("/")
    body = (
        None
        if payload is None
        else (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode()
        )
    )

    request = Request(
        base + path,
        data=body,
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            **(
                {"Content-Type": "application/json"}
                if body is not None and not isinstance(payload, bytes)
                else {}
            ),
            **(headers or {}),
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(
            f"Supabase {method} failed ({exc.code}): {detail}"
        ) from exc


def _rows(table: str, params: dict):
    return _request(
        "/rest/v1/" + table + "?" + urlencode(params, safe="*,().")
    ) or []


def _documents(row: dict) -> list[dict]:
    docs = row.get("case_documents")

    if docs is None:
        docs = _rows(
            "case_documents",
            {
                "select": (
                    "id,file_name,document_type,mime_type,"
                    "storage_path,created_at"
                ),
                "case_id": "eq." + row["id"],
                "order": "created_at.asc",
            },
        )

    return [
        {
            "id": doc["id"],
            "name": doc["file_name"],
            "type": doc["document_type"],
            "mime_type": doc["mime_type"],
            "uploaded_at": doc["created_at"],
            "available": bool(doc["storage_path"]),
        }
        for doc in docs
    ]


def map_case(row: dict) -> dict:
    raw = row.get("raw_request") or {}
    supplier = raw.get("supplier") or raw.get("form") or {}
    purchase = raw.get("purchase") or {}

    status = row["status"]

    mapped_status = {
        "BLOCKED": "REJECTED",
        "REWORK": "NEEDS_INFO",
        "PENDING_PROCUREMENT": "HUMAN_REVIEW",
        "PENDING_FINANCE_HEAD": "HUMAN_REVIEW",
    }.get(status, status)

    checks = row.get("validation_checks")

    if checks is None:
        checks = _rows(
            "validation_checks",
            {
                "select": "check_name,result,score,message",
                "case_id": "eq." + row["id"],
                "order": "evaluated_at.asc",
            },
        )

    result = []

    for check in checks:
        label = str(check["result"]).upper()

        result.append(
            {
                "name": check["check_name"],
                "result": (
                    "Pass"
                    if label in {"PASS", "PASSED"}
                    else (
                        "Fail"
                        if label in {"FAIL", "FAILED", "BLOCKED"}
                        else "Review"
                    )
                ),
                "score": check["score"] or 0,
                "detail": check["message"] or "",
            }
        )

    form = {**supplier, **purchase}

    # Stored intake fields take precedence over the synthetic-pack
    # supplier/purchase structure.
    form.update(raw.get("form") or {})

    name = (
        row.get("supplier_name")
        or row.get("legal_name")
        or row["case_key"]
    )

    return {
        "id": (
            row["case_key"]
            if row["case_key"].startswith("VO-")
            else "SD-" + row["case_key"]
        ),
        "vendor_name": name,
        "category": (
            row.get("supplier_type")
            or form.get("category")
            or "General"
        ),
        "region": (
            row.get("country")
            or form.get("region")
            or "India"
        ),
        "submitted_by": (
            row.get("requesting_department")
            or form.get("submitted_by")
            or "Demo request"
        ),
        "submitted_at": row["created_at"],
        "status": mapped_status,
        "confidence": (
            int(row["confidence_score"])
            if row.get("confidence_score") is not None
            else None
        ),
        "risk_level": row.get("risk_label") or "Unscored",
        "assigned_to": (
            row.get("procurement_owner")
            or "Procurement team"
        ),
        "document": next(
            (doc["name"] for doc in _documents(row)),
            "No document",
        ),
        "documents": _documents(row),
        "submitted_form": form,
        "extracted_fields": {
            key: form.get(key, "")
            for key in (
                "legal_name",
                "tax_id",
                "pan",
                "bank_account",
                "ifsc",
                "registered_address",
                "contact_email",
            )
        },
        "checks": result,
        "source_status": status,
    }


def list_cases() -> list[dict]:
    rows = _rows(
        "onboarding_cases",
        {"select": "*", "order": "created_at.desc"},
    )

    docs = _rows(
        "case_documents",
        {
            "select": (
                "id,case_id,file_name,document_type,"
                "mime_type,storage_path,created_at"
            ),
            "order": "created_at.asc",
        },
    )

    checks = _rows(
        "validation_checks",
        {
            "select": "case_id,check_name,result,score,message",
            "order": "evaluated_at.asc",
        },
    )

    for row in rows:
        row["case_documents"] = [
            doc for doc in docs if doc["case_id"] == row["id"]
        ]
        row["validation_checks"] = [
            check
            for check in checks
            if check["case_id"] == row["id"]
        ]

    return [map_case(row) for row in rows]


def find_case(case_key: str) -> dict | None:
    key = case_key[3:] if case_key.startswith("SD-") else case_key

    rows = _rows(
        "onboarding_cases",
        {
            "select": "*",
            "case_key": "eq." + key,
            "limit": "1",
        },
    )

    return map_case(rows[0]) if rows else None


def upload_document(
    case_key: str,
    name: str,
    content: bytes,
    mime_type: str | None = None,
    document_type: str = "uploaded",
) -> dict:
    rows = _rows(
        "onboarding_cases",
        {
            "select": "id",
            "case_key": "eq." + case_key,
            "limit": "1",
        },
    )

    if not rows:
        raise ValueError("Unknown case")

    safe_name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    path = f"{rows[0]['id']}/{uuid4().hex}/{safe_name}"

    mime = (
        mime_type
        or mimetypes.guess_type(safe_name)[0]
        or "application/octet-stream"
    )

    _request(
        "/storage/v1/object/"
        + BUCKET
        + "/"
        + quote(path, safe="/"),
        "POST",
        content,
        {
            "Content-Type": mime,
            "x-upsert": "false",
        },
    )

    existing = _rows(
        "case_documents",
        {
            "select": "id",
            "case_id": "eq." + rows[0]["id"],
            "file_name": "eq." + safe_name,
            "storage_path": "is.null",
            "limit": "1",
        },
    )

    document = {
        "case_id": rows[0]["id"],
        "document_type": document_type,
        "file_name": safe_name,
        "mime_type": mime,
        "storage_path": path,
        "file_hash": hashlib.sha256(content).hexdigest(),
        "extraction_status": "pending",
    }

    try:
        if existing:
            document.pop("case_id")
            document.pop("file_name")

            inserted = _request(
                "/rest/v1/case_documents?"
                + urlencode(
                    {"id": "eq." + existing[0]["id"]}
                ),
                "PATCH",
                document,
                {"Prefer": "return=representation"},
            )
        else:
            inserted = _request(
                "/rest/v1/case_documents",
                "POST",
                document,
                {"Prefer": "return=representation"},
            )

        return inserted[0]

    except Exception:
        _request(
            "/storage/v1/object/"
            + BUCKET
            + "/"
            + quote(path, safe="/"),
            "DELETE",
        )
        raise


def document_url(case_key: str, document_id: str) -> str | None:
    rows = _rows(
        "onboarding_cases",
        {
            "select": "id",
            "case_key": "eq." + case_key,
            "limit": "1",
        },
    )

    if not rows:
        return None

    docs = _rows(
        "case_documents",
        {
            "select": "storage_path",
            "id": "eq." + document_id,
            "case_id": "eq." + rows[0]["id"],
            "limit": "1",
        },
    )

    if not docs or not docs[0]["storage_path"]:
        return None

    result = _request(
        "/storage/v1/object/sign/"
        + BUCKET
        + "/"
        + quote(docs[0]["storage_path"], safe="/"),
        "POST",
        {"expiresIn": 60},
    )

    signed = result.get("signedURL") or result.get("signedUrl")

    scheme = "https" + "://"

    return (
        signed
        if signed.startswith(scheme)
        else os.environ["SUPABASE_URL"].rstrip("/")
        + (signed if signed.startswith("/") else "/" + signed)
    )


def save_intake(
    case: dict,
    payload: dict,
    documents: list[tuple[str, bytes, str]],
) -> None:
    row = {
        "case_key": case["id"],
        "request_id": case["id"],
        "title": case["vendor_name"],
        "status": case["status"],
        "confidence_score": case["confidence"],
        "risk_label": case["risk_level"],
        "supplier_name": case["vendor_name"],
        "legal_name": payload["legal_name"],
        "supplier_type": payload.get("category"),
        "country": payload.get("region"),
        "address": payload.get("registered_address"),
        "tax_id": payload.get("tax_id"),
        "contact_email": payload.get("contact_email"),
        "raw_request": {
            "form": payload,
            "data_classification": "vendor_intake",
        },
    }

    inserted = _request(
        "/rest/v1/onboarding_cases",
        "POST",
        row,
        {"Prefer": "return=representation"},
    )[0]

    uploaded_paths: list[str] = []

    try:
        for index, (name, content, mime_type) in enumerate(documents):
            uploaded = upload_document(
                case["id"],
                name,
                content,
                mime_type,
                (
                    "Source document"
                    if index == 0
                    else "Supporting document"
                ),
            )

            if uploaded.get("storage_path"):
                uploaded_paths.append(uploaded["storage_path"])

        if case["checks"]:
            checks = [
                {
                    "case_id": inserted["id"],
                    "code": "CHECK_" + str(index + 1),
                    "check_name": check["name"],
                    "result": check["result"],
                    "score": check["score"],
                    "message": check["detail"],
                }
                for index, check in enumerate(case["checks"])
            ]

            _request(
                "/rest/v1/validation_checks",
                "POST",
                checks,
            )

    except Exception:
        for path in uploaded_paths:
            try:
                _request(
                    "/storage/v1/object/"
                    + BUCKET
                    + "/"
                    + quote(path, safe="/"),
                    "DELETE",
                )
            except Exception:
                pass

        _request(
            "/rest/v1/onboarding_cases?"
            + urlencode(
                {"case_key": "eq." + case["id"]}
            ),
            "DELETE",
        )

        raise


def save_decision(
    case_key: str,
    decision: str,
    reviewer: str,
) -> dict | None:
    key = case_key[3:] if case_key.startswith("SD-") else case_key

    rows = _request(
        "/rest/v1/onboarding_cases?"
        + urlencode({"case_key": "eq." + key}),
        "PATCH",
        {
            "status": decision,
            "procurement_owner": reviewer,
        },
        {"Prefer": "return=representation"},
    )

    return map_case(rows[0]) if rows else None