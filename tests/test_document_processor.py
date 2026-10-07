import pymupdf
import pytest

from app.ocr.base import OcrProvider
from app.services.document_processor import DocumentProcessor


class FakeOcr(OcrProvider):
    def __init__(self, text: str = "OCR TEXT") -> None:
        self.text = text
        self.calls = 0

    async def extract_text(self, image_bytes: bytes) -> str:
        self.calls += 1
        assert image_bytes
        return self.text


@pytest.mark.asyncio
async def test_pdf_prefers_embedded_text(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("GEMINI_API_KEY", "test")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(72, 72, 500, 220),
        (
            "BUSINESS REGISTRATION\n"
            "Evergreen Facility Solutions Private Limited\n"
            "Registration Number U74999MH2024PTC100101"
        ),
        fontsize=11,
    )
    pdf = doc.tobytes()
    doc.close()

    ocr = FakeOcr()
    processor = DocumentProcessor(ocr)
    result = await processor.extract_text("registration.pdf", "application/pdf", pdf)

    assert result.method == "native_pdf_text"
    assert "U74999MH2024PTC100101" in result.text
    assert ocr.calls == 0


@pytest.mark.asyncio
async def test_image_uses_ocr(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("GEMINI_API_KEY", "test")

    ocr = FakeOcr("Account Holder: Crestline Trading House")
    processor = DocumentProcessor(ocr)
    result = await processor.extract_text("cheque.png", "image/png", b"fake-image")

    assert result.method == "windows_ocr"
    assert result.text == "Account Holder: Crestline Trading House"
    assert ocr.calls == 1


@pytest.mark.asyncio
async def test_scanned_pdf_falls_back_to_ocr(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("GEMINI_API_KEY", "test")

    doc = pymupdf.open()
    doc.new_page()
    pdf = doc.tobytes()
    doc.close()

    ocr = FakeOcr("Tax ID GST27EFS9012Z5A")
    processor = DocumentProcessor(ocr)
    result = await processor.extract_text("scan.pdf", "application/pdf", pdf)

    assert result.method == "windows_ocr"
    assert "GST27EFS9012Z5A" in result.text
    assert ocr.calls == 1
