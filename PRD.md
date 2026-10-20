# PRD: Monitoring Progres Editing Batas Wilkerstat

## 1. Tujuan

Web app untuk memantau progres perbaikan (editing) titik bangunan terhadap batas
wilkerstat (SLS/SubSLS) BPS, menggantikan pengecekan manual lewat model QGIS.
Semua hitungan spasial dilakukan dengan Python, tanpa QGIS/PyQGIS. Hasil Proses A
dan Proses B harus identik dengan keluaran model QGIS pada data uji.

## 2. Pengguna

Petugas dan pengawas BPS. Login memakai SSO BPS. Admin provinsi mengelola geotag
master per kabupaten/kota; petugas kabupaten/kota menjalankan Proses A/B dan
melihat data wilayahnya.

## 3. Arsitektur dan hosting

- **Frontend**: Next.js 16 + React 19 + Tailwind 4, dijalankan sebagai **Node.js
  App cPanel** agar callback SSO dan penjagaan halaman berjalan di server. Tidak
  ada Vercel dan tidak ada rute proxy API. Server cPanel tidak menjangkau domain
  backend.
- **Backend**: FastAPI Python **3.11+** dijalankan langsung sebagai ASGI dengan
  **uvicorn** (satu worker) pada server **AlmaLinux 8/aaPanel**, bukan Passenger.
  API mendengarkan loopback dan diproksikan nginx. Path API mengikuti
  `API_PREFIX` (default kosong, bukan `/backend`).
- **Frontend ↔ API**: browser memanggil API lintas origin secara **client-side**
  memakai `NEXT_PUBLIC_API_BASE` yang diisi saat build. Autentikasi hanya
  `Authorization: Bearer`; backend tidak menerima cookie atau credentials.
  Token Bearer dibaca dari cookie non-httpOnly yang ditulis callback SSO.
- **CORS**: hanya origin frontend (`CORS_ORIGINS`, default
  `https://pointse.web.bps.go.id`), metode `GET/POST/PUT/DELETE/OPTIONS`, dan
  header `Authorization`, `Content-Type`, `Accept`, `X-SHA256`. Preflight
  unggahan `application/octet-stream` harus lolos.
- **Database**: **MariaDB 10.11/InnoDB**. Tidak memakai PostgreSQL/PostGIS.
  Geometri dan berkas mentah tidak disimpan di database; hanya hasil hitungan dan
  metadata. Konfigurasi: `innodb_buffer_pool_size=768M`,
  `innodb_flush_log_at_trx_commit=2`, hanya loopback, satu database/pengguna.
- **Berkas mentah**: GeoJSON/GPKG disimpan di disk server. Berkas besar diunggah
  berpotongan dan dapat dilanjutkan.
- **Server backend**: AlmaLinux 8, 4 core, RAM 7,6 GB (~2,8 GB tersedia), disk
  HDD, swap 8 GB (lambat). systemd 239; Python 3.6 bawaan tidak dipakai. API
  `MemoryMax=1G`; worker `MemoryMax=1500M`, `Nice=10`.
- **Frontend cPanel**: batas akun tetap **1 GB TOTAL** (idle ±366 MB); proses di
  atas ±1.110 MB dimatikan tanpa pesan. Frontend statis harus tetap ringan.
- **Jaringan**: di depan server ada **F5** dan **WAF**. Body request dibatasi
  **128 MiB** per request. Nginx memakai HTTPS saja, `client_max_body_size 512m`,
  timeout 600 detik, `proxy_request_buffering off`, dan `limit_req` 10 r/s per IP.
- **Impor berat**: API tidak boleh mengimpor pandas/geopandas/pyogrio/shapely
  saat startup. Impor tersebut hanya boleh terjadi di modul worker.
