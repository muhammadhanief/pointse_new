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
.venv\Scripts\python.exe -m alembic upgrade head   # buat semua tabel (termasuk geotag_master)
.venv\Scripts\python.exe -m alembic check          # pastikan skema DB = model ORM
```

Pengembangan lokal memakai **MySQL 8.0.30 dari Laragon** (`127.0.0.1:3306`, user `root`
tanpa password) dan database `pointse`:

```sql
CREATE DATABASE pointse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Lalu isi `backend/.env` dengan `DB_HOST=127.0.0.1`, `DB_PORT=3306`, `DB_USER=root`,
`DB_PASSWORD=`, dan `DB_NAME=pointse`. Migrasi `0005` sudah memakai
`DEFAULT (CURRENT_DATE)` agar kompatibel dengan MySQL 8 (MariaDB menerima keduanya).

## Jalan & tes

```powershell
# API (worker ikut nyala, lihat WORKER_ENABLED di .env)
.venv\Scripts\python.exe -m uvicorn app.main:app --reload      # http://127.0.0.1:8000/docs

# Worker terpisah (mis. di server lain / proses sendiri)
.venv\Scripts\python.exe -m app.worker

# Tes (tanpa MySQL: tes memakai SQLite sementara)
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -q -m "not slow"           # 15 detik; tanpa tes data penuh docs/
.venv\Scripts\python.exe -m pytest -q -m "slow"               # ±2,5 menit: baca GPKG 397.443 titik
```

## Endpoint API (T3)

| Method | Alamat | Keterangan |
|---|---|---|
| GET | `/health` | Cek aplikasi hidup |
| POST | `/geotag-master` | Unggah **geotag master** per kabupaten/kota (multipart: `kdprov`, `kdkab` 4 digit, `titik`, `user`, `layer`, `tanggal_data`). Berkas disimpan permanen di `DIR_MASTER`; semua `level_6_full_code` yang terisi harus berawalan `kdprov`+`kdkab` |
| GET | `/geotag-master` | Daftar versi geotag master (saring `kdprov`/`kdkab`, paging), terbaru lebih dulu |
| POST | `/runs` | Unggah berkas (multipart: `tipe`, `titik`, `peta`, `user`, `layer_titik`, `layer_peta`, `tanggal_data`) -> baris `runs` berstatus `menunggu`. **Proses A:** kirim `peta` saja; master dicari otomatis (409 kalau belum ada). **Proses B:** kirim `titik` saja (GPKG hasil edit A); peta diambil dari run A sukses terakhir. Mengirim kedua berkas tetap didukung untuk mode manual/uji |
| GET | `/runs` | Daftar job (saring `tipe`, `status`, `kdprov`, `kdkab`; paging `limit`/`offset`), terbaru lebih dulu |
| GET | `/ringkasan` | Ringkasan provinsi: satu baris per kabupaten/kota dari run terakhir, dibaca dari `rekap_kabupaten` (saring `tipe`/`kdprov`/`kdkab`, `dasar`); menyertakan `persen_progres` dan `belum_ada_upload_tipe_b` |
| GET | `/tren` | Tren progres per `tanggal_data` (run sukses terakhir pada tanggal itu); `tingkat` = `kabupaten` (bawaan) atau `provinsi` |
| GET | `/perubahan` | Perubahan antara dua run (`run_awal`, `run_akhir`): selisih rekap kabupaten/desa + perubahan status per titik (hanya pasangan baseline vs sukses terakhir yang detailnya masih ada) |
| GET | `/runs/{id}` | Status job + jumlah baris hasil tersimpan + `jumlah_tanpa_wilayah` + `detail_tersedia` |
| GET | `/runs/{id}/hasil` | Baris hasil titik (paging); **hanya titik yang perlu perhatian** (titik `benar_awal` tidak disimpan, terhitung di rekap) |
| GET | `/runs/{id}/rekap?tingkat=&dasar=` | Rekap progres per wilayah: `kabupaten`, `kecamatan`, `desa` dari snapshot `rekap_kabupaten`/`rekap_desa`; `sls`/`subsls` dihitung saat diminta dari `titik_hasil` (409 bila detail run itu sudah dipangkas); `dasar` = `tugas` (bawaan) atau `posisi`; tiap baris memuat `jumlah`, `belum`, `benar_awal`, `ditindak_posisi_benar`, `ditindak_posisi_salah`, `digeser`, `tanpa_wilayah`, `persen_progres` (kosong kalau penyebutnya 0); kategori tanpa wilayah dibalas kode `null` + nama "(tanpa wilayah)" dan ditaruh paling akhir |
| GET | `/runs/{id}/ekspor/hasil-a.gpkg` | Unduh **keluaran Proses A** sebagai GPKG untuk diedit di QGIS (layer `hasil_identifikasi_titik`, kolom + urutan sama dengan model QGIS, EPSG:4326). Dihitung ulang dari berkas mentah run lalu di-cache (2 berkas terbaru); 409 kalau run bukan tipe A, belum sukses, atau berkas mentahnya sudah dipangkas |
| GET | `/runs/{id}/ekspor/titik.csv` | Unduh **titik perlu tindakan** run ini sebagai CSV (dari `titik_hasil`); 409 kalau detail run itu sudah dipangkas |
| GET | `/runs/{id}/ekspor/titik.gpkg` | Unduh titik perlu tindakan sebagai GPKG (titik EPSG:4326; pakai koordinat edited kalau ada, kalau tidak origin) |
| GET | `/ekspor/rekap.csv?tingkat=&tipe=&kdprov=&kdkab=&dasar=&tanggal_awal=&tanggal_akhir=` | Unduh rekap **kabupaten** atau **desa** sebagai CSV; satu baris per run per wilayah, rentang `tanggal_data` inklusif |

