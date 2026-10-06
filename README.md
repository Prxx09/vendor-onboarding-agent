# Vendor Onboarding Agent

Client-demo MVP for automating vendor onboarding from document upload to approval decision.

The flow is designed around one hard rule: the user uploads the vendor document first, the intake form is auto-populated from extracted fields, and manual entry remains available for corrections. After submit, checks and validations run, scores are calculated, an overall confidence score is produced, and the case is either auto-approved or sent for human review based on a preset threshold. Every action is logged with timestamps for traceability.

## Features

- Document-first intake with auto-populated editable fields
- Validation scoring across KYC, tax, sanctions, banking, compliance, and document quality
- Configurable pass/fail confidence threshold
- Auto-approval for low-risk vendors and review queue for exceptions
- Human review decision actions
- Timestamped audit trail for every major action
- FastAPI backend serving both API and frontend from one local command
- Supabase schema for cases, documents, validations, approvals, references, and audit events

## Quick Start

Use the combined frontend + backend branch:

```bash
git fetch origin
git checkout test-fe+be
```

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/storage/status
```

## Supabase

The hosted project is `vendor-onboarding-agent` in `ap-south-1` with project ref `uhralsrggcpuwdbocsie`. The migrations in `supabase/migrations/` create the backend schema and seed the synthetic demo pack. They include RLS policies that allow read-only access to synthetic demo data; workflow writes should go through the FastAPI service using a server-side key.

With `SUPABASE_URL` and a server-side `SUPABASE_SERVICE_ROLE_KEY` in `.env`, the API reads the synthetic cases from Supabase and stores newly submitted forms, validation checks, and uploaded documents in the private `vendor-documents` bucket. Without these values, the four original showcase cases and new intakes continue in local memory; local files disappear when the server restarts. The original four showcase records have vendor field snapshots and document names but no source file bytes, so the UI labels those documents as unavailable instead of offering broken links.

Copy `.env.example` to `.env` and add the server-side Supabase key before enabling hosted writes. Never expose that key in the browser or commit it to Git. The backend must be protected with application authentication before handling real vendor records; this demo API has no user authorization.\n\nThe supplied 10-scenario ZIP is seeded as Supabase case/document metadata. Their source file bytes are not yet in Storage. To upload them from your copy of the ZIP, run:\n\n```powershell\npython -m scripts.import_demo_documents \"C:\\path\\to\\Vendor_Onboarding_Synthetic_Demo_Data(3).zip\"\n```\n\nThe script matches each document by case and filename, fills existing document records, and skips files already present. The UI then offers an **Open file** action for each stored object. These ten scenarios retain their own recorded statuses and show **Not scored** where no confidence score was calculated; they are separate from the four original showcase cases.

## API

- `GET /health`
- `GET /api/config`
- `GET /api/demo-cases`
- `GET /api/demo-cases/{case_id}`
- `POST /api/intake/submit`
- `POST /api/demo-cases/{case_id}/decision`
- `POST /api/upload/simulate`
- `GET /api/audit-events`
- `GET /api/storage/status`

The **Submitted form & documents** tab opens when a case is selected. It shows the stored form values and each recorded document, with a clear unavailable state for legacy metadata without source bytes.

## Synthetic test pack

The original ten scenarios plus four generated showcase case documents are described in [docs/demo_test_coverage.md](docs/demo_test_coverage.md). The supplied complete ZIP contains 14 cases and 50 top-level source documents. The four showcase source files can be regenerated with:

```powershell
python -m pip install -r requirements-demo.txt
python -m scripts.build_showcase_fixtures .\\showcased_cases
```

The importer accepts the complete ZIP, including the showcase files. It requires a server-side Supabase key in `.env`. Existing records without file bytes remain marked as unavailable until the import completes. The current extractor is filename based, so the pack does not certify content extraction or all reference checks.
