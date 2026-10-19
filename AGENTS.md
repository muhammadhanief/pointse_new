# AGENTS.md

Web app monitoring progres editing batas Wilkerstat BPS. Baca `PRD.md` sebelum
mengerjakan task apa pun, terutama bagian "Proses" untuk logika spasial.

## Struktur
- `backend/`  FastAPI (Python), geopandas, SQLAlchemy + PyMySQL, Alembic
- `pointse_frontend/` Next.js 16 + React 19 + Tailwind 4 (scaffold `create-next-app`;
  sesuai keputusan pemilik proyek nama folder TETAP `pointse_frontend/`, bukan `frontend/`).
  Deploy di server BPS (domain `*.bps.go.id`), bukan Vercel — syarat SSO BPS.
- Acuan tampilan (sidebar dan gaya) = aplikasi lokal SE2026:
  `D:\2026\SID\SPBE\Sistem Informasi\se2026\assignse2026\assignse2026`
  (Next.js, sidebar di `app/(dashboard)/layout.tsx`, halaman contoh di
  `app/(dashboard)/**/page.tsx`, komponen di `components/`). Folder itu punya
  `AGENTS.md` sendiri: baca `node_modules/next/dist/docs/` sebelum menulis kode Next.js.
- `docs/` = data uji + model QGIS asli (bukan kode, JANGAN di-commit; total ~370 MB):
  - `docs/Titik Bangunan dan SLS/3307/Landmark Bangunan/landmark_202523307.gpkg`
    input Proses A/B, layer `geotag`, 397.443 titik, CRS 4326
  - `docs/Titik Bangunan dan SLS/3307/Peta SLS SubSLS/Final_SLS_202513307.geojson`
    peta wilkerstat baru, 7.966 poligon SubSLS, CRS 4326
  - `docs/hasil_identifikasi_titik_model1.gpkg` = OUTPUT QGIS Proses A (pembanding tes T1),
    layer `hasil_identifikasi_titik`, 397.364 baris
  - `docs/hasil_pengecekan_posisi_model2.gpkg` = OUTPUT QGIS Proses B (pembanding tes T2),
    layer `hasil_pengecekan_titik_hasil_penggeseran`, 397.364 baris.
    CATATAN: di file ini semua `flag_position`=0 dan `flag_edit_atr_repair`=0, jadi hanya
    menguji kasus "tidak ada titik digeser".
  - `docs/Model Olah Titik Bangunan dan Peta/.../Model/*.model3` = model QGIS asli
    (format XML, bukan JSON). Ini sumber kebenaran logika Proses A dan B.
  - `docs/Panduan SSO Client.pdf` = panduan SSO BPS (Keycloak 26.7.0,
    https://accounts.bps.go.id, realm `pegawai`/`public`, OIDC Authorization Code + PKCE).
    PENTING: SSO BPS hanya boleh dipakai aplikasi berdomain `*.bps.go.id` (di-hosting di
    layanan BPS) — hosting di luar BPS (mis. Vercel) tidak boleh memakai SSO BPS.

## Perintah (isi/koreksi sesuai kenyataan)
- Backend jalan: `cd backend && uvicorn app.main:app --reload`
- Backend tes: `cd backend && pytest -q`
- Frontend jalan: `cd pointse_frontend && npm run dev`
- Migrasi DB: `cd backend && alembic upgrade head`

## Aturan teknis
- Database hanya MySQL. Jangan pakai PostgreSQL/PostGIS. Jangan simpan geometri di DB.
- Jangan pakai QGIS/PyQGIS. Hitungan spasial pakai geopandas/pyogrio/shapely.
- Replikasi logika model QGIS PERSIS seperti di PRD.md. Jangan "memperbaiki" logikanya
  kecuali diminta.
- Hanya backend yang boleh mengakses MySQL. Frontend selalu lewat API.
- Jangan commit data mentah, file `.env`, atau kredensial.
- Beri type hints di Python. Komentar kode singkat, dalam Bahasa Indonesia.

## Cara kerja
- Kerjakan SATU task per sesi, sesuai daftar di PRD.md bagian 12. Jangan melebar ke task lain.
- Ubah file seperlunya saja. Jangan refactor di luar yang diminta.
- Tambahkan tes untuk logika baru. Jalankan tes sebelum menyatakan selesai.
- Kalau ada hal yang ambigu atau ada di "Pertanyaan terbuka" PRD, tanya dulu, jangan menebak.
- Jawab ringkas dalam Bahasa Indonesia. Tidak perlu penjelasan panjang kecuali diminta.
