import platform

from app.core.config import get_settings
from app.ocr.base import OcrProvider


class WindowsOcrUnavailableError(RuntimeError):
    pass


class WindowsOcrProvider(OcrProvider):
    """
    Uses the Windows.Media.Ocr WinRT API.

    Imports are intentionally lazy so the FastAPI project can still be imported
    on non-Windows machines. OCR itself requires Windows 10/11 and an installed
    Windows OCR language pack.
    """

    def __init__(self) -> None:
        self.language = (get_settings().OCR_LANGUAGE or "").strip() or None
        self._engine = None

    def _get_engine(self):
        if platform.system() != "Windows":
            raise WindowsOcrUnavailableError(
                "Windows OCR was requested, but the backend is not running on Windows."
            )

        try:
            from winrt.windows.globalization import Language
            from winrt.windows.media.ocr import OcrEngine
        except ImportError as exc:
            raise WindowsOcrUnavailableError(
                "Windows OCR Python bindings are missing. Install requirements.txt on Windows."
            ) from exc

        if self._engine is not None:
            return self._engine

        if self.language:
            language = Language(self.language)
            if not OcrEngine.is_language_supported(language):
                raise WindowsOcrUnavailableError(
                    f"Windows OCR language '{self.language}' is not installed."
                )
            engine = OcrEngine.try_create_from_language(language)
        else:
            engine = OcrEngine.try_create_from_user_profile_languages()

        if engine is None:
            raise WindowsOcrUnavailableError(
                "Windows could not create an OCR engine. Install an OCR language pack "
                "under Windows language settings."
            )

        self._engine = engine
        return engine

    async def extract_text(self, image_bytes: bytes) -> str:
        if not image_bytes:
            return ""

        engine = self._get_engine()

        try:
            from winrt.windows.graphics.imaging import BitmapDecoder
            from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
        except ImportError as exc:
            raise WindowsOcrUnavailableError(
                "Required WinRT imaging/stream packages are missing."
            ) from exc

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(image_bytes)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)

        # Joining lines preserves document structure better than flattening all text.
        text = "\n".join(line.text for line in result.lines)
        return text.strip()