- **Worker**: service systemd `python -m app.worker --loop` (polling 5 detik),
  `fcntl.flock` (bukan `GET_LOCK`), checkpoint tiap batch, heartbeat tiap 15 detik
  dan tiap batch. SIGTERM menyelesaikan batch berjalan lalu job dikembalikan ke
  antrean. `--once` tetap tersedia untuk cron. Anggaran memori
  `WORKER_MEM_BUDGET_MB=800`.

## 4. Input

1. **Peta batas wilkerstat lapangan** (poligon, GeoJSON). Kolom wajib: kdprov,
   kdkab, kdkec, kddesa, nmprov, nmkab, nmkec, nmdesa, idsls, nmsls, idsubsls.
2. **Titik bangunan** (GPKG, layer `geotag`). Kolom yang dipakai: assignment_id,
   unique_bang, flag_psls, level_6_full_code, geotag_latitude, geotag_longitude,
   no_bang, kode_bang_value, ada_keluarga_value, ada_bang_usaha_value, count_usaha,
   nama_usaha_bang.
3. **Geotag master** (GPKG, layer `geotag`) diunggah admin provinsi per
   kabupaten/kota, disimpan permanen, dan dipakai otomatis oleh Proses A. Semua
   `level_6_full_code` harus milik kabupaten/kota tersebut (4 digit pertama =
   `kdprov`+`kdkab`).
4. Untuk Proses B: **titik hasil pengolahan** (output Proses A yang sudah
   diedit/digeser). Peta tidak diunggah ulang; form memilih run Proses A sukses
   sebagai sumber peta, dengan pilihan awal run A sukses terakhir. Alur kerjanya:
   unduh GPKG keluaran Proses A dari aplikasi, edit titik di QGIS, lalu unggah
   hasil edit itu sebagai masukan Proses B.

## 5. Proses

Prinsip: **replikasi persis dulu** perilaku model QGIS, perbaikan belakangan.
Hasil harus identik dengan output QGIS pada data uji.

Di antarmuka, Proses A tampil sebagai **1. Identifikasi Titik** dan Proses B
sebagai **2. Pengecekan Titik**, di halaman terpisah. Istilah teknis A/B tetap
dipakai di API dan basis data. Nomor job yang tampil dihitung per
(`kdprov`, `kdkab`, `tipe`), bukan dari id global; versi master dihitung per
kabupaten/kota.

### Proses A: Identifikasi Titik (model `01_Identifikasi_Titik`)

1. Reproject peta dan titik ke EPSG:4326.
2. Spatial join titik ke poligon (titik masuk/menyentuh poligon). Di QGIS
   predikatnya intersects + within, dan hanya poligon cocok PERTAMA yang diambil.
   Titik yang tidak cocok tetap dipertahankan (kolom wilayah kosong).
   - GeoPandas: `sjoin(how="left", predicate="intersects")`, lalu ambil baris
     pertama per titik (titik di garis batas bisa cocok ke >1 poligon).
3. Gabungkan hasil cocok dan tidak cocok, buang duplikat berdasarkan
   `assignment_id`.
4. Bentuk kolom hasil:
   - `idsubsls_origin` = idsubsls hasil join
   - `latitude_origin` = geotag_latitude, `longitude_origin` = geotag_longitude
   - `flag_repair_initial` = `flag_repair` = 0 jika idsubsls == level_6_full_code,
     selain itu 1
   - `jumlah_usaha_ditemukan` = `usaha` = count_usaha
   - `kk` = 1 jika ada_keluarga_value in (1,2), else 0
   - `btt` = 1 jika kode_bang_value in (2,3)
   - `bku` = 1 jika kode_bang_value == 1
   - `bttk` = 1 jika kode_bang_value == 12
   - `bbtt` = 1 jika kode_bang_value in (4,5,6)
   - plus kolom identitas dan wilayah (assignment_id, unique_bang, flag_psls,
     level_6_full_code, no_bang, kode_bang_value, ada_keluarga_value,
     ada_bang_usaha_value, nama_usaha_bang, kdprov..nmdesa, nmsls)
