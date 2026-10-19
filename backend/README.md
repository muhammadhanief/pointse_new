# Backend pointse

FastAPI + geopandas/pyogrio/shapely + MySQL (SQLAlchemy + PyMySQL + Alembic).
Semua hitungan spasial di Python, tanpa QGIS/PyQGIS. Hanya backend yang mengakses MySQL.

## Setup (Windows, PowerShell)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env   # lalu isi kredensial MySQL
```

## Jalan & tes

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload   # http://127.0.0.1:8000/health
.venv\Scripts\python.exe -m pytest -q
```

## Isi

- `app/config.py` — setelan dari `.env` (kredensial DB, CORS)
- `app/main.py` — aplikasi FastAPI (baru endpoint `/health`)
- `tests/` — tes pytest

Rencana pengisian: T1 Proses A, T2 Proses B, T3 API upload/jalankan/status/hasil + skema MySQL + Alembic.