Semua endpoint selain `/health` membutuhkan header `Authorization: Bearer <token sesi>`.
Token dibuat frontend setelah login SSO BPS (lihat `frontend/README.md`) dan diverifikasi
backend memakai `AUTH_SECRET` yang sama. Isi `user` dari form diabaikan saat SSO aktif.
CSV memakai UTF-8 tanpa BOM dan pemisah koma.

### Autentikasi dan peran (T4)

- `AUTH_REQUIRED=true` (bawaan) mewajibkan token. `AUTH_REQUIRED=false` hanya untuk tes/mode
  lokal tanpa SSO.
- `AUTH_SECRET` minimal 32 karakter dan harus sama dengan `AUTH_SECRET` frontend.
- `org` SSO 4/5 digit dipetakan ke peran oleh `app/peran.py`: `3300`/`33000` = admin provinsi
  `33`; `3307`/`33070` = petugas kabupaten/kota `3307`.
- Admin provinsi hanya boleh mengunggah geotag master, tetapi boleh menjalankan Proses A/B
  dan melihat data kabupaten/kota di provinsinya (pengawasan/uji). Petugas kabupaten/kota
  hanya boleh menjalankan Proses A/B dan melihat kabupaten/kotanya. Filter wilayah pada
  endpoint daftar/ringkasan/tren/ekspor otomatis dibatasi ke wilayah pengguna.
- `runs.kdkab` bisa berbentuk kode peta pendek (`07`) atau 4 digit (`3307`); penyaring
  mencocokkan keduanya.

## Alur pemrosesan

1. **Geotag master (admin provinsi).** `POST /geotag-master` menyimpan geotag asli
   ke `DIR_MASTER/<kdkab>/<uuid>/` (permanen, tidak ikut pemangkasan) dan memeriksa
   bahwa semua `level_6_full_code` yang terisi berawalan kode kabupaten/kota 4 digit
   (`kdprov`+`kdkab`, mis. `3307`). Versi lama tidak dihapus.
2. **Proses A (kabupaten/kota).** `POST /runs` dengan `tipe=A` cukup mengirim `peta`.
   Peta disimpan ke `DIR_UNGGAHAN/<uuid>/`, `kdprov`/`kdkab` dibaca dari peta, lalu
   geotag master terbaru untuk kabupaten itu dipakai sebagai berkas titik. Kalau
   master belum ada, unggahan ditolak `409` dan tidak ada job yang dibuat. Run A
   mencatat `geotag_master_id`, sehingga master baru hanya memengaruhi run A baru.
3. **Proses B (kabupaten/kota).** `POST /runs` dengan `tipe=B` cukup mengirim `titik`
   (GPKG keluaran Proses A yang sudah diedit). Kabupaten/kota ditentukan dari 4 digit
   pertama `level_6_full_code`; backend memakai run A sukses terakhir, menyalin peta
   run A ke folder job B, dan mencatat `sumber_run_a_id`. Tidak perlu unggah peta lagi.