5. Output: **Hasil Identifikasi Titik**.

### Proses B: Pengecekan Titik Hasil Penggeseran (model `02_Pengecekan_Titik`)

1. Input: titik hasil pengolahan (output A, sudah diedit) dan peta dari run A
   sukses yang dipilih pada form (disalin ke folder job B; tidak diunggah ulang
   oleh kabupaten/kota). Pilihan awal adalah run A sukses terakhir; run sumber
   harus berasal dari kabupaten/kota yang sama.
2. Hitung `latitude_edited`, `longitude_edited` dari geometri titik saat ini.
3. `flag_edit_atr_repair` = 1 jika `flag_repair` != `flag_repair_initial`, else 0
   (artinya atribut flag_repair diubah manual).
4. Spatial join ulang ke peta (aturan sama seperti A: ambil poligon pertama,
   pertahankan titik tak cocok), buang duplikat `assignment_id`.
5. Hitung ulang:
   - `idsubsls_edited` = idsubsls hasil join baru
   - `flag_position` = 0 jika `latitude_origin` == `latitude_edited`, else 1
     (model asli hanya membandingkan latitude)
   - `flag_repair_initial` = 0 jika level_6_full_code == idsubsls (hasil join
     baru), else 1
   - `flag_repair` akhir = 0 jika (flag_repair == 1 dan flag_repair_initial == 0);
     selain itu 1 jika (flag_repair_initial == 1 dan flag_edit_atr_repair == 0);
     selain itu tetap nilai flag_repair
6. Output: **Hasil Pengecekan Titik Hasil Penggeseran**.

### Indikator progres

Jumlah titik dipisah menjadi kategori berikut.

| Kategori | Aturan |
|---|---|
| `belum` | `flag_repair` = 1. |
| `benar_awal` | `flag_repair` = 0 dan `flag_edit_atr_repair` bukan 1; pada Proses A kolom itu NULL dan dianggap 0. |
| `ditindak_posisi_benar` | `flag_repair` = 0, `flag_edit_atr_repair` = 1, dan `flag_repair_initial` = 0. |
| `ditindak_posisi_salah` | `flag_repair` = 0, `flag_edit_atr_repair` = 1, dan `flag_repair_initial` = 1. |
| `digeser` | `flag_position` = 1; keterangan tersendiri, bisa tumpang tindih dengan kategori lain. |
| `tanpa_wilayah` | Titik tidak masuk poligon wilkerstat mana pun; keterangan tersendiri, bisa tumpang tindih dengan `belum`. |

Rumus:

- `jumlah` = `belum` + `benar_awal` + `ditindak_posisi_benar` +
  `ditindak_posisi_salah`.
- `persen_progres` = (`ditindak_posisi_benar` + `ditindak_posisi_salah`) /
  (`belum` + `ditindak_posisi_benar` + `ditindak_posisi_salah`) × 100.
- `benar_awal` dan `digeser` tidak masuk penyebut. Kalau penyebutnya 0,
  `persen_progres` kosong (bukan 0%).

Titik yang tidak bisa dipetakan ke wilayah pada dasar rekap yang dipakai dihitung
sebagai kategori terpisah "(tanpa wilayah)", sehingga jumlah tiap dasar selalu
utuh. Rekap tersedia per kabupaten/kota, kecamatan, desa, dan SLS/SubSLS.

Kunci kabupaten/kota di seluruh rekap adalah (`kdprov`, `kdkab`). Rekap tingkat
desa dikelompokkan per (`kdkec`, `kddesa`) dan nama desa ikut disimpan/dibalas,
karena peta wilkerstat memakai kode wilayah pendek sehingga kode desa bisa
berulang antar kecamatan. Tingkat kecamatan dan desa tersedia dari tabel rekap;
tingkat SLS/SubSLS dihitung saat diminta (hanya untuk run yang detail titiknya
masih disimpan).

Setiap rekap disimpan untuk dua dasar:

