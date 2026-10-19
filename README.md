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
- [x] T2 Fungsi Proses B + tes lawan output QGIS
- [ ] T3 API FastAPI + skema MySQL + Alembic
- [ ] T4 Login SSO BPS
- [ ] T5 Kerangka frontend (sidebar, layout)
- [ ] T6 Halaman upload dan jalankan proses
- [ ] T7 Dashboard rekap progres
- [ ] T8 Deploy ke server BPS (domain `*.bps.go.id`)

## Catatan Proses B (T2)

Keluaran Proses B (`backend/app/proses_b.py`) sudah identik dengan keluaran QGIS
pada data uji 3307 (semua kolom, 397.364 baris), tetapi data uji itu hanya
mewakili kasus **tanpa titik digeser dan tanpa atribut diedit** (semua
`flag_position` dan `flag_edit_atr_repair` bernilai 0). Kasus titik yang benar-benar
digeser/diedit baru diuji lewat tes unit; PRD §9 untuk Proses B dinyatakan lulus
penuh setelah ada data edit asli dari petugas.