4. `POST /runs` dengan kedua berkas tetap didukung untuk mode manual/uji (dan data lama).
5. Worker mengambil job dengan `SELECT ... FOR UPDATE SKIP LOCKED` (MySQL 8), jadi aman
   dijalankan beberapa worker sekaligus (`MAX_WORKERS`). Job dikerjakan **sesuai urutan
   unggah** (id terkecil dulu) dan hanya **satu job aktif** per (`kdprov`, `kdkab`, `tipe`);
   job antre lain untuk kabupaten/tipe itu dibiarkan `menunggu` sampai gilirannya
   (tidak ada job yang dibatalkan/ditandai `digantikan`).
6. Worker meng-upsert dimensi wilayah dari peta ke `wilayah`, menjalankan
   `app.proses_a.proses_a` atau `app.proses_b.proses_b`, lalu menyimpan hasil ke
   `titik_hasil` per batch 10.000 baris (`runs.jumlah_baris` diperbarui tiap batch).
7. Job sukses (satu transaksi): rekap dihitung lewat query GROUP BY (`app/rekap.py`) dan
   disimpan sebagai snapshot di `rekap_kabupaten` + `rekap_desa`, `runs` diisi
   `jumlah_baris`/`jumlah_tanpa_wilayah`/`detail_tersedia`, lalu `titik_hasil` dan berkas
   mentah run lain untuk (`kdprov`, `kdkab`, `tipe`) yang sama dipangkas — hanya **baseline**
   (sukses pertama) dan **sukses terakhir** yang menyimpan detail. Baris `runs` dan seluruh
   snapshot rekap tidak pernah dihapus. Job gagal: hasil separuh dibuang,
   status `gagal` + pesan di `runs.pesan`.

Status job: `menunggu` → `jalan` → `sukses` / `gagal`.

### Mode hemat memori (`PROSES_CHUNK_TITIK`)

Set `PROSES_CHUNK_TITIK` > 0 (mis. `50000`) untuk membaca titik per potongan
dengan `pyogrio` (`skip_features`/`max_features`) sementara peta tetap utuh di
memori. Hasil tiap potongan langsung di-`upsert` ke `titik_hasil` per batch
10.000 baris; `assignment_id` ganda lintas potongan dimenangkan oleh baris yang
paling awal pada urutan hasil (sama dengan mode biasa). Karena kunci urut
sementara bisa melebihi `INTEGER`, `titik_hasil.urut` kini `BIGINT`; setelah
rekap dihitung, urut dirapikan menjadi peringkat `0..n-1` sebelum pemangkasan,
jadi hasil akhir (termasuk celah `urut` setelah pemangkasan) identik dengan mode
biasa. Nilai `0` (default) memakai mode lama (seluruh titik sekaligus).

### Worker cron dan job menggantung

- `python -m app.worker --once` mengambil **paling banyak satu** job, memproses,
  lalu keluar. Kunci `GET_LOCK` MariaDB mencegah dua pemanggilan cron berjalan
  bersamaan (di SQLite/tes kunci ini no-op).
- Worker memperbarui `runs.heartbeat_at` tiap batch. Job `jalan` yang heartbeat-nya
  lebih lama dari `JOB_TIMEOUT_MENIT` (default 10) dianggap terhenti: statusnya
  `gagal`, pesannya "proses terhenti, kemungkinan dimatikan server", hasil
  separuhnya dibersihkan, dan aturan satu job aktif tidak lagi menghalangi unggahan
  baru untuk kabupaten/tipe itu.

### Alat ukur

`scripts/ukur_proses_a.py` mengukur waktu per tahap dan puncak RSS tanpa basis
data. Di Linux/macOS memakai `resource.getrusage`; di Windows memakai API
`K32GetProcessMemoryInfo` lewat `scripts/_memori.py` (tanpa `psutil`).

```powershell
.venv\Scripts\python.exe scripts\ukur_proses_a.py --titik <GPKG> --peta <GeoJSON> --chunk 0
.venv\Scripts\python.exe scripts\ukur_proses_a.py --titik <GPKG> --peta <GeoJSON> --chunk 50000
```

