"""Aplikasi FastAPI pointse (kerangka awal T0).

Endpoint diisi bertahap per task: upload, jalankan proses, status, dan hasil
ada di T3.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

# CORS dibatasi ke domain frontend saja (lihat CORS_ORIGINS di .env).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Cek aplikasi hidup; dipakai monitoring dan tes."""
    return {"status": "ok", "app": settings.app_name}
