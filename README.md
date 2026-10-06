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

The current runtime uses `local-memory` storage so frontend and backend can run together immediately. The backend workflow logic is separated in `app/workflow.py`, which keeps scoring/routing independent from storage. That makes the next migration step straightforward: replace the local store calls with Supabase reads/writes while keeping the same frontend API contract.

Copy `.env.example` to `.env` and add the server-side Supabase key before enabling hosted writes. Never expose that key in the browser or commit it to Git.

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
