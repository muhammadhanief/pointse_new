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
  rekap kabupaten/kecamatan/desa/sls sesuai (265 desa, 7.799 SubSLS, 48.364 titik belum diperbaiki).
- Satu job aktif per (kdkab, tipe) terbukti: unggahan baru membuat job lama berstatus
  `digantikan` dan `titik_hasil`-nya dihapus.
- Performa: penyimpanan ±1.000 baris/detik saat backend jauh dari server DB (latensi jaringan
  per batch 10.000 baris). Untuk produksi, jalankan worker di server yang sama dengan MySQL.
- Peta SLS memakai kode wilayah pendek (`kdkab` `07`, `kddesa` `005`), jadi nilai `runs.kdkab`
  dan kolom wilayah mengikuti kode di berkas sumber.
