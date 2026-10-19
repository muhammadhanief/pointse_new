"""Aplikasi FastAPI pointse.

Endpoint: ``/health``, ``/runs`` (unggah/antre + daftar), ``/runs/{id}`` (status),
``/runs/{id}/hasil``, dan ``/runs/{id}/rekap``.

Worker Proses A/B dinyalakan di lifespan kalau ``WORKER_ENABLED=true`` (default).
Untuk produksi, worker bisa juga dijalankan sebagai proses terpisah::

    .venv\\Scripts\\python.exe -m app.worker
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.config import get_settings
from app.worker import mulai_worker

logger = logging.getLogger("pointse")

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Nyalakan worker saat aplikasi hidup, hentikan saat aplikasi mati."""
    benang: list[threading.Thread] = []
    penghenti: threading.Event | None = None
    if settings.worker_enabled:
        benang, penghenti = mulai_worker(settings)

    try:
        yield
    finally:
        if penghenti is not None:
            penghenti.set()
            for satu in benang:
                satu.join(timeout=10)


app = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)

# CORS dibatasi ke domain frontend saja (lihat CORS_ORIGINS di .env).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Cek aplikasi hidup; dipakai monitoring dan tes."""
    return {"status": "ok", "app": settings.app_name}