## Skema basis data

| Tabel | Isi |
|---|---|
| `runs` | satu baris per job: `tipe`, `kdprov`/`kdkab`, `tanggal_data` (tanggal data) + `created_at` (waktu unggah), status, `jumlah_baris`, `jumlah_tanpa_wilayah` (titik di luar poligon wilkerstat), `detail_tersedia` (baris `titik_hasil` masih disimpan), berkas masukan, `geotag_master_id` (versi master untuk run A), `sumber_run_a_id` (run A sumber peta untuk run B) |
| `geotag_master` | versi geotag asli per kabupaten/kota dari admin provinsi: `kdprov`, `kdkab` 4 digit, `tanggal_data`, nama/berkas/layer, jumlah baris, pengunggah, `created_at`; berkas disimpan permanen di `DIR_MASTER`, tidak pernah ikut pemangkasan |
| `wilayah` | dimensi wilayah: satu baris per SubSLS (`idsubsls`) dengan kode + nama; diisi dari peta lewat **upsert** dan tidak pernah dihapus |
| `titik_hasil` | hasil per titik: kunci `(run_id, urut)`, flag (`flag_repair`, `flag_position`, …), `kk/btt/bku/bttk/bbtt`, `usaha`, koordinat, `level_6_full_code`, dan wilayah lewat `wilayah_asal_id`/`wilayah_edit_id`. **Hanya titik yang perlu perhatian** yang disimpan (`flag_repair` = 1, `flag_edit_atr_repair` = 1, atau tanpa wilayah); titik `benar_awal` hanya terhitung di rekap |
| `rekap_desa` | snapshot rekap per **desa** (`kdprov`+`kdkab`+`kdkec`+`kddesa`) per job per `dasar`, plus baris "(tanpa wilayah)"; kunci utama `id` + `UNIQUE (run_id, dasar, kdprov, kdkab, kdkec, kddesa)` |
| `rekap_kabupaten` | rekap yang sama dijumlahkan per **kabupaten/kota** (`kdprov`+`kdkab`) per job per `dasar`; dipakai ringkasan dan tren |

Nama/kode wilayah tidak lagi disimpan di `titik_hasil` (dinormalkan ke `wilayah`), dan
dashboard membaca `rekap_kabupaten`/`rekap_desa` sehingga tidak perlu memindai `titik_hasil`.
Ukuran tiap tabel pada data uji penuh dan catatan pemangkasan ada di [`../README.md`](../README.md).

Arti hitungan (PRD §5) dan baris kategori "(tanpa wilayah)":

- `belum` = `flag_repair` = 1; `benar_awal` = `flag_repair` = 0 dan `flag_edit_atr_repair`
  bukan 1 (Proses A yang kolomnya NULL dianggap 0); `ditindak_posisi_benar` = `flag_repair` = 0,
  `flag_edit_atr_repair` = 1, `flag_repair_initial` = 0; `ditindak_posisi_salah` =
  `flag_repair` = 0, `flag_edit_atr_repair` = 1, `flag_repair_initial` = 1; `jumlah` =
  `belum` + `benar_awal` + `ditindak_posisi_benar` + `ditindak_posisi_salah`.
- `digeser` = titik dengan `flag_position` = 1 dan `tanpa_wilayah` = titik pada baris itu yang
  tidak masuk poligon wilkerstat mana pun (keduanya keterangan tersendiri, bisa tumpang tindih
  dengan kolom lain).
- Persentase progres dihitung saat dibaca (`app.layanan.rekap_run`, `app.layanan.ringkasan`),
  tidak disimpan: (`ditindak_posisi_benar` + `ditindak_posisi_salah`) /
  (`belum` + `ditindak_posisi_benar` + `ditindak_posisi_salah`); kosong (`null`) kalau
  penyebutnya 0.
- Baris "(tanpa wilayah)" (kode desa `null`) = kategori terpisah: dasar `tugas` untuk
  `level_6_full_code` kosong / tidak ada di tabel `wilayah`, dasar `posisi` untuk titik di
  luar semua poligon. Kunci utama `rekap_desa` memakai `id` (dengan `UNIQUE (run_id, dasar,
  kdprov, kdkab, kdkec, kddesa)`) karena MySQL tidak mengizinkan kolom kunci utama bernilai
  NULL; jumlah tiap dasar tetap sama dengan `runs.jumlah_baris`.
