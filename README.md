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

`backend/app/proses_b.py` sudah identik dengan keluaran QGIS pada data uji 3307 (semua kolom,
397.364 baris), tetapi data uji itu hanya mewakili kasus **tanpa titik digeser dan tanpa
atribut diedit** (semua `flag_position` dan `flag_edit_atr_repair` bernilai 0). Kasus titik yang
benar-benar digeser/diedit baru diuji lewat tes unit; PRD §9 untuk Proses B dinyatakan lulus
penuh setelah ada data edit asli dari petugas.

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
  sesuai (264 desa, 7.567 SubSLS pada dasar `tugas`, 7.798 pada dasar `posisi`,
  48.364 titik belum diperbaiki).
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

Hasil ukur pada data uji penuh satu kabupaten (397.364 baris, MariaDB):

| Tabel | Sebelum | Sesudah |
|---|---|---|
| `titik_hasil` (data + indeks) | 223,48 MB | 106,73 MB |
| `wilayah` | — | 2,11 MB (7.966 baris) |
| `rekap_subsls` | — | 4,57 MB (15.365 baris) |

Perkiraan per kabupaten/run: ±113 MB (sebelumnya ±223 MB); untuk 35 kabupaten ±4,0 GB
(sebelumnya ±7,8 GB). Snapshot `rekap_subsls` dan baris `runs` **tidak** ikut dihapus saat hasil
lama digantikan job baru — yang dihapus hanya isi `titik_hasil`.
