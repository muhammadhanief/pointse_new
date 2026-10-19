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
- [ ] T2 Fungsi Proses B + tes lawan output QGIS — **belum dianggap selesai**: data uji yang
      ada hanya mewakili kasus "tidak ada titik digeser/diedit". Menunggu berkas peta/titik
      hasil penggeseran dari petugas untuk menguji kasus titik yang benar-benar digeser.
- [x] T3 API FastAPI + skema MySQL + Alembic
- [ ] T4 Login SSO BPS
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

- `alembic upgrade head` jalan dan `alembic check` bersih (skema DB = model ORM).
- Data uji penuh kdkab 3307 (397.443 titik) diunggah lewat `POST /runs` dan diproses worker:
  397.364 baris tersimpan (79 duplikat `assignment_id` dibuang — sama dengan output QGIS),
  `jumlah_tanpa_wilayah` = 82 (titik di luar semua poligon), rekap kabupaten/kecamatan/desa/sls
  sesuai untuk kedua dasar (`tugas` 7.567 baris, `posisi` 7.799 baris termasuk kategori
  "(tanpa wilayah)"), dengan rincian `belum` 48.364 / `benar_awal` 349.000 /
  `ditindak_posisi_benar` 0 / `ditindak_posisi_salah` 0 / `digeser` 0 / `tanpa_wilayah` 82
  (Proses A belum punya kolom `flag_edit_atr_repair`/`flag_position`, jadi persentase
  progresnya 0%).
- Satu job aktif per (kdkab, tipe) terbukti: unggahan baru membuat job lama berstatus
  `digantikan` dan `titik_hasil`-nya dihapus.
- Performa: 397.364 baris tersimpan dalam ±45 detik (±9.000 baris/detik) pada pengukuran ini,
  termasuk waktu tulis ke MariaDB yang jauh dari mesin uji. Untuk produksi, jalankan worker di
  server yang sama dengan MySQL.
- Peta SLS memakai kode wilayah pendek (`kdkab` `07`, `kddesa` `005`), jadi nilai `runs.kdkab`
  dan kolom wilayah mengikuti kode di berkas sumber.

## Catatan normalisasi skema (T3 lanjutan, migrasi `0002`)

Agar DB tidak membengkak saat dipakai semua kabupaten/kota, skema awal dirapikan:

- `wilayah` — dimensi wilayah (satu baris per SubSLS `idsubsls`, 11 kolom kode + nama). Diisi
  dari peta yang diunggah dengan aturan **upsert** (tidak pernah dihapus).
- `titik_hasil` — hanya kolom yang dipakai dashboard: flag, `kk/btt/bku/bttk/bbtt`, `usaha`,
  4 kolom koordinat, `level_6_full_code`, dan wilayah sebagai **id** (`wilayah_asal_id`,
  `wilayah_edit_id`). Kolom atribut bangunan dan nama/kode wilayah dibuang (berkas mentah di
  disk tetap sumber lengkapnya).
- `rekap_subsls` — snapshot rekap per SubSLS per job untuk dua dasar: `tugas`
  (`level_6_full_code`, wilayah penugasan titik) dan `posisi` (hasil join peta). Dashboard
  membaca tabel ini, jadi tidak pernah memindai `titik_hasil`.
- `runs.jumlah_tanpa_wilayah` — jumlah titik yang tidak masuk poligon wilkerstat mana pun.

Migrasi `0003`/`0004` merinci hitungan rekap (PRD §5) menjadi `belum` (`flag_repair` = 1),
`benar_awal` (`flag_repair` = 0 tanpa tindakan manual), `ditindak_posisi_benar` (`flag_repair` = 0,
`flag_edit_atr_repair` = 1, `flag_repair_initial` = 0), `ditindak_posisi_salah` (`flag_repair` = 0,
`flag_edit_atr_repair` = 1, `flag_repair_initial` = 1), `digeser` (`flag_position` = 1), dan
`tanpa_wilayah`; `jumlah` = `belum` + `benar_awal` + `ditindak_posisi_benar` +
`ditindak_posisi_salah`. Persentase progres = (`ditindak_posisi_benar` + `ditindak_posisi_salah`) /
(`belum` + `ditindak_posisi_benar` + `ditindak_posisi_salah`) dan ditampilkan kosong kalau
penyebutnya 0.

Titik yang tidak bisa dipetakan ke wilayah pada dasar rekap dihitung sebagai baris kategori
**"(tanpa wilayah)"**: `rekap_subsls.wilayah_id` NULL untuk dasar `tugas` (kode
`level_6_full_code` kosong atau tidak ada di tabel `wilayah`) maupun dasar `posisi` (titik di
luar semua poligon). Karena kolom kunci utama di MySQL tidak boleh NULL, kunci utama
`rekap_subsls` dipindah ke `id` (`UNIQUE (run_id, dasar, wilayah_id)` tetap menjaga keunikan).
Dengan begitu **jumlah setiap dasar = `runs.jumlah_baris`** dan tidak ada titik yang hilang;
`wilayah` tetap hanya berisi SubSLS yang benar-benar ada di peta (kode asing tidak dibuatkan
baris seadanya).

Hasil ukur pada data uji penuh satu kabupaten (397.364 baris, MariaDB, setelah migrasi `0004`):

| Tabel | Sebelum | Sesudah |
|---|---|---|
| `titik_hasil` (data + indeks) | 223,48 MB | 101,78 MB |
| `wilayah` | — | 2,02 MB (7.966 baris) |
| `rekap_subsls` | — | 2,69 MB (15.366 baris: 7.567 dasar `tugas` + 7.799 dasar `posisi`) |

Perkiraan per kabupaten/run: ±107 MB (sebelumnya ±223 MB); untuk 35 kabupaten ±3,7 GB
(sebelumnya ±7,8 GB). Snapshot `rekap_subsls` dan baris `runs` **tidak** ikut dihapus saat hasil
lama digantikan job baru — yang dihapus hanya isi `titik_hasil`.
