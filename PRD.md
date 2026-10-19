# PRD: Monitoring Progres Editing Batas Wilkerstat

## 1. Tujuan
Web app untuk memantau progres perbaikan (editing) titik bangunan terhadap batas
wilkerstat (SLS/SubSLS) BPS, menggantikan pengecekan manual lewat model QGIS.
Semua hitungan spasial dilakukan dengan Python, tanpa QGIS/PyQGIS.

## 2. Pengguna
Petugas dan pengawas BPS. Login memakai SSO BPS.

## 3. Arsitektur
- **Frontend**: Next.js, di-host di Vercel. Tampilan (sidebar dan gaya) mengikuti
  aplikasi lokal yang sudah ada (acuan: `docs/ui-reference/`).
- **Backend**: FastAPI (Python) di server sendiri. Hanya backend yang mengakses database.
- **Database**: MySQL (PostgreSQL/PostGIS tidak tersedia). Menyimpan HASIL hitungan
  (tabel biasa), bukan geometri.
- **File mentah** (GeoJSON/GPKG) disimpan di disk server, bukan di database.
- Library inti: geopandas, pyogrio, shapely, SQLAlchemy + PyMySQL, Alembic.
- Frontend memanggil API backend lewat HTTPS. Port MySQL tidak dibuka ke internet.
  CORS dibatasi ke domain frontend.

## 4. Input
1. **Peta batas wilkerstat lapangan** (poligon, GeoJSON). Kolom wajib: kdprov, kdkab,
   kdkec, kddesa, nmprov, nmkab, nmkec, nmdesa, idsls, nmsls, idsubsls.
2. **Titik bangunan** (GPKG, layer `geotag`). Kolom yang dipakai: assignment_id,
   unique_bang, flag_psls, level_6_full_code, geotag_latitude, geotag_longitude,
   no_bang, kode_bang_value, ada_keluarga_value, ada_bang_usaha_value, count_usaha,
   nama_usaha_bang.
3. Untuk Proses B: **titik hasil pengolahan** (output Proses A yang sudah diedit/digeser)
   dan **peta wilkerstat lama lapangan**.

## 5. Proses
Prinsip: **replikasi persis dulu** perilaku model QGIS, perbaikan belakangan.
Hasil harus identik dengan output QGIS pada data uji.

### Proses A: Identifikasi Titik (model `01_Identifikasi_Titik`)
1. Reproject peta dan titik ke EPSG:4326.
2. Spatial join titik ke poligon (titik masuk/menyentuh poligon). Di QGIS predikatnya
   intersects + within, dan hanya poligon cocok PERTAMA yang diambil. Titik yang tidak
   cocok tetap dipertahankan (kolom wilayah kosong).
   - GeoPandas: `sjoin(how="left", predicate="intersects")`, lalu ambil baris pertama
     per titik (titik di garis batas bisa cocok ke >1 poligon).
3. Gabungkan hasil cocok dan tidak cocok, buang duplikat berdasarkan `assignment_id`.
4. Bentuk kolom hasil:
   - `idsubsls_origin` = idsubsls hasil join
   - `latitude_origin` = geotag_latitude, `longitude_origin` = geotag_longitude
   - `flag_repair_initial` = `flag_repair` = 0 jika idsubsls == level_6_full_code, selain itu 1
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
1. Input: titik hasil pengolahan (output A, sudah diedit) dan peta wilkerstat lama lapangan.
2. Hitung `latitude_edited`, `longitude_edited` dari geometri titik saat ini.
3. `flag_edit_atr_repair` = 1 jika `flag_repair` != `flag_repair_initial`, else 0
   (artinya atribut flag_repair diubah manual).
4. Spatial join ulang ke peta (aturan sama seperti A: ambil poligon pertama, pertahankan
   titik tak cocok), buang duplikat `assignment_id`.
