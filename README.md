# pointse_new

Web app monitoring progres editing batas Wilkerstat BPS. Menggantikan pengecekan manual
lewat model QGIS dengan hitungan spasial di Python (geopandas/pyogrio/shapely).

Baca **[`PRD.md`](PRD.md)** sebelum mengerjakan apa pun (terutama bagian "Proses"),
lalu **[`AGENTS.md`](AGENTS.md)** untuk aturan kerja.

## Struktur

| Folder | Isi |
|---|---|
| `backend/` | FastAPI + geopandas + SQLAlchemy/PyMySQL + Alembic. Hanya backend yang mengakses MySQL |
| `frontend/` | Next.js 16 + React 19 + Tailwind 4 (tampilan mengikuti aplikasi SE2026) |
| `docs/` | Data uji + model QGIS asli + PDF SSO. **Tidak di-commit** (lihat `docs/README.md`) |

## Mulai cepat

```powershell
# backend
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.venv\Scripts\python.exe -m pytest -q

# frontend
cd ..\frontend
npm install
npm run dev
```

## Status task (PRD §12)

- [x] T0 Kerangka repo
- [x] T1 Fungsi Proses A + tes lawan output QGIS
- [x] T2 Fungsi Proses B + tes lawan output QGIS (kasus tanpa editan dan kasus 6 titik
      digeser/atribut diubah; lihat `backend/tests/test_proses_b_qgis.py` dan
      `test_proses_b_edit_qgis.py`)
- [x] T3 API FastAPI + skema MySQL + Alembic (termasuk revisi garis waktu, penyimpanan, dan
      rekap: migrasi `0005`)
- [x] T4 Login SSO BPS (OIDC Authorization Code + PKCE, sesi JWT httpOnly, otorisasi per
      wilayah). Login lokal sudah dicoba; pemetaan `org` masih asumsi dan perlu diuji dengan
      beberapa akun nyata.
- [ ] T5 Kerangka frontend (sidebar, layout)
- [ ] T6 Halaman upload dan jalankan proses
- [ ] T7 Dashboard rekap progres
- [ ] T8 Deploy ke server BPS (domain `*.bps.go.id`)

## Catatan Proses B (T2)

`backend/app/proses_b.py` sudah identik dengan keluaran QGIS pada data uji 3307 untuk **dua
kasus**, semuanya dibandingkan penuh (semua kolom, 397.364 baris, 0 beda):

- kasus tanpa editan (`docs/hasil_pengecekan_posisi_model2.gpkg`; semua `flag_position` dan
  `flag_edit_atr_repair` = 0) — tes `tests/test_proses_b_qgis.py`;
- kasus **ada editan** (`docs/Titik Bangunan dan SLS/3307/hasil_edit_runmodel2.gpkg`; 6 titik
  digeser dan `flag_repair`-nya diubah manual) — tes `tests/test_proses_b_edit_qgis.py`.

Berkas masukan model untuk kasus kedua tidak ikut di `docs/` (hanya keluarannya), jadi
masukannya disusun ulang dari keluaran Proses A oleh `qgis_data.muat_input_b_edit` (geser
geometri titik yang `flag_position` = 1 dan ubah `flag_repair` titik yang
`flag_edit_atr_repair` = 1 menjadi 0). Dengan dua tes ini PRD §9 untuk Proses B terpenuhi.

## Catatan T3

Tes backend tidak memerlukan server MySQL: tabel dibuat dari model ORM di SQLite sementara,
dan kueri yang khusus MySQL (`FOR UPDATE SKIP LOCKED`, DDL migrasi) diuji lewat kompilasi ke
dialek MySQL. Jalankan migrasi sungguhan dengan `alembic upgrade head` setelah `.env` diisi.

T3 juga sudah diuji **end-to-end lawan MariaDB asli** (`pointse_new`; kredensial hanya ada di
`backend/.env`, tidak di-commit):

- `alembic upgrade head` jalan (termasuk migrasi `0005`, lihat bagian berikutnya) dan
  `alembic check` bersih (skema DB = model ORM).
