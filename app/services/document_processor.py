from dataclasses import dataclass

import fitz

from app.core.config import get_settings
from app.ocr.base import OcrProvider


@dataclass(slots=True)
class DocumentTextResult:
    text: str
    method: str
    page_count: int


def _clean_text(text: str) -> str:
    return "\n".join(
        line.strip()
        for line in text.replace("\x00", "").splitlines()
        if line.strip()
    ).strip()


def _has_usable_native_text(text: str, min_chars: int) -> bool:
    cleaned = _clean_text(text)
    alphanumeric_count = sum(ch.isalnum() for ch in cleaned)
    return len(cleaned) >= min_chars and alphanumeric_count >= max(15, min_chars // 2)


class DocumentProcessor:
    """
    Extracts raw document text before the LLM sees the document.

    PDF:
      - use the embedded text layer page-by-page when it is usable;
      - OCR only pages that do not have usable embedded text.

    Images:
      - use the configured OCR provider (Windows OCR for the MVP).
    """

    def __init__(self, ocr: OcrProvider) -> None:
        self.ocr = ocr
        self.settings = get_settings()

    async def extract_text(
        self,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> DocumentTextResult:
        if not content:
            raise ValueError(f"{filename} is empty.")

        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            return await self._extract_pdf(filename, content)

        if mime_type.startswith("image/"):
            text = _clean_text(await self.ocr.extract_text(content))
            if not text:
                raise ValueError(f"OCR returned no readable text for {filename}.")
            return DocumentTextResult(
                text=text,
                method="windows_ocr",
                page_count=1,
            )

        raise ValueError(f"Unsupported document type: {mime_type}")

    async def _extract_pdf(
        self,
        filename: str,
        content: bytes,
    ) -> DocumentTextResult:
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise ValueError(f"Could not open PDF {filename}: {exc}") from exc

        with document:
            page_count = document.page_count
            if page_count == 0:
                raise ValueError(f"{filename} has no pages.")
            if page_count > self.settings.OCR_MAX_PDF_PAGES:
                raise ValueError(
                    f"{filename} has {page_count} pages; the prototype limit is "
                    f"{self.settings.OCR_MAX_PDF_PAGES}."
                )

            page_texts: list[str] = []
            native_pages = 0
            ocr_pages = 0

            for page in document:
                native_text = _clean_text(page.get_text("text"))

                if _has_usable_native_text(
                    native_text,
                    self.settings.PDF_NATIVE_TEXT_MIN_CHARS,
                ):
                    page_texts.append(native_text)
                    native_pages += 1
                    continue

                matrix = fitz.Matrix(
                    self.settings.OCR_PDF_RENDER_SCALE,
                    self.settings.OCR_PDF_RENDER_SCALE,
                )
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                png_bytes = pixmap.tobytes("png")
                ocr_text = _clean_text(await self.ocr.extract_text(png_bytes))

                if ocr_text:
                    page_texts.append(ocr_text)
                ocr_pages += 1

            text = "\n\n".join(part for part in page_texts if part).strip()
            if not text:
                raise ValueError(f"No readable text could be extracted from {filename}.")

            if ocr_pages == 0:
                method = "native_pdf_text"
            elif native_pages == 0:
                method = "windows_ocr"
            else:
                method = "hybrid_pdf_text_ocr"

            return DocumentTextResult(
                text=text,
                method=method,
                page_count=page_count,
            )
