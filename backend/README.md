# Backend pointse

FastAPI + geopandas/pyogrio/shapely + MySQL (SQLAlchemy + PyMySQL + Alembic).
Semua hitungan spasial di Python, tanpa QGIS/PyQGIS. Hanya backend yang mengakses MySQL,
dan hanya lewat endpoint API (frontend tidak pernah menyentuh basis data).

## Setup (Windows, PowerShell)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env          # lalu isi kredensial MySQL
.venv\Scripts\python.exe -m alembic upgrade head   # buat tabel runs + titik_hasil
```

## Jalan & tes

```powershell
# API (worker ikut nyala, lihat WORKER_ENABLED di .env)
.venv\Scripts\python.exe -m uvicorn app.main:app --reload      # http://127.0.0.1:8000/docs

# Worker terpisah (mis. di server lain / proses sendiri)
.venv\Scripts\python.exe -m app.worker

# Tes (tanpa MySQL: tes memakai SQLite sementara)
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -q -m "not slow"           # lewati tes data penuh docs/
```

## Endpoint API (T3)

| Method | Alamat | Keterangan |
|---|---|---|
| GET | `/health` | Cek aplikasi hidup |
| POST | `/runs` | Unggah berkas (multipart: `tipe`, `titik`, `peta`, `user`, `layer_titik`, `layer_peta`) → baris `runs` berstatus `menunggu` |
| GET | `/runs` | Daftar job (saring `tipe`, `status`, `kdkab`; paging `limit`/`offset`) |
| GET | `/runs/{id}` | Status job + jumlah baris hasil tersimpan |
| GET | `/runs/{id}/hasil` | Baris hasil titik (paging) |
| GET | `/runs/{id}/rekap?tingkat=` | Rekap progres per wilayah: `kabupaten`, `kecamatan`, `desa`, `sls` |

Belum ada autentikasi (T4). Isi `user` sementara dikirim lewat form.

## Alur pemrosesan

1. `POST /runs` menyimpan berkas ke `DIR_UNGGAHAN/<uuid>/` dan memeriksa metadata:
   kolom wajib ada, layer yang dipakai, dan `kdkab` di peta harus tunggal
   (satu job = satu kabupaten/kota).
2. Worker mengambil job dengan `SELECT ... FOR UPDATE SKIP LOCKED` (MySQL 8), jadi aman
   dijalankan beberapa worker sekaligus (`MAX_WORKERS`). Satu job aktif per
   (kdkab, tipe); job antre lama untuk itu ditandai `digantikan` (yang terbaru dikerjakan).
3. Worker menjalankan `app.proses_a.proses_a` atau `app.proses_b.proses_b`, lalu menyimpan
   hasil ke `titik_hasil` per batch 10.000 baris (`runs.jumlah_baris` diperbarui tiap batch).
4. Job sukses: hasil job lain untuk (kdkab, tipe) yang sama dihapus dan job lama ditandai
   `digantikan`. Job gagal: hasil separuh dibuang, status `gagal` + pesan di `runs.pesan`.

Status job: `menunggu` → `jalan` → `sukses` / `gagal` (atau `digantikan`).

## Isi

- `app/config.py` — setelan dari `.env` (MySQL, CORS, folder unggahan, worker)
- `app/db.py` — engine + sesi SQLAlchemy (MySQL lewat PyMySQL)
- `app/models.py` — tabel `runs` dan `titik_hasil` (PRD §7)
- `app/proses_a.py`, `app/proses_b.py` — hitungan spasial (model QGIS 01 & 02)
- `app/layanan.py` — pemeriksaan unggahan, pembuatan job, query hasil & rekap
- `app/worker.py` — worker Proses A/B (klaim job, batch simpan, ganti hasil lama)
- `app/api.py` — endpoint FastAPI
- `migrations/` — migrasi Alembic (`alembic upgrade head`)
- `tests/` — tes pytest (SQLite sementara; tes di `docs/` ditandai `slow`)