- `tugas` = `level_6_full_code` titik;
- `posisi` = hasil join peta: `wilayah_edit_id` bila ada, kalau tidak
  `wilayah_asal_id`.

## 6. Fitur (urut prioritas)

1. **Login SSO BPS** (bypass hanya untuk pengujian lokal; tidak boleh aktif di
   production).
2. **Master geotag** per kabupaten/kota: unggah, versi, dan pemakaian otomatis
   oleh Proses A.
3. **Proses A (1. Identifikasi Titik)**: unggah peta, jalankan job, pantau status.
4. **Proses B (2. Pengecekan Titik)**: unggah GPKG hasil edit, pilih peta dari run
   A sukses, jalankan, pantau status.
5. **Dashboard rekap progres** per wilayah (tabel + filter, `tugas`/`posisi`,
   ekspor rekap).
6. **Ekspor hasil**: GPKG keluaran Proses A untuk bahan edit QGIS, titik perlu
   tindakan (CSV/GPKG), dan rekap kabupaten/desa (CSV).
7. **Status Sistem**: status worker, heartbeat, antrean job, progres job aktif,
   pemakaian memori/disk, sesi unggahan sementara, dan kondisi cadangan database.
8. **Peta visualisasi titik** (opsional, terakhir).

## 7. Skema MariaDB terbaru

Sembilan tabel; geometri/peta mentah tidak pernah masuk database, hanya berkas di
disk server.

- `runs`: satu baris per job. Berisi id, tipe (A/B), `kdprov` + `kdkab`, user,
  status (`menunggu`, `jalan`, `sukses`, `gagal`), nama + path berkas input/peta,
  layer, `jumlah_baris`, `jumlah_tanpa_wilayah`, `tanggal_data` (tanggal data,
  default tanggal unggah, boleh diisi saat unggah), `detail_tersedia` (1 = baris
  `titik_hasil` run ini masih disimpan), `geotag_master_id`, `sumber_run_a_id`,
  pesan galat, serta created/started/finished/heartbeat.
  Index: `kdprov`+`kdkab`, `status`, `tipe`.
- `geotag_master`: satu baris per versi geotag asli kabupaten/kota. Berisi id,
  `kdprov`, `kdkab` 4 digit, `tanggal_data`, nama/berkas/layer, `jumlah_baris`,
  user, `created_at`. Berkas disimpan permanen di `DIR_MASTER` dan tidak ikut
  pemangkasan; versi lama tidak dihapus karena masih dirujuk run A lama.
- `wilayah`: dimensi wilayah, satu baris per SubSLS. Berisi id, `idsubsls` (unik),
  `idsls`, `nmsls`, `kdprov`..`nmdesa`. Diisi dari peta lewat upsert (nama
  disegarkan, tidak pernah dihapus); kode di luar peta tidak dibuatkan baris
  seadanya.
- `titik_hasil`: hasil per titik (ramping). Kunci `(run_id, urut)`, unik
  `(run_id, assignment_id)`; `assignment_id`, `level_6_full_code`,
  `wilayah_asal_id`/`wilayah_edit_id` (FK ke `wilayah`, boleh NULL), flag
  (`flag_psls`, `flag_position`, `flag_edit_atr_repair`, `flag_repair_initial`,
  `flag_repair`), `kk`/`btt`/`bku`/`bttk`/`bbtt`, `usaha`, dan koordinat
  origin/edited. Nama dan kode wilayah tidak disimpan di sini. Hanya titik yang
  perlu perhatian (`flag_repair` = 1, `flag_edit_atr_repair` = 1, atau tidak
  masuk poligon mana pun) yang disimpan; titik `benar_awal` hanya terhitung di
  rekap.
