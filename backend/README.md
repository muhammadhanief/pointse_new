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
.venv\Scripts\python.exe -m alembic upgrade head   # buat tabel runs, wilayah, titik_hasil, rekap_subsls
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
| GET | `/runs/{id}` | Status job + jumlah baris hasil tersimpan + `jumlah_tanpa_wilayah` |
| GET | `/runs/{id}/hasil` | Baris hasil titik (paging); wilayah dibalas sebagai `wilayah_tugas`, `wilayah_asal`, `wilayah_edit` |
| GET | `/runs/{id}/rekap?tingkat=&dasar=` | Rekap progres per wilayah: `kabupaten`, `kecamatan`, `desa`, `sls`, `subsls`; `dasar` = `tugas` (bawaan) atau `posisi`; tiap baris memuat `jumlah`, `belum`, `sudah_posisi`, `sudah_manual`, `tanpa_wilayah`, `persen_belum`; kategori `wilayah_id` NULL dibalas sebagai kode `null` + nama "(tanpa wilayah)" dan ditaruh paling akhir |

Belum ada autentikasi (T4). Isi `user` sementara dikirim lewat form.

## Alur pemrosesan

1. `POST /runs` menyimpan berkas ke `DIR_UNGGAHAN/<uuid>/` dan memeriksa metadata:
   kolom wajib ada, layer yang dipakai, dan `kdkab` di peta harus tunggal
   (satu job = satu kabupaten/kota).
2. Worker mengambil job dengan `SELECT ... FOR UPDATE SKIP LOCKED` (MySQL 8), jadi aman
   dijalankan beberapa worker sekaligus (`MAX_WORKERS`). Satu job aktif per
   (kdkab, tipe); job antre lama untuk itu ditandai `digantikan` (yang terbaru dikerjakan).
3. Worker meng-upsert dimensi wilayah dari peta ke `wilayah`, menjalankan
   `app.proses_a.proses_a` atau `app.proses_b.proses_b`, lalu menyimpan hasil ke
   `titik_hasil` per batch 10.000 baris (`runs.jumlah_baris` diperbarui tiap batch).
4. Job sukses: rekap per SubSLS (dasar `tugas` dan `posisi`) dihitung dengan query
   GROUP BY dan disimpan sebagai snapshot di `rekap_subsls`; hasil titik job lain untuk
   (kdkab, tipe) yang sama dihapus dan job lama ditandai `digantikan` (**hanya**
   `titik_hasil` yang dihapus — baris `runs` dan snapshot `rekap_subsls` tetap ada).
   Job gagal: hasil separuh dibuang, status `gagal` + pesan di `runs.pesan`.

Status job: `menunggu` → `jalan` → `sukses` / `gagal` (atau `digantikan`).

## Skema basis data

| Tabel | Isi |
|---|---|
| `runs` | satu baris per job (berkas masukan, status, `jumlah_baris`, `jumlah_tanpa_wilayah` = titik di luar poligon wilkerstat) |
| `wilayah` | dimensi wilayah: satu baris per SubSLS (`idsubsls`) dengan kode + nama; diisi dari peta lewat **upsert** dan tidak pernah dihapus |
| `titik_hasil` | hasil per titik: kunci `(run_id, urut)`, flag (`flag_repair`, `flag_position`, …), `kk/btt/bku/bttk/bbtt`, `usaha`, koordinat, `level_6_full_code`, dan wilayah lewat `wilayah_asal_id`/`wilayah_edit_id` |
| `rekap_subsls` | snapshot rekap per SubSLS per job: `jumlah`, `belum`, `sudah_posisi`, `sudah_manual`, `tanpa_wilayah` untuk dua `dasar` (`tugas` = `level_6_full_code`, `posisi` = hasil join peta) |

Nama/kode wilayah tidak lagi disimpan di `titik_hasil` (dinormalkan ke `wilayah`), dan
dashboard membaca `rekap_subsls` sehingga tidak perlu memindai `titik_hasil`.

Arti hitungan (PRD §5) dan baris kategori "(tanpa wilayah)":

- `belum` = `flag_repair` = 1; `sudah_posisi` = `flag_repair` = 0 dan
  `flag_edit_atr_repair` bukan 1 (Proses A yang kolomnya NULL dianggap 0);
  `sudah_manual` = `flag_repair` = 0 dan `flag_edit_atr_repair` = 1; `jumlah` =
  `belum` + `sudah_posisi` + `sudah_manual`.
- `tanpa_wilayah` = titik pada baris itu yang tidak masuk poligon wilkerstat mana pun
  (keterangan tersendiri, bisa tumpang tindih dengan `belum`).
- `wilayah_id` NULL = kategori terpisah "(tanpa wilayah)": dasar `tugas` untuk
  `level_6_full_code` kosong / tidak ada di tabel `wilayah`, dasar `posisi` untuk titik di
  luar semua poligon. Kunci utama `rekap_subsls` memakai `id` (`UNIQUE (run_id, dasar,
  wilayah_id)`) karena MySQL tidak mengizinkan kolom kunci utama bernilai NULL; jumlah
  tiap dasar tetap sama dengan `runs.jumlah_baris`.

## Isi

- `app/config.py` — setelan dari `.env` (MySQL, CORS, folder unggahan, worker)
- `app/db.py` — engine + sesi SQLAlchemy (MySQL lewat PyMySQL)
- `app/models.py` — tabel `runs`, `wilayah`, `titik_hasil`, `rekap_subsls` (PRD §7)
- `app/wilayah.py` — dimensi wilayah (baris dari peta, upsert, pemetaan kode → id; kode di
  luar peta dibiarkan tanpa id, bukan dibuatkan baris seadanya)
- `app/proses_a.py`, `app/proses_b.py` — hitungan spasial (model QGIS 01 & 02), murni tanpa I/O
- `app/layanan.py` — pemeriksaan unggahan, pembuatan job, query hasil & rekap
- `app/worker.py` — worker Proses A/B (klaim job, batch simpan, dimensi wilayah, rekap)
- `app/api.py` — endpoint FastAPI
- `migrations/` — migrasi Alembic (`alembic upgrade head`; `0002` normalisasi skema, `0003`
  hitungan rekap terpisah + baris "(tanpa wilayah)")
- `tests/` — tes pytest (SQLite sementara; tes data penuh di `docs/` ditandai `slow`:
  `test_proses_a_qgis.py`, `test_proses_b_qgis.py`, dan `test_proses_b_edit_qgis.py` untuk
  data uji yang sudah diedit)
