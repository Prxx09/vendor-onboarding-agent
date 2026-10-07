import asyncio
import json

import groq
from groq import AsyncGroq
from pydantic import ValidationError

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
Do not guess, repair, normalize, or silently correct identifiers that OCR may
have read incorrectly. Preserve account numbers, tax identifiers, registration
numbers and IFSC/SWIFT values exactly as they appear in the supplied text.
Use null for values that are absent or unreadable.

For bank letters, cancelled cheques or bank confirmations, extract:
account holder legal name, bank name, account number and IFSC/SWIFT.

For business registration, extract:
legal company name, registration number, address, issue date and expiry date.

For tax certificates, extract:
legal company name, tax identifier, PAN when explicitly present, address and relevant dates.

If any document explicitly contains a vendor contact email or vendor category,
extract those values as contact_email and vendor_category. Otherwise use null.

For every extracted field, populate field_confidence with a 0.0-1.0 confidence
value keyed by the JSON field name. Omit confidence entries for absent fields.
The field confidence should reflect readability/extraction certainty only, not
whether the document is authentic.

Dates should be ISO YYYY-MM-DD when the text provides enough information.
The top-level confidence field is confidence in the document classification,
not confidence that the document is genuine.

Return only data matching the supplied JSON schema.
"""


class GroqDocumentExtractor:
    """Structures OCR/native PDF text with Groq; document images stay local."""

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.GROQ_MODEL
        self.max_chars = settings.DOCUMENT_TEXT_MAX_CHARS
        self.max_retries = max(1, settings.GROQ_MAX_RETRIES)
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    async def extract(self, filename: str, raw_text: str) -> DocumentExtraction:
        text = raw_text[: self.max_chars]
        user_content = (
            f"Filename: {filename}\n\n"
            "Extracted document text:\n"
            "----- BEGIN DOCUMENT TEXT -----\n"
            f"{text}\n"
            "----- END DOCUMENT TEXT -----"
        )

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": EXTRACTION_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "document_extraction",
                            "strict": False,
                            "schema": DocumentExtraction.model_json_schema(),
                        },
                    },
                )

                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Groq returned an empty extraction response.")

                # Parsing through JSON first produces clearer errors in audit logs.
                payload = json.loads(content)
                parsed = DocumentExtraction.model_validate(payload)
                parsed.filename = filename
                return parsed

            except (
                json.JSONDecodeError,
                ValidationError,
                ValueError,
                groq.APIConnectionError,
                groq.RateLimitError,
                groq.InternalServerError,
            ) as exc:
                last_error = exc
            except groq.APIStatusError as exc:
                # Retry temporary Groq failures, but surface bad requests/auth errors.
                if exc.status_code != 429 and exc.status_code < 500:
                    raise
                last_error = exc

            if attempt < self.max_retries:
                await asyncio.sleep(0.75 * (2 ** (attempt - 1)))

        raise RuntimeError(
            f"Groq document extraction failed after {self.max_retries} attempts: "
            f"{last_error}"
        ) from last_error