- Data uji penuh kdkab 3307 (397.443 titik) diunggah lewat `POST /runs` dan diproses worker:
  397.364 baris tersimpan (79 duplikat `assignment_id` dibuang — sama dengan output QGIS),
  `jumlah_tanpa_wilayah` = 82 (titik di luar semua poligon), rekap kabupaten/kecamatan/desa
  sesuai untuk kedua dasar (`tugas` dan `posisi`), dengan rincian `belum` 48.364 /
  `benar_awal` 349.000 / `ditindak_posisi_benar` 0 / `ditindak_posisi_salah` 0 / `digeser` 0 /
  `tanpa_wilayah` 82 (Proses A belum punya kolom `flag_edit_atr_repair`/`flag_position`, jadi
  persentase progresnya 0%).
- Unggahan baru **tidak** menghapus/membatalkan job lama: job antre dikerjakan berurutan
  (yang paling lama dulu) dan aturan satu job aktif per (kdprov, kdkab, tipe) tetap dijaga.
- Performa: 397.364 baris tersimpan dalam ±45 detik (±9.000 baris/detik) pada pengukuran ini,
  termasuk waktu tulis ke MariaDB yang jauh dari mesin uji. Untuk produksi, jalankan worker di
  server yang sama dengan MySQL.
- Peta SLS memakai kode wilayah pendek (`kdprov` `33`, `kdkab` `07`, `kdkec` `010`,
  `kddesa` `001`), jadi nilai `runs.kdkab` dan kolom wilayah mengikuti kode di berkas sumber.
  Akibatnya kode desa bisa berulang antar kecamatan: rekap tingkat desa dikelompokkan per
  (`kdkec`, `kddesa`) dan kolom `kode` yang dibalas berisi `kddesa` saja (nama desanya ikut
  dibalas supaya bisa dibedakan di tampilan).

### Ekspor (fitur 5)

Alur kerja: unduh **GPKG keluaran Proses A** → edit titik di QGIS → unggah hasil edit sebagai
masukan Proses B.

- `GET /runs/{id}/ekspor/hasil-a.gpkg` — dihitung ulang dari berkas mentah run dengan
  `proses_a` (bukan dari `titik_hasil` yang sudah dirampingkan), jadi layer, kolom, urutan,
  dan nilainya sama dengan model QGIS. Pada data uji 3307: **397.364 baris, ±124 MB, ±25 detik**
  untuk unduhan pertama; hasilnya di-cache di `DIR_UNGGAHAN/_ekspor/` (2 berkas terbaru) sehingga
  unduhan berikutnya **±0,1 detik**. Hanya untuk run tipe A yang sukses dan berkas mentahnya
  masih ada (baseline/sukses terakhir); selain itu HTTP 409.
- `GET /runs/{id}/ekspor/titik.csv` dan `.gpkg` — titik perlu tindakan (data uji: 48.364 baris)
  lengkap dengan kode wilayah tugas/asal/edit serta koordinat origin/edited; geometri GPKG
  memakai koordinat edited kalau ada, kalau tidak origin.
- `GET /ekspor/rekap.csv?tingkat=kabupaten|desa&...` — snapshot rekap per run per wilayah dengan
  saringan tipe, provinsi, kabupaten, dasar, dan rentang `tanggal_data`.
- Tes pulang-pergi ada di `backend/tests/test_ekspor.py`: GPKG hasil ekspor A diunggah sebagai
  masukan B tanpa edit, lalu rekap B harus sama dengan rekap A.
- Semua endpoint ekspor sudah memanggil `layanan.periksa_akses(kdprov, kdkab)` sebagai titik
  pemasangan otorisasi per wilayah untuk T4 (sekarang belum menolak apa pun).

## Catatan T4 (SSO BPS)

- Login memakai OIDC Authorization Code + PKCE di frontend Next.js; callback persis di
  `/callback`. Sesi disimpan sebagai JWT HS256 di cookie httpOnly, lalu
  diteruskan ke backend sebagai Bearer. Backend memverifikasi token dan membatasi
  wilayah sesuai peran (`3300`/`33000` admin provinsi, `3307`/`33070` petugas
  kabupaten/kota).
- Client OIDC yang dipakai adalah `PointSE` (`33000-pointse-v5h`) dengan redirect
  `http://localhost:3000/callback` dan `https://pointse.web.bps.go.id/callback`.
  Client Alih Audio lama tidak dipakai lagi.