- `rekap_desa`: snapshot rekap per **desa** per job. Kunci utama `id`, unik
  `(run_id, dasar, kdprov, kdkab, kdkec, kddesa)`; kolom `jumlah`, `belum`,
  `benar_awal`, `ditindak_posisi_benar`, `ditindak_posisi_salah`, `digeser`,
  `tanpa_wilayah`, dan `dasar` (`tugas`/`posisi`). Baris `kddesa` NULL =
  kategori "(tanpa wilayah)". Index: `(run_id, dasar)`.
- `rekap_kabupaten`: rekap yang sama dijumlahkan per **kabupaten/kota**
  (`kdprov` + `kdkab`) per job per `dasar`; dipakai ringkasan provinsi dan tren.
  Index: `(run_id, dasar)`.
- `unggahan`: sesi unggahan berpotongan. Berisi id, nama, jenis
  (`master`/`peta`/`titik`), ukuran, SHA-256, jumlah potongan, potongan yang sudah
  diterima, status selesai, waktu kedaluwarsa, dan `created_at`. Potongan
  sementara disimpan di disk dan dibersihkan setelah disusun atau kedaluwarsa.
- `worker_event`: catatan operasional worker untuk Status Sistem, termasuk
  checkpoint/progres dan pesan. Berisi id, `worker_id`, `run_id`, level/jenis,
  pesan, dan `created_at`; dipangkas berkala.
- `worker_heartbeat`: denyut worker. Berisi `worker_id` (unik), pid, `run_id`,
  `started_at`, `heartbeat_at`, dan status; satu baris per worker yang sedang
  hidup. Baris kedaluwarsa dipakai untuk mendeteksi worker mati tanpa pesan.

Penyimpanan dibatasi agar database tidak membengkak:

- baris `runs`, seluruh snapshot rekap, dan `geotag_master` tidak pernah dihapus;
- `titik_hasil` dan berkas mentah hanya disimpan untuk **baseline** (sukses
  pertama) dan **sukses terakhir** per (`kdprov`, `kdkab`, `tipe`);
- run di antara itu `detail_tersedia` = 0, dan drill-down SLS/SubSLS-nya dibalas
  HTTP 409;
- sesi `unggahan` sementara kedaluwarsa (default 24 jam);
- `worker_event` dipangkas berkala, sedangkan `worker_heartbeat` hanya menyimpan
  denyut terbaru.

Rekap dihitung lewat query GROUP BY di database saat job sukses dan disimpan
sebagai snapshot, bukan dihitung ulang di Python tiap permintaan dashboard. Job
dikerjakan berurutan sesuai urutan unggah, hanya satu job aktif per
(`kdprov`, `kdkab`, `tipe`).

## 8. Non-fungsional

- **Memori**: server backend punya ~2,8 GB tersedia; API dibatasi `MemoryMax=1G`
  dan worker `MemoryMax=1500M` dengan `WORKER_MEM_BUDGET_MB=800`. Worker membaca
  titik per potongan, menyimpan checkpoint, dan berhenti dengan status jelas bila
  anggaran terlampaui. Frontend cPanel tetap dibatasi 1 GB TOTAL (idle ±366 MB,
  mati di atas ±1.110 MB). API harus ringan dan tidak mengimpor library spasial
  saat startup.
- **Unggahan**: body mentah `application/octet-stream`; dilarang
  `FormData`/multipart. Batas body 128 MiB/request; berkas besar lewat potongan
  16 MiB, hash per potongan, retry, dan resume. Pesan 403/413 dari WAF/server
  harus ditampilkan jelas. Ukuran dan batas diambil dari env, bukan hardcode.
- **Hosting backend**: AlmaLinux 8/aaPanel dengan systemd 239, root/SSH, dan
  nginx. API dan worker adalah service terpisah; worker memakai `--loop`,
  `fcntl.flock`, checkpoint, dan heartbeat tiap 15 detik. SIGTERM menyelesaikan
  batch berjalan. Job yang heartbeat-nya kedaluwarsa ditandai gagal agar tidak
  menghalangi antrean. `--once` tetap didukung untuk cron/manual.
