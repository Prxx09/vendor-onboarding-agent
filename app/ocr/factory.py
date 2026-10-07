from app.core.config import get_settings
from app.ocr.base import OcrProvider
from app.ocr.windows import WindowsOcrProvider


def get_ocr_provider() -> OcrProvider:
    mode = get_settings().OCR_PROVIDER.lower().strip()

    if mode == "windows":
        return WindowsOcrProvider()

    raise ValueError(f"Unsupported OCR_PROVIDER={mode}")
