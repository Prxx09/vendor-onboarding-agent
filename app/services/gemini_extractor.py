from google import genai
from google.genai import types

from app.core.config import get_settings
from app.domain.models import DocumentExtraction


EXTRACTION_PROMPT = """
You are the document-understanding component of a vendor onboarding verification agent.

You receive text that has already been extracted from a document using either:
1. the PDF's embedded text layer, or
2. local Windows OCR.

Classify the document into exactly one of:
- business_registration
- tax_certificate
- bank_proof
- other

Extract only information explicitly present in the supplied text.
Do not guess or repair identifiers that OCR may have read incorrectly.
Use null for values that are absent or unreadable.

For bank letters, cancelled cheques or bank confirmations, extract:
account holder legal name, bank name, account number and IFSC/SWIFT.

For business registration, extract:
legal company name, registration number, address, issue date and expiry date.

For tax certificates, extract:
legal company name, tax identifier, address and relevant dates.

Dates should be ISO YYYY-MM-DD when the text provides enough information.
The confidence field should reflect confidence in the document classification,
not confidence in whether the document is genuine.
"""


class GeminiDocumentExtractor:
    """
    Gemini structures OCR/native PDF text. It does not receive document images
    in the default MVP path.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.GEMINI_MODEL
        self.max_chars = settings.DOCUMENT_TEXT_MAX_CHARS
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def extract(
        self,
        filename: str,
        raw_text: str,
    ) -> DocumentExtraction:
        text = raw_text[: self.max_chars]
        prompt = (
            f"{EXTRACTION_PROMPT}\n\n"
            f"Filename: {filename}\n\n"
            "Extracted document text:\n"
            "----- BEGIN DOCUMENT TEXT -----\n"
            f"{text}\n"
            "----- END DOCUMENT TEXT -----"
        )

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DocumentExtraction,
                temperature=0,
            ),
        )

        if isinstance(response.parsed, DocumentExtraction):
            parsed = response.parsed
        else:
            parsed = DocumentExtraction.model_validate_json(response.text)

        parsed.filename = filename
        return parsed
