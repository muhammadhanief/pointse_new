# AGENTS.md

## Konteks
- Aplikasi monitoring progres editing batas Wilkerstat BPS; baca `PRD.md` sebelum task, terutama bagian Proses dan Keputusan.
- Backend: AlmaLinux 8/aaPanel, 4 core (i5), RAM 7,6 GB (~2,8 GB tersedia), HDD, swap 8 GB; systemd 239, Python 3.11+ (bawaan 3.6 tidak dipakai), MariaDB 10.11.
- API: FastAPI/uvicorn langsung (bukan Passenger), satu worker uvicorn, service `pointse-api`, `MemoryMax=1G`.
- Worker: service `pointse-worker` menjalankan `--loop`, `MemoryMax=1500M`, `Nice=10`, `WORKER_MEM_BUDGET_MB=800`, `fcntl.flock`.
- Frontend: Next.js static export di cPanel; batas akun cPanel tetap 1 GB TOTAL (idle ±366 MB). Frontend memanggil API lintas origin dengan `NEXT_PUBLIC_API_BASE` dan Bearer; tanpa cookie, rewrite, atau rute API Next.js di production.
- File spasial di disk; MariaDB InnoDB tanpa PostGIS dan tanpa geometri di DB.

## Perintah
- Venv: `cd backend; python -m venv .venv`
- Install: `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt`
- API lokal: `cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --reload`
- Tes: `cd backend; .venv\Scripts\python.exe -m pytest -q`
- Worker sekali: `cd backend; python -m app.worker --once`
- Worker service lokal: `cd backend; python -m app.worker --loop`
- Frontend: `cd frontend; npm run dev`; build: `npm run build` dengan `NEXT_PUBLIC_API_BASE`.
- Migrasi: `cd backend; alembic upgrade head`
- Deploy/backup: `deploy/deploy.sh`, `deploy/backup.sh`; panduan `deploy/README.md`.
- Pantau worker: `cd backend; python scripts/pantau_worker.py`

## Aturan keras
- Jangan ubah `proses_a.py`/`proses_b.py` kecuali diminta; replikasi logika model QGIS PERSIS.
- API tidak boleh mengimpor pandas/geopandas/pyogrio/shapely saat startup; impor berat hanya di modul worker.
- Anggaran memori worker `WORKER_MEM_BUDGET_MB=800`; hormati batas RAM server dan jangan menjalankan proses paralel di luar systemd/cron.
- Unggahan: body mentah `application/octet-stream`; dilarang FormData/multipart (WAF: isi biner berlabel form 403, body form di atas ±1 MB 413). Batas body 128 MiB/request; berkas besar lewat potongan 16 MiB, resume, dan hash per potongan.
- CORS hanya origin frontend; `Authorization: Bearer` saja, tanpa cookie/credentials. `ENV=production` menolak `AUTH_MODE=dev` dan mewajibkan `AUTH_SECRET`.
- `API_PREFIX` menentukan path API (default kosong); frontend memakai `NEXT_PUBLIC_API_BASE` yang sama.
- Nginx: HTTPS saja, `client_max_body_size 512m`, `client_body_timeout 600s`, `proxy_read_timeout 600s`, `proxy_request_buffering off`, `limit_req` 10 r/s per IP.
- MariaDB hanya dari `127.0.0.1`, satu database, satu pengguna aplikasi; `innodb_buffer_pool_size=768M`, `innodb_flush_log_at_trx_commit=2`.
- Jangan pakai QGIS/PyQGIS; hitungan spasial di Python.
- Hanya backend yang mengakses MariaDB; frontend selalu lewat API.
- Jangan mencetak atau menyimpan token, cookie, atau kata sandi di log, dokumen, atau commit.
- Jangan commit data mentah `docs/`, `.env`, atau kredensial.
- Satu task per sesi; jangan refactor di luar permintaan; tanya bila ambigu.
- Tambahkan tes untuk logika baru dan jalankan tes sebelum menyatakan selesai.
- Jawab ringkas dalam Bahasa Indonesia.
