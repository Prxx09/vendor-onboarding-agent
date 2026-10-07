# Frontend

React + Vite frontend for the Vendor Verification Agent.

## Local development

From the repository root:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Frontend: http://127.0.0.1:3000

Backend expected at: http://127.0.0.1:8000

The default `.env.example` already contains:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Backend endpoints used

- `GET /health`
- `POST /api/v1/vendors/process`
- `POST /api/v1/vendors/{vendor_id}/documents` — upload missing documents and resume the same ACTION_REQUIRED case
- `GET /api/v1/vendors/review-queue`
- `GET /api/v1/vendors/{vendor_id}`
- `POST /api/v1/vendors/{vendor_id}/review`

## Supported upload types

PDF, PNG, JPG/JPEG and WEBP, up to 20 MB per file.

The current verification flow shown in the UI is:

Windows OCR / native PDF text -> Groq structuring -> Supabase verification -> decision -> human review when required.


## Resume an incomplete vendor

When the process response is `ACTION_REQUIRED`, the result screen shows a "Continue this onboarding case" upload control. The frontend sends only the newly selected document(s) to `POST /api/v1/vendors/{vendor_id}/documents`; the backend reuses documents already stored for that vendor and keeps the same vendor ID.
