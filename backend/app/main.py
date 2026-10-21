"""Aplikasi FastAPI pointse.

Endpoint: ``/health``, ``/runs`` (unggah/antre + daftar), ``/runs/{id}`` (status),
``/runs/{id}/hasil``, ``/runs/{id}/rekap``, ``/runs/{id}/ekspor/*`` (CSV/GPKG),
``/ekspor/rekap.csv``, ``/ringkasan``, ``/tren``, ``/perubahan``, dan
``/sistem/status`` (pemantauan worker untuk admin).

API dijalankan langsung sebagai ASGI dengan uvicorn. Path dapat diberi prefix
lewat ``API_PREFIX`` (default kosong). Worker produksi dijalankan sebagai service
terpisah (``python -m app.worker --loop``); set ``WORKER_ENABLED=false`` di proses
API agar tidak ada worker tambahan di dalam uvicorn.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api import router
from app.config import get_settings
from app.pengguna import router as router_pengguna
from app.sistem import router as router_sistem
from app.unggahan import router as router_unggahan
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


prefix = settings.api_prefix
app = FastAPI(
    title=settings.app_name,
    version="0.5.0",
    lifespan=lifespan,
    docs_url=f"{prefix}/docs" if prefix else "/docs",
    redoc_url=f"{prefix}/redoc" if prefix else "/redoc",
    openapi_url=f"{prefix}/openapi.json" if prefix else "/openapi.json",
)

# Frontend statis berada di origin lain; autentikasi memakai Bearer, bukan
# cookie, sehingga credentials tidak boleh diaktifkan.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-SHA256"],
    expose_headers=["Content-Disposition", "Retry-After"],
    max_age=600,
)


@app.middleware("http")
async def tanpa_cache(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Cegah proxy/cache menyimpan balasan API yang berubah tiap saat."""
    respons = await call_next(request)
    respons.headers["Cache-Control"] = "no-store, max-age=0"
    respons.headers["Pragma"] = "no-cache"
    return respons


app.include_router(router, prefix=prefix)
app.include_router(router_pengguna, prefix=prefix)
app.include_router(router_sistem, prefix=prefix)
app.include_router(router_unggahan, prefix=prefix)


@app.get(f"{prefix}/health")
def health() -> dict[str, str]:
    """Cek aplikasi hidup; dipakai monitoring dan tes."""
    return {"status": "ok", "app": settings.app_name}
