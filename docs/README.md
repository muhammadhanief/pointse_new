# docs/ (tidak ikut di-commit)

Folder ini berisi **data mentah dan dokumen internal BPS**. Semuanya diabaikan
`.gitignore` karena ukurannya besar (±370 MB) dan bukan bagian kode.

Isi yang harus ada di lokal (untuk menjalankan tes T1/T2):

| Path | Isi |
|---|---|
| `Titik Bangunan dan SLS/3307/Landmark Bangunan/landmark_202523307.gpkg` | Input titik bangunan, layer `geotag`, 397.443 baris, CRS 4326 |
| `Titik Bangunan dan SLS/3307/Peta SLS SubSLS/Final_SLS_202513307.geojson` | Peta wilkerstat baru, 7.966 poligon SubSLS, CRS 4326 |
| `hasil_identifikasi_titik_model1.gpkg` | Output QGIS Proses A (pembanding tes T1), layer `hasil_identifikasi_titik`, 397.364 baris |
| `hasil_pengecekan_posisi_model2.gpkg` | Output QGIS Proses B (pembanding tes T2), layer `hasil_pengecekan_titik_hasil_penggeseran`, 397.364 baris |
| `Titik Bangunan dan SLS/3307/hasil_edit_runmodel2.gpkg` | Output QGIS Proses B pada data yang **sudah diedit** (pembanding tes T2), layer `hasil_pengecekan_titik_hasil_penggeseran`, 397.364 baris |
| `Model Olah Titik Bangunan dan Peta/.../Model/*.model3` | Model QGIS asli (XML) untuk Proses A dan B — sumber kebenaran logika |
| `Model Olah Titik Bangunan dan Peta/.../Style/*.qml` | Gaya (style) QGIS |
| `Panduan SSO Client.pdf` | Panduan SSO BPS (Keycloak 26.7.0, OIDC Authorization Code + PKCE) |

Catatan:

- `hasil_pengecekan_posisi_model2.gpkg`: seluruh `flag_position` = 0 dan
  `flag_edit_atr_repair` = 0, jadi menguji kasus "tidak ada titik yang digeser/diedit"
  (`tests/test_proses_b_qgis.py`).
- `hasil_edit_runmodel2.gpkg`: 6 titik digeser dan `flag_repair`-nya diubah manual
  (`flag_position` = 1 dan `flag_edit_atr_repair` = 1), jadi menguji kasus ada editan
  (`tests/test_proses_b_edit_qgis.py`). Berkas **masukan** model untuk data ini tidak
  ada di folder; masukannya disusun ulang dari keluaran Proses A oleh
  `tests/qgis_data.py::muat_input_b_edit`.