- **Hosting frontend**: Node.js App cPanel untuk halaman, callback SSO, dan
  penjagaan sesi. Semua panggilan API memakai `NEXT_PUBLIC_API_BASE` langsung
  dari browser; tidak ada route proxy API/rewrite ke backend.
- **Database**: MariaDB 10.11/InnoDB, `FOR UPDATE SKIP LOCKED` untuk klaim job;
  tanpa PostGIS dan tanpa geometri di DB. Buffer pool 768M dan flush transaksi 2
  untuk HDD; pengguna aplikasi hanya boleh dari loopback dan satu database.
- **Cadangan database**: `deploy/backup.sh` menjalankan `mysqldump` harian ke
  `/home/backup`, kredensial dari `~/.my.cnf` (mode 600), rotasi 14 hari, dan
  harus diuji restore. Berkas master geotag ikut dicadangkan; berkas run mentah
  tidak wajib.
- **Keamanan**: `AUTH_MODE=dev` ditolak saat `ENV=production`; `AUTH_SECRET`
  wajib (minimal 32 karakter) dan tidak punya nilai bawaan. Token Bearer tidak
  disimpan di cookie; frontend memakai memori/`sessionStorage`. Token, cookie,
  dan kata sandi tidak boleh dicetak/disimpan di log, dokumen, atau commit.
  Sertifikat SSL harus valid sebelum SSO production.
- **Operasional**: Status Sistem dan `scripts/pantau_worker.py` dipakai untuk
  mendeteksi worker mati, heartbeat lambat, antrean, dan pemakaian memori/disk.
- **Ketersediaan**: job dapat diulang setelah gagal; unggahan dapat dilanjutkan;
  status job dapat dipantau tanpa membaca log mentah.

## 9. Kriteria selesai (Proses A dan B)

Pada data uji satu kabupaten/kota: jumlah baris, nilai semua flag, dan kolom
wilayah sama dengan output QGIS. Di production, unggahan 151 MB berhasil lewat
potongan 16 MiB, worker menyelesaikan 397 ribu titik dalam anggaran memori, dan
Status Sistem menunjukkan job sukses tanpa proses yang dimatikan server.

## 10. Di luar cakupan (dulu)

Edit titik langsung di web, notifikasi, multi-bahasa, dan perbaikan logika model
(misalnya `flag_position` yang hanya membandingkan latitude) sebelum replikasi
persis lulus uji.

## 11. Pertanyaan terbuka

- **Protokol SSO production**: client id/secret, redirect URI, dan apakah callback
  ditangani API atau frontend. Pemetaan klaim `org` ke peran juga masih perlu
  diuji dengan akun provinsi dan kabupaten/kota nyata. Client uji lokal tidak
  boleh dipakai di production; frontend Node.js perlu alur token Bearer dari
  cookie non-httpOnly tanpa mengirim cookie ke backend.
- **Peta lama untuk Proses B**: kebijakan penyimpanan memangkas berkas mentah
  run lama. Perlu dipastikan peta sumber tetap tersedia (atau disalin saat job B
  dibuat) ketika pengguna memilih run A lama, dan berapa lama peta itu disimpan.
- **SSL**: sertifikat saat ini kedaluwarsa/self-signed. Perlu pemilik dan jadwal
  perpanjangan; SSO production tidak dapat dimulai sebelum SSL valid.
- **Batas `level_6_full_code` kosong**: saat ini diabaikan, tetapi berkas ditolak
  kalau tidak ada satu pun kode yang bisa diverifikasi. Perlu keputusan apakah
  baris kosong boleh masuk rekap "(tanpa wilayah)".
- **Anggaran memori final**: `WORKER_MEM_BUDGET_MB=800` masih perlu divalidasi
  dengan data 397 ribu titik dan ukuran potongan yang dipakai di production.

## 12. Status task T0–T8