- Client uji tidak mengirim atribut `org` di UserInfo/ID token. Frontend memakai REST API
  Data Pegawai BPS (service account/Client Credentials) untuk mengambil
  `attributes.org`, `provinceCode`, dan `cityCode`. Pada akun uji, `org` bernilai `92000`
  tetapi `provinceCode` `33`/`cityCode` `00`; karena itu kode wilayah dipilih dari
  `provinceCode`+`cityCode` bila awalan provinsi `org` tidak cocok. Hasilnya provinsi
  `33` (bukan `92`).
- Cloudflare di `accounts.bps.go.id` memblokir fingerprint TLS Node/undici (HTTP 403
  "Just a moment"). Panggilan discovery/token/JWKS/UserInfo/API Pegawai dari server
  Next.js karena itu memakai binary `curl` (tersedia di Windows/Linux); bila tidak ada,
  kode jatuh ke `fetch` bawaan.
- Database pengembangan sekarang memakai **MySQL 8.0.30 Laragon** di
  `127.0.0.1:3306` (root tanpa password), database `pointse`; migrasi `0005` diperbaiki
  agar `DEFAULT (CURRENT_DATE)` kompatibel dengan MySQL 8. MariaDB jauh yang dipakai
  sebelumnya tidak lagi dapat dihubungi.

## Catatan skema (T3 lanjutan, migrasi `0002`—`0005`)

Agar DB tidak membengkak saat dipakai semua kabupaten/kota, skema dirapikan bertahap:

- `wilayah` — dimensi wilayah (satu baris per SubSLS `idsubsls`, kode + nama). Diisi dari peta
  yang diunggah dengan aturan **upsert** (tidak pernah dihapus).
- `titik_hasil` — hanya kolom yang dipakai dashboard: flag, `kk/btt/bku/bttk/bbtt`, `usaha`,
  4 kolom koordinat, `level_6_full_code`, dan wilayah sebagai **id** (`wilayah_asal_id`,
  `wilayah_edit_id`). Kolom atribut bangunan dan nama/kode wilayah dibuang (berkas mentah di
  disk tetap sumber lengkapnya). Sejak `0005`, yang disimpan **hanya titik yang perlu
  perhatian** (`flag_repair` = 1, `flag_edit_atr_repair` = 1, atau tidak masuk poligon mana
  pun); titik `benar_awal` hanya terhitung di rekap.
- `rekap_desa` — snapshot rekap per **desa** (`kdprov`+`kdkab`+`kdkec`+`kddesa`) per job per
  dasar, plus baris "(tanpa wilayah)" bila ada titik yang tak terpetakan pada dasar itu.
  Dashboard, drill-down kecamatan/desa, perubahan antar run, dan ekspor membaca tabel ini.
- `rekap_kabupaten` — rekap yang sama dijumlahkan per **kabupaten/kota**
  (`kdprov`+`kdkab`) per job per dasar; dipakai ringkasan provinsi dan tren.
- `runs.kdprov` + `runs.tanggal_data` + `runs.detail_tersedia` — kunci kabupaten/kota di seluruh
  API/query adalah (`kdprov`, `kdkab`); `tanggal_data` (tanggal data, default tanggal unggah,
  boleh diisi saat `POST /runs`) dipisah dari `created_at` (waktu unggah, UTC) sebagai sumbu
  tren/ringkasan; `detail_tersedia` menandai run yang baris `titik_hasil`-nya masih disimpan
  (run **baseline** dan **sukses terakhir** per kabupaten/tipe).
- `runs.jumlah_tanpa_wilayah` — jumlah titik yang tidak masuk poligon wilkerstat mana pun.

Hitungan rekap (PRD §5) sama di kedua tabel rekap: `belum` (`flag_repair` = 1), `benar_awal`
(`flag_repair` = 0 tanpa tindakan manual), `ditindak_posisi_benar` (`flag_repair` = 0,
`flag_edit_atr_repair` = 1, `flag_repair_initial` = 0), `ditindak_posisi_salah` (`flag_repair` = 0,
`flag_edit_atr_repair` = 1, `flag_repair_initial` = 1), `digeser` (`flag_position` = 1), dan
`tanpa_wilayah`; `jumlah` = `belum` + `benar_awal` + `ditindak_posisi_benar` +
`ditindak_posisi_salah`. Persentase progres = (`ditindak_posisi_benar` + `ditindak_posisi_salah`) /
(`belum` + `ditindak_posisi_benar` + `ditindak_posisi_salah`) dan ditampilkan kosong kalau
penyebutnya 0. Semua angka dihitung di basis data dengan satu query GROUP BY
(`app/rekap.py`, dipakai worker **dan** migrasi `0005` supaya tidak ada dua versi logika),
disimpan sebagai snapshot, dan tidak pernah dihitung ulang saat dashboard dibuka.

