# Vendor Onboarding Verification Agent

Client-demo MVP for supplier onboarding focused on document understanding and vendor verification.

The prototype intentionally excludes PO creation and procurement approvals. Its core job is:

1. Accept vendor details and required documents.
2. Use Gemini multimodal extraction to classify documents and extract structured fields.
3. Verify extracted company, tax, bank, KYC/KYB and sanctions data against preset Supabase registries.
4. Cross-check the documents against each other.
5. Return one of three business states: APPROVED, ACTION_REQUIRED, or REVIEW_REQUIRED.
6. Let a human approve or reject items in the review queue.

## Workflow

~~~text
Upload documents
      |
      v
Gemini extraction
      |
      v
Completeness check
   /          \
missing       complete
  |              |
ACTION_REQUIRED  v
             verification tools
                  |
                  v
             cross-document checks
                  |
                  v
               decision
              /       \
         APPROVED   REVIEW_REQUIRED
                         |
                         v
                    human review
                    /          \
                APPROVED     REJECTED
~~~

## Required documents for the MVP

- Business Registration
- Tax Certificate
- Bank Proof / Bank Letter / Cancelled Cheque

Other uploaded files are classified but do not block onboarding.

## Architecture

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

Gemini is used for document classification and structured extraction. Verification decisions are not delegated entirely to the LLM. Registry lookups, duplicate checks, status rules and cross-document matching are deterministic tools around the model.

The model is configurable with GEMINI_MODEL. Default: gemini-3.8-flash.

## Setup

1. Create a Python virtual environment.
2. Install dependencies:

~~~bash
pip install -r requirements.txt
~~~

3. Copy .env.example to .env and add your rotated Supabase service-role key and Gemini API key.
4. Run sql/schema.sql in Supabase SQL Editor.
5. Run sql/seed_demo.sql to load synthetic verification records.
6. Start the API:

~~~bash
uvicorn app.main:app --reload
~~~

API docs: http://127.0.0.1:8000/docs

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
