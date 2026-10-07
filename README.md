# Vendor Onboarding Verification Agent — Test FE + BE

This branch combines the current vendor-verification backend with a React + Vite frontend for the client prototype.

The old test backend has been removed. The backend now matches `feature/vendor-verification-mvp` and keeps the existing API contract unchanged.

## Architecture

```text
React + Vite
    |
    | existing REST endpoints
    v
FastAPI + LangGraph
    |
    +--> PDF native text / Windows.Media.Ocr
    +--> Gemini structured extraction
    +--> Supabase synthetic verification registries
    +--> deterministic cross-document checks
    +--> human review queue
```

## Backend setup

Use Windows 10/11 for the current scanned-document OCR provider.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `.env` with your Supabase service-role key and Gemini API key, then run:

```powershell
uvicorn app.main:app --reload
```

Backend:
- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

## Frontend setup

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Frontend: http://127.0.0.1:5173

To point the UI at another backend:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## API contract — unchanged

- `GET /health`
- `POST /api/v1/vendors/process` — multipart: `legal_name`, repeated `files`
- `GET /api/v1/vendors/review-queue`
- `GET /api/v1/vendors/{vendor_id}`
- `POST /api/v1/vendors/{vendor_id}/review`

Review body:

```json
{
  "decision": "APPROVE",
  "reviewer": "Reviewer name",
  "comment": "Supporting evidence manually confirmed."
}
```

## Frontend features

- Drag-and-drop PDF/image upload
- Backend health indicator
- Clean `APPROVED`, `ACTION_REQUIRED`, and `REVIEW_REQUIRED` result states
- Verification-check cards and agent activity timeline
- Extracted document evidence
- Human review queue
- Review detail with approve/reject override
- Responsive desktop/mobile layout

## Required prototype documents

- Business Registration
- Tax Certificate
- Bank Proof / Bank Letter / Cancelled Cheque

The verification registries and demo records are synthetic. Do not present them as real government, banking, KYC or sanctions responses.

## Database scripts

`sql/schema.sql` and `sql/seed_demo.sql` contain the verification-agent schema/seed data. The configured Supabase project already has the corresponding verification tables.

## Tests

```powershell
pytest -q
```
