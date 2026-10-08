from abc import ABC, abstractmethod


class OcrProvider(ABC):
    """Stable OCR contract used by the document processor."""

    @abstractmethod
    async def extract_text(self, image_bytes: bytes) -> str:
        raise NotImplementedError
