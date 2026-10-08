from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings


app = FastAPI(
    title="Vendor Onboarding Verification Agent",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "storage_mode": "supabase",
        "supabase_configured": bool(
            settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY
        ),
        "verification_provider_mode": settings.VERIFICATION_PROVIDER_MODE,
        "document_storage_bucket": settings.DOCUMENT_STORAGE_BUCKET,
    }
