# Frontend

React + Vite frontend for the Vendor Verification Agent.

The UI is fully driven by backend/Supabase data. It does not embed demo vendors,
fixed reviewer names, fixed regions, fixed approval thresholds, or frontend
upload-limit fallbacks.

## Local development

From the repository root:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Frontend: `http://127.0.0.1:3000`

Backend URL is read from `VITE_API_BASE_URL`.

## Main screens

- Dashboard
- Vendor case list/search/filter
- New vendor intake with automatic OCR/Groq extraction
- Detailed case view with Overview / Original submission / Scorecard / History
- Human review queue with approve / reject / request-information actions
- Audit trail grouped by vendor case

## Backend APIs used

- `GET /health`
- `GET /api/v1/config`
- `GET /api/v1/dashboard`
- `GET /api/v1/vendors`
- `POST /api/v1/documents/extract`
- `POST /api/v1/vendors/process`
- `POST /api/v1/vendors/{vendor_id}/documents`
- `GET /api/v1/vendors/review-queue`
- `GET /api/v1/vendors/{vendor_id}`
- `POST /api/v1/vendors/{vendor_id}/review`
- `GET /api/v1/audit-events`

## Backend-controlled UI policy

The frontend reads upload limits, required intake fields, approval threshold,
category/region suggestions, supported file types and optional validation
patterns from `GET /api/v1/config`.

Configure those values in the backend root `.env`, not in frontend source.

## Existing Supabase projects

Run `sql/frontend_workflow_migration.sql` once before using the expanded
case-management UI. It adds case metadata, scorecards, audit events and private
document storage metadata/bucket support.


## API base URL

Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `frontend/.env`.
When `VITE_API_BASE_URL` is not set during Vite development, the frontend now
falls back to `http://127.0.0.1:8000` instead of the Vite origin. This prevents
API requests from accidentally receiving `index.html` from the frontend dev server.