5. Hitung ulang:
   - `idsubsls_edited` = idsubsls hasil join baru
   - `flag_position` = 0 jika `latitude_origin` == `latitude_edited`, else 1
     (model asli hanya membandingkan latitude)
   - `flag_repair_initial` = 0 jika level_6_full_code == idsubsls (hasil join baru), else 1
   - `flag_repair` akhir = 0 jika (flag_repair == 1 dan flag_repair_initial == 0);
     selain itu 1 jika (flag_repair_initial == 1 dan flag_edit_atr_repair == 0);
     selain itu tetap nilai flag_repair
6. Output: **Hasil Pengecekan Titik Hasil Penggeseran**.

### Indikator progres
Jumlah titik dipisah menjadi:

- `belum`: `flag_repair` = 1;
- `benar_awal`: `flag_repair` = 0 dan `flag_edit_atr_repair` bukan 1 (pada Proses A kolom
  itu kosong, NULL dianggap 0) — titik sudah benar tanpa tindakan manual;
- `ditindak_posisi_benar`: `flag_repair` = 0, `flag_edit_atr_repair` = 1, dan
  `flag_repair_initial` = 0 (atribut ditindak manual dan posisinya sudah di SubSLS tugas);
- `ditindak_posisi_salah`: `flag_repair` = 0, `flag_edit_atr_repair` = 1, dan
  `flag_repair_initial` = 1 (ditindak manual tetapi posisinya masih belum sesuai);
- `digeser`: `flag_position` = 1 (titik dipindah; keterangan tersendiri, bisa tumpang
  tindih dengan kolom lain);
- `tanpa_wilayah`: titik yang tidak masuk poligon wilkerstat mana pun (keterangan
  tersendiri, bisa tumpang tindih dengan `belum`).

Persentase progres = (`ditindak_posisi_benar` + `ditindak_posisi_salah`) / (`belum` +
`ditindak_posisi_benar` + `ditindak_posisi_salah`); `benar_awal` dan `digeser` tidak ikut
dihitung. Kalau penyebutnya 0, persentasenya ditampilkan kosong (bukan 0%).

Titik yang tidak bisa dipetakan ke wilayah pada dasar rekap yang dipakai dihitung sebagai
kategori terpisah "(tanpa wilayah)", jadi jumlah tiap dasar selalu utuh (`jumlah` =
`belum` + `benar_awal` + `ditindak_posisi_benar` + `ditindak_posisi_salah`). Semua
direkap per kabupaten/kota, kecamatan, desa, dan SLS/SubSLS.

## 6. Fitur (urut prioritas)
1. Login SSO BPS
2. Upload input dan jalankan Proses A
3. Jalankan Proses B pada titik yang sudah diedit
4. Dashboard rekap progres per wilayah (tabel + filter)
5. Ekspor hasil (CSV/GPKG)
6. Peta visualisasi titik (opsional, terakhir)

## 7. Model data MySQL (skema terpasang)
Empat tabel (lihat `backend/migrations/`); geometri/peta mentah tidak pernah masuk DB,
hanya berkas di disk server.

- `runs`: satu baris per job — id, tipe (A/B), kdkab, user, status (`menunggu`,
  `jalan`, `sukses`, `gagal`, `digantikan`), nama + path berkas input/peta, layer yang
  dipakai, `jumlah_baris`, `jumlah_tanpa_wilayah`, pesan galat, created/started/finished_at.
  Index: `kdkab`, `status`, `tipe`.
- `wilayah`: dimensi wilayah, satu baris per SubSLS — id, `idsubsls` (unik), `idsls`,
  `nmsls`, `kdprov`..`nmdesa`. Diisi dari peta lewat upsert (nama disegarkan, tidak
  pernah dihapus); kode di luar peta **tidak** dibuatkan baris seadanya. Index: `kdkab`.
- `titik_hasil`: hasil per titik (ramping) — kunci `(run_id, urut)`, unik
  `(run_id, assignment_id)`; `assignment_id`, `level_6_full_code`,
  `wilayah_asal_id`/`wilayah_edit_id` (FK ke `wilayah`, boleh NULL),
  flag (`flag_psls`, `flag_position`, `flag_edit_atr_repair`, `flag_repair_initial`,
  `flag_repair`), `kk`/`btt`/`bku`/`bttk`/`bbtt`, `usaha`, dan koordinat
  origin/edited. Nama & kode wilayah tidak disimpan di sini (lewat `wilayah`).
