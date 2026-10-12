import pytest
from fastapi import HTTPException

from app.api.routes import _validate_file_content, _validate_submitted_data


def test_upload_content_validation_accepts_supported_signatures():
    _validate_file_content("sample.pdf", "application/pdf", b"%PDF-1.7 test")
    _validate_file_content("sample.png", "image/png", b"\x89PNG\r\n\x1a\nrest")
    _validate_file_content("sample.jpg", "image/jpeg", b"\xff\xd8\xffrest")
    _validate_file_content(
        "sample.webp",
        "image/webp",
        b"RIFF\x00\x00\x00\x00WEBPrest",
    )


def test_upload_content_validation_rejects_spoofed_file():
    with pytest.raises(HTTPException) as exc:
        _validate_file_content("sample.pdf", "application/pdf", b"not a pdf")
    assert exc.value.status_code == 400


def test_intake_format_validation_rejects_invalid_email():
    with pytest.raises(HTTPException) as exc:
        _validate_submitted_data({"contact_email": "not-an-email"})
    assert exc.value.status_code == 422


def test_intake_format_validation_accepts_demo_identifiers():
    _validate_submitted_data(
        {
            "contact_email": "vendor@example.com",
            "bank_account": "004400112233",
            "ifsc": "MTBK0000321",
        }
    )
