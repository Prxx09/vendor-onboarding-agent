# Vendor Onboarding Verification Agent

Client-demo MVP for supplier onboarding focused on document understanding and vendor verification.

The prototype intentionally excludes PO creation and procurement approvals. Its core job is:

1. Accept vendor details and required documents.
2. Read documents locally using the PDF text layer or Windows built-in OCR.
3. Send only extracted text to Gemini for document classification and structured field extraction.
4. Verify extracted company, tax, bank, KYC/KYB and sanctions data against preset Supabase registries.
5. Cross-check the documents against each other.
6. Return APPROVED, ACTION_REQUIRED, or REVIEW_REQUIRED.
7. Let a human approve or reject items in the review queue.

## Document extraction pipeline

~~~text
PDF / image
    |
    +-- PDF page has usable embedded text
    |       |
    |       +--> PyMuPDF text extraction
    |
    +-- Image or scanned PDF page
            |
            +--> Windows.Media.Ocr
                        |
                        v
                   raw text
                        |
                        v
                     Gemini
             classification + JSON
~~~

Gemini does not receive the image/PDF in the default MVP path. It receives the text already extracted locally. This reduces vision usage and makes OCR replaceable independently from the LLM.

For mixed PDFs, the processor works page-by-page: pages with a usable text layer use native text, while scanned pages fall back to Windows OCR.

## Windows OCR requirements

The MVP OCR provider uses the Windows.Media.Ocr WinRT API, so scanned documents/images must be processed on Windows 10/11.

Python WinRT dependencies are installed only on Windows through environment markers in requirements.txt.

Windows also needs an OCR language capability installed. Normally the user's Windows language pack is used. You may optionally set:

~~~env
OCR_LANGUAGE=en-US
~~~

If no language is specified, the provider uses the Windows user-profile OCR languages.

For a future Linux/cloud deployment, replace the OCR provider behind app/ocr/base.py; the agent and Gemini structuring layer do not need to change.

## Required documents for the MVP

- Business Registration
- Tax Certificate
- Bank Proof / Bank Letter / Cancelled Cheque

Other uploaded files are classified but do not block onboarding.

## Verification architecture

The agent never talks directly to Supabase tables or future official websites.

~~~text
LangGraph Agent
      |
      v
VerificationProvider interface
      |
      +---- SupabaseVerificationProvider   <- current demo
      |
      +---- HttpVerificationProvider       <- later official APIs
~~~

When official services become available, set VERIFICATION_PROVIDER_MODE=http and configure the endpoint environment variables. If a provider returns a different JSON shape, only the adapter in app/providers/http_provider.py should need mapping changes.

## Gemini

Gemini is used only after local text extraction. It classifies the document and converts OCR/native PDF text into the structured DocumentExtraction schema.

Registry lookup, duplicate checks, name matching, expiry checks and final routing are deterministic application logic around the LLM.

The model is configurable with GEMINI_MODEL.

## Setup

1. Use Windows 10/11 for the current OCR implementation.
2. Create a Python virtual environment.
3. Install dependencies:

~~~bash
pip install -r requirements.txt
~~~

4. Copy .env.example to .env and add your rotated Supabase service-role key and Gemini API key.
5. Run sql/schema.sql in Supabase SQL Editor.
6. Run sql/seed_demo.sql to load synthetic verification records.
7. Start the API:

~~~bash
uvicorn app.main:app --reload
~~~

API docs: http://127.0.0.1:8000/docs

Run unit tests:

~~~bash
pytest -q
~~~

## Main API

POST /api/v1/vendors/process

Multipart fields:
- legal_name: optional vendor-submitted legal name
- files: multiple PDF/JPG/PNG files

GET /api/v1/vendors/review-queue

POST /api/v1/vendors/{vendor_id}/review

Body:

~~~json
{
  "decision": "APPROVE",
  "reviewer": "finance.user@company.com",
  "comment": "Supporting evidence manually confirmed."
}
~~~

## Demo scenarios

The seed data is aligned to the synthetic sample pack:

- Evergreen Facility Solutions Private Limited -> clean -> APPROVED
- Lighthouse Workplace Supplies Private Limited -> missing tax certificate -> ACTION_REQUIRED
- Crestline Packaging Private Limited -> bank-holder mismatch -> REVIEW_REQUIRED
- Blue River Industrial Supplies LLP -> duplicate tax ID -> REVIEW_REQUIRED
- Pinecrest Technical Services Private Limited -> expired company registration -> REVIEW_REQUIRED
- Northstar Export Trading LLC -> sanctions/KYC flag -> REVIEW_REQUIRED

All sample registry data is synthetic and must not be represented as real government, KYC or bank verification.