- `rekap_subsls`: snapshot rekap per SubSLS per job — kunci utama `id`, unik
  `(run_id, dasar, wilayah_id)`; kolom `jumlah`, `belum`, `benar_awal`,
  `ditindak_posisi_benar`, `ditindak_posisi_salah`, `digeser`, `tanpa_wilayah`, dan
  `dasar` (`tugas` = `level_6_full_code` titik, `posisi` = hasil join peta:
  `wilayah_edit_id` bila ada, kalau tidak `wilayah_asal_id`). Index: `(run_id, dasar)`.
  - `wilayah_id` NULL = kategori "(tanpa wilayah)": titik yang tidak bisa dipetakan ke
    wilayah pada dasar itu (dasar `tugas`: `level_6_full_code` kosong atau tidak ada di
    tabel `wilayah`; dasar `posisi`: titik di luar semua poligon). Karena kolom kunci
    utama di MySQL tidak boleh NULL, kunci utama tabel ini memakai `id`.
  - `jumlah` = `belum` + `benar_awal` + `ditindak_posisi_benar` + `ditindak_posisi_salah`;
    `digeser` dan `tanpa_wilayah` adalah keterangan tersendiri (bisa tumpang tindih
    dengan kolom lain).
  - Persentase progres tidak disimpan: dihitung saat dibaca sebagai
    (`ditindak_posisi_benar` + `ditindak_posisi_salah`) / (`belum` +
    `ditindak_posisi_benar` + `ditindak_posisi_salah`), kosong kalau penyebutnya 0.
  - Jumlah baris tiap dasar = `runs.jumlah_baris` (tidak ada titik yang hilang).

Rekap dihitung lewat query GROUP BY di basis data saat job sukses dan disimpan sebagai
snapshot, bukan dihitung ulang di Python tiap permintaan dashboard.

## 8. Non-fungsional
- Proses berat jalan sebagai background task dengan status yang bisa dipantau.
- Pemrosesan per kabupaten/kota (kalau perlu per kecamatan) agar hemat RAM.
- Tidak ada data dan secret di repo (`.env`, data mentah di-ignore).

## 9. Kriteria selesai (Proses A dan B)
Pada data uji satu kabupaten/kota: jumlah baris, nilai semua flag, dan kolom wilayah
sama dengan output QGIS.

## 10. Di luar cakupan (dulu)
Edit titik langsung di web, notifikasi, multi-bahasa, perbaikan logika model
(misalnya flag_position yang hanya membandingkan latitude) sebelum replikasi persis lulus uji.

## 11. Pertanyaan terbuka
- Protokol SSO BPS (OIDC/Keycloak?), siapa yang mengurus client id dan redirect URI?
- Peta mana yang dipakai di A dan B (di B namanya "peta wilkerstat lama lapangan")?
- Input diupload manual atau diambil dari folder/server?
- Siapa yang mengedit titik (di QGIS atau nanti di web) dan bagaimana hasil editnya masuk?

## 12. Rencana task (kerjakan satu per satu, commit tiap selesai)
- T0: Kerangka repo (`backend/`, `frontend/`, `docs/`), AGENTS.md, .gitignore — selesai
- T1: Fungsi Proses A di Python + tes lawan output QGIS — selesai
- T2: Fungsi Proses B + tes lawan output QGIS — selesai (data uji dengan titik digeser
  dan atribut diubah manual: `docs/Titik Bangunan dan SLS/3307/hasil_edit_runmodel2.gpkg`)
- T3: API FastAPI (upload, jalankan, status, hasil) + skema MySQL + Alembic — selesai
- T4: Login SSO
- T5: Kerangka frontend (sidebar, layout) dengan data tiruan
- T6: Halaman upload dan jalankan proses
- T7: Dashboard rekap progres
- T8: Deploy (Vercel + server sendiri)