Titik yang tidak bisa dipetakan ke wilayah pada dasar rekap dihitung sebagai baris kategori
**"(tanpa wilayah)"** (kode desa NULL) untuk dasar `tugas` (kode `level_6_full_code` kosong atau
tidak ada di tabel `wilayah`) maupun dasar `posisi` (titik di luar semua poligon). Karena kolom
kunci utama di MySQL tidak boleh NULL, `rekap_desa` memakai kunci utama `id` (dengan
`UNIQUE (run_id, dasar, kdprov, kdkab, kdkec, kddesa)`). Dengan begitu **jumlah setiap dasar =
`runs.jumlah_baris`** dan tidak ada titik yang hilang; `wilayah` tetap hanya berisi SubSLS yang
benar-benar ada di peta (kode asing tidak dibuatkan baris seadanya).

### Yang disimpan lama (dan yang dipangkas)

- Baris `runs` dan seluruh snapshot rekap **tidak pernah dihapus** (riwayat tren tetap utuh).
- `titik_hasil` dan berkas mentah di `DIR_UNGGAHAN` hanya disimpan untuk **baseline** (sukses
  pertama) dan **sukses terakhir** per (`kdprov`, `kdkab`, `tipe`); run di antaranya hanya
  menyisakan baris `runs` + rekapnya (`detail_tersedia` = 0). Drill-down SLS/SubSLS run yang
  detailnya sudah dipangkas dibalas HTTP 409.
- Pemangkasan dijalankan di akhir job sukses dalam satu transaksi bersama rekap dan status.

### Hasil ukur pada data uji penuh satu kabupaten (397.364 baris, MariaDB 10.11)

| Tabel | Migrasi `0004` | Setelah `0005` (data + indeks) |
|---|---|---|
| `titik_hasil` | 101,78 MB (397.364 baris) | 96,86 MB — 48.364 baris (hanya perlu perhatian) |
| `wilayah` | 2,02 MB (7.966 baris) | 2,02 MB |
| `rekap_subsls` | 2,69 MB (15.366 baris) | — (tabel dihapus) |
| `rekap_desa` | — | 0,14 MB (531 baris: 265 desa pada dasar `tugas`, dan 265 desa + baris "(tanpa wilayah)" pada dasar `posisi`) |
| `rekap_kabupaten` | — | 0,04 MB (2 baris) |
| `runs` | 0,07 MB | 0,08 MB |

Catatan operasional MySQL/MariaDB (penting untuk produksi):

- `DELETE` (pemangkasan `titik_hasil`) **tidak** mengecilkan tablespace di disk: ukuran
  `titik_hasil` di `information_schema` nyaris tidak turun (46,59 MB → 46,14 MB data) walau
  349.000 baris dibuang. Ruangnya hanya dipakai ulang oleh baris baru; jalankan
  `OPTIMIZE TABLE titik_hasil` (mengunci tabel sementara) kalau ruangnya benar-benar perlu
  dikembalikan, mis. setelah migrasi besar atau sebelum pindah server.
  `information_schema.tables.data_free` bisa dipantau sebagai indikasi ruang bebas di dalam file.
- Server uji ini `log_bin = 0` (binlog mati). Kalau di server produksi binlog menyala, `DELETE`
  besar ikut menulis binlog (berpotensi cepat memenuhi disk) — atur `expire_logs_days` /
  `binlog_expire_logs_seconds` (di sini 10 hari / 864.000 detik) dan pantau ukuran binlog;
  pemangkasan bisa juga dijalankan bertahap per run kalau terlalu besar.
- Perkiraan kapasitas: tabel `titik_hasil` di DB yang sudah pernah menampung run penuh lalu
  memangkasnya masih memakan ±97 MB karena ruang tidak dilepas. Untuk DB baru, 48.364 baris
  (perhatian saja) kira-kira ±12 MB per run; dengan 35 kabupaten/kota × 2 run (baseline +
  terakhir) perkirakan ±0,9 GB `titik_hasil`. Ringkasan dan tren hanya membaca tabel rekap
  (±0,2 MB per run), jadi murah dibaca.