- **T0 — Kerangka repo, AGENTS.md, .gitignore**: selesai.
- **T1 — Fungsi Proses A + tes lawan output QGIS**: selesai.
- **T2 — Fungsi Proses B + tes lawan output QGIS**: selesai, termasuk data uji
  dengan titik digeser dan atribut diubah manual.
- **T3 — API FastAPI, skema MariaDB, Alembic, rekap, ekspor**: selesai untuk
  skema inti dan migrasi `0001`–`0008`; ekspor GPKG/CSV dan rekap
  desa/kabupaten tersedia. Tabel operasional `unggahan`, `worker_event`, dan
  `worker_heartbeat` masuk skema acuan dan diselesaikan bersama T8.
- **T4 — Login SSO**: selesai di lokal (OIDC Authorization Code + PKCE, sesi JWT
  httpOnly, otorisasi wilayah); production tertahan SSL dan client SSO.
- **T5 — Kerangka frontend**: selesai (sidebar, layout, halaman proses/rekap/
  ekspor/master). Static export production belum diterapkan.
- **T6 — Halaman upload dan jalankan proses**: selesai (Proses A/B terpisah,
  polling status, pemilihan sumber, master geotag, ekspor per job, unggahan
  berpotongan dengan resume dan hash); click-through production belum.
- **T7 — Dashboard rekap progres dan Status Sistem**: selesai di kode. Halaman
  rekap memakai `/ringkasan` dan `/runs/{id}/rekap` (kabupaten/kecamatan/desa/
  SLS/SubSLS, dasar tugas/posisi, ekspor CSV). Status Sistem menampilkan
  `worker_event`/`worker_heartbeat`, riwayat kejadian, dan status backup dari
  `deploy/backup.sh`. Uji klik-through di server production belum.
- **T8 — Deploy AlmaLinux/aaPanel**: sebagian. Berkas `deploy/` (systemd API dan
  worker, nginx, env contoh, deploy, backup) serta dokumentasi server sudah
  disiapkan. Frontend statis tetap di cPanel. Migrasi database, SSL/domain API,
  SSO production, tabel operasional, uji restore cadangan, dan pengujian penuh
  Status Sistem di server baru belum selesai/diuji.

## 13. Keputusan dan alasannya

- **Backend terpisah di AlmaLinux + frontend statis di cPanel**: backend berat
  (Python/spasial) tidak lagi berbagi batas 1 GB akun cPanel; frontend tetap
  ringan. API dipanggil lintas origin dengan Bearer, jadi tidak butuh cookie atau
  server Next.js.
- **Unggahan `octet-stream` berpotongan 16 MiB**: multipart diblokir WAF (403) dan
  body form di atas ±1 MB ditolak 413; batas body 128 MiB membuat unggahan
  sekali jalan tidak aman.
- **Service `--loop` + `fcntl.flock` + checkpoint/heartbeat**: systemd 239
  tersedia di server baru; flock mencegah service dan `--once` cron berjalan
  bersamaan, checkpoint mengurangi pekerjaan ulang, heartbeat mendeteksi proses
  yang dimatikan, dan SIGTERM berhenti setelah batch.
- **Anggaran worker 800 MB dan impor berat hanya di worker**: API dibatasi 1 GB
  dan worker 1,5 GB di server dengan ~2,8 GB tersedia; impor spasial tidak boleh
  ikut membebani proses API.
- **MariaDB tanpa PostGIS/geometri di DB**: hanya MariaDB yang tersedia; geometri
  diproses dari berkas dengan Python, database menyimpan hasil dan rekap.
- **Detail hanya baseline + terbaru, rekap permanen**: menjaga ukuran database
  sambil mempertahankan riwayat progres dan audit.
- **Bypass mati di production dan tidak ada rahasia di log/dokumen**: melindungi
  akun serta mencegah kebocoran token/cookie/kata sandi.
- **Status Sistem**: proses yang dimatikan server tidak meninggalkan pesan galat,
  jadi status worker, heartbeat, dan progres harus terlihat dari aplikasi.