- Rekap tingkat desa dikelompokkan per (`kdkec`, `kddesa`) karena peta memakai kode wilayah
  pendek (`kddesa` bisa berulang antar kecamatan); nama desa ikut dibalas supaya bisa
  dibedakan di tampilan (catatan untuk UI T7).

## Ekspor (fitur 5)

Alur kerja yang didukung: **unduh GPKG keluaran Proses A → edit di QGIS → unggah hasil edit
sebagai masukan Proses B**.

- `GPKG` keluaran A dihitung ulang dari berkas mentah run (bukan dari `titik_hasil` yang
  sudah dirampingkan), jadi isinya sama dengan model QGIS: layer `hasil_identifikasi_titik`,
  30 kolom + `geom`, EPSG:4326, urutan baris hasil Proses A. Hasil disimpan di
  `DIR_UNGGAHAN/_ekspor/` dengan batas `MAKS_CACHE_HASIL_A` (2) berkas terbaru; unduhan
  pertama pada data uji 397.364 baris ±25 detik dan ±124 MB, unduhan berikutnya ±0,1 detik.
- `titik.csv`/`titik.gpkg` berisi titik yang disimpan di `titik_hasil` (hanya yang perlu
  perhatian), termasuk kode wilayah tugas/asal/edit dan koordinat origin/edited.
- `rekap.csv` berisi snapshot `rekap_kabupaten`/`rekap_desa` per run, dengan nama wilayah
  dari tabel `wilayah`; baris "(tanpa wilayah)" diberi nama `(tanpa wilayah)` dan kode kosong.
- Tes `tests/test_ekspor.py` memuat tes pulang-pergi: GPKG hasil ekspor A diunggah sebagai
  masukan B tanpa edit, lalu rekap B harus sama dengan rekap A (tidak ada titik tergeser,
  `flag_edit_atr_repair` = 0).

## Isi

- `app/config.py` — setelan dari `.env` (MySQL, CORS, auth, folder unggahan, worker)
- `app/db.py` — engine + sesi SQLAlchemy (MySQL lewat PyMySQL)
- `app/auth.py` — verifikasi token sesi HS256 + pembatasan wilayah per peran
- `app/peran.py` — pemetaan `org` SSO 4/5 digit ke peran
- `app/models.py` — tabel `runs`, `wilayah`, `titik_hasil`, `rekap_desa`, `rekap_kabupaten` (PRD §7)
- `app/wilayah.py` — dimensi wilayah (baris dari peta, upsert, pemetaan kode → id; kode di
  luar peta dibiarkan tanpa id, bukan dibuatkan baris seadanya)
- `app/proses_a.py`, `app/proses_b.py` — hitungan spasial (model QGIS 01 & 02), murni tanpa I/O
- `app/rekap.py` — query GROUP BY rekap + `simpan_rekap` + `pangkas_titik_hasil`; tanpa
  dependensi berat, dipakai worker **dan** migrasi `0005` supaya logikanya tidak bercabang
- `app/layanan.py` — pemeriksaan unggahan, pembuatan job, query hasil, rekap, ringkasan, tren, perubahan
- `app/ekspor.py` — ekspor GPKG keluaran Proses A (dengan cache LRU), titik perlu tindakan
  (CSV/GPKG), dan rekap kabupaten/desa (CSV)
- `app/worker.py` — worker Proses A/B (klaim job FIFO, batch simpan, dimensi wilayah, rekap, pemangkasan)
- `app/api.py` — endpoint FastAPI
- `migrations/` — migrasi Alembic (`alembic upgrade head`; `0002` normalisasi skema, `0003`
  baris "(tanpa wilayah)" untuk rekap, `0004` kolom hitungan rekap dipisah, `0005` rekap
  desa/kabupaten + `runs.tanggal_data`/`kdprov`/`detail_tersedia` + pemangkasan `titik_hasil`
  dan berkas mentah, `rekap_subsls` dihapus)
- `tests/` — tes pytest (SQLite sementara; tes data penuh di `docs/` ditandai `slow`:
  `test_proses_a_qgis.py`, `test_proses_b_qgis.py`, dan `test_proses_b_edit_qgis.py` untuk
  data uji yang sudah diedit)
