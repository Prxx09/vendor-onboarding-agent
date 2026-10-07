from google import genai
from google.genai import types

from app.core.config import get_settings
from app.domain.models import DocumentExtraction


EXTRACTION_PROMPT = """
You are the document-intake component of a vendor onboarding verification agent.

Classify this uploaded vendor document into exactly one of:
- business_registration
- tax_certificate
- bank_proof
- other

Extract only information visibly present in the document.
Do not infer missing identifiers.
Use null for values that are absent or unreadable.

For bank letters, cancelled cheques or bank confirmations, extract:
account holder legal name, bank name, account number and IFSC/SWIFT.

For business registration, extract:
legal company name, registration number, address, issue date and expiry date.

For tax certificates, extract:
legal company name, tax identifier, address and relevant dates.

Dates should be ISO YYYY-MM-DD when the document provides enough information.
"""


class GeminiDocumentExtractor:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.GEMINI_MODEL
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def extract(
        self,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> DocumentExtraction:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=[
                EXTRACTION_PROMPT,
                types.Part.from_bytes(data=content, mime_type=mime_type),
            ],
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
