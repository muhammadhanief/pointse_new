"""Tes modul Rekonsiliasi Batas Antar-Kabupaten/Kota (Gap & Overlap run V)."""

from __future__ import annotations

import json
from datetime import date

import shapely
from sqlalchemy import select

from app import layanan, pengaturan, rekonsiliasi_batas
from app.config import Settings
from app.models import (
    KUNCI_LUAS_MIN_BATAS,
    STATUS_SUKSES,
    TIPE_V,
    RekonsiliasiBatasPasang,
    Run,
)


def test_kamus_74_pasangan_tetangga_jawa_tengah() -> None:
    """Kamus pasangan tetangga Jawa Tengah berisi 74 pasangan kanonik unik."""
    assert len(rekonsiliasi_batas.PASANGAN_TETANGGA_33) == 74
    for a, b in rekonsiliasi_batas.PASANGAN_TETANGGA_33:
        assert a < b
        assert len(a) == 4 and a.startswith("33")
        assert len(b) == 4 and b.startswith("33")
    # Pastikan simetri kamus TETANGGA_KAB_33
    for a, daftar in rekonsiliasi_batas.TETANGGA_KAB_33.items():
        for b in daftar:
            assert a in rekonsiliasi_batas.TETANGGA_KAB_33[b]


def test_periksa_batas_dua_geometri_clean() -> None:
    """Dua poligon kabupaten bersebelahan rapat tanpa celah maupun tumpang tindih."""
    poly_a = shapely.box(109.000, -7.500, 109.010, -7.490)
    poly_b = shapely.box(109.010, -7.500, 109.020, -7.490)
    hasil = rekonsiliasi_batas.periksa_batas_dua_geometri(
        "3301",
        "3302",
        [poly_a],
        [{"idsls": "33010100010001", "idsubsls": "3301010001000100", "nmsls": "RT 01"}],
        [poly_b],
        [{"idsls": "33020100010001", "idsubsls": "3302010001000100", "nmsls": "RT 02"}],
    )
    assert hasil.bersih is True
    assert hasil.jumlah_overlap == 0
    assert hasil.jumlah_gap == 0
    assert hasil.temuan == []


def test_periksa_batas_dua_geometri_overlap_dan_gap() -> None:
    """Deteksi tumpang tindih (overlap) dan celah kosong terjepit (gap) antar kabupaten."""
    # Poligon A1 dan A2 di sisi barat (x = 109.000 .. 109.010)
    a1 = shapely.box(109.000, -7.500, 109.010, -7.495)
    # A2 menjorok ke timur sejauh 0.0002 derajat di bagian utara -> overlap dengan B2
    a2 = shapely.box(109.000, -7.495, 109.0102, -7.490)

    # Poligon B1 punya lekukan celah kecil di tengah perbatasan (y = -7.498 .. -7.496)
    # sehingga antara A1 dan B1 terbentuk celah tertutup (x = 109.010 .. 109.0102, y = -7.498 .. -7.496)
    celah_buatan = shapely.box(109.010, -7.498, 109.0102, -7.496)
    b1_utuh = shapely.box(109.010, -7.500, 109.020, -7.495)
    b1 = shapely.difference(b1_utuh, celah_buatan)
    b2 = shapely.box(109.010, -7.495, 109.020, -7.490)

    atr_a = [
        {"idsls": "33010100010001", "idsubsls": "3301010001000100", "nmsls": "RT 01 CILACAP"},
        {"idsls": "33010100010002", "idsubsls": "3301010001000200", "nmsls": "RT 02 CILACAP"},
    ]
    atr_b = [
        {"idsls": "33020100010001", "idsubsls": "3302010001000100", "nmsls": "RT 01 BANYUMAS"},
        {"idsls": "33020100010002", "idsubsls": "3302010001000200", "nmsls": "RT 02 BANYUMAS"},
    ]

    hasil = rekonsiliasi_batas.periksa_batas_dua_geometri(
        "3301", "3302", [a1, a2], atr_a, [b1, b2], atr_b
    )
    assert hasil.bersih is False
    assert hasil.jumlah_overlap == 1
    assert hasil.jumlah_gap == 1
    assert hasil.total_luas_overlap_m2 > 100.0
    assert hasil.total_luas_gap_m2 > 100.0

    temuan_ov = [t for t in hasil.temuan if t.jenis == "overlap"]
    temuan_gp = [t for t in hasil.temuan if t.jenis == "gap"]
    assert len(temuan_ov) == 1
    assert temuan_ov[0].idsubsls_a == "3301010001000200"
    assert temuan_ov[0].idsubsls_b == "3302010001000200"

    assert len(temuan_gp) == 1
    assert temuan_gp[0].idsubsls_a == "3301010001000100"
    assert temuan_gp[0].idsubsls_b == "3302010001000100"


def test_perbarui_batas_dan_layanan_ringkasan_detail(tmp_path, sesi) -> None:
    """Alur penuh: simpan GeoJSON dua kab tetangga -> perbarui_batas_untuk_run_v -> ringkasan & detail."""
    setelan = Settings(
        dir_unggahan=str(tmp_path / "unggahan"),
        dir_master=str(tmp_path / "master"),
        dir_master_sls_2026_s1=str(tmp_path / "master-v"),
    )

    def _tulis_geojson(jalur, fitur_list):
        jalur.parent.mkdir(parents=True, exist_ok=True)
        jalur.write_text(
            json.dumps({"type": "FeatureCollection", "features": fitur_list}),
            encoding="utf-8",
        )

    berkas_3301 = tmp_path / "peta_3301.geojson"
    berkas_3302 = tmp_path / "peta_3302.geojson"

    # Buat poligon 3301 dan 3302 yang overlap sedikit
    _tulis_geojson(
        berkas_3301,
        [
            {
                "type": "Feature",
                "properties": {
                    "idsls": "33010100010001",
                    "idsubsls": "3301010001000100",
                    "nmsls": "RT 001 RW 001",
                },
                "geometry": json.loads(
                    shapely.to_geojson(shapely.box(109.000, -7.500, 109.0102, -7.490))
                ),
            }
        ],
    )
    _tulis_geojson(
        berkas_3302,
        [
            {
                "type": "Feature",
                "properties": {
                    "idsls": "33020100010001",
                    "idsubsls": "3302010001000100",
                    "nmsls": "RT 005 RW 002",
                },
                "geometry": json.loads(
                    shapely.to_geojson(shapely.box(109.010, -7.500, 109.020, -7.490))
                ),
            }
        ],
    )

    run_1 = Run(
        tipe=TIPE_V,
        kdprov="33",
        kdkab="3301",
        status=STATUS_SUKSES,
        tanggal_data=date(2026, 11, 10),
        user="Petugas Cilacap",
        nama_file_input="peta_3301.geojson",
        nama_file_peta="peta_3301.geojson",
        berkas_input=str(berkas_3301),
        berkas_peta=str(berkas_3301),
        semester="2026_1",
    )
    run_2 = Run(
        tipe=TIPE_V,
        kdprov="33",
        kdkab="3302",
        status=STATUS_SUKSES,
        tanggal_data=date(2026, 11, 11),
        user="Petugas Banyumas",
        nama_file_input="peta_3302.geojson",
        nama_file_peta="peta_3302.geojson",
        berkas_input=str(berkas_3302),
        berkas_peta=str(berkas_3302),
        semester="2026_1",
    )
    sesi.add_all([run_1, run_2])
    sesi.commit()

    diperiksa = rekonsiliasi_batas.perbarui_batas_untuk_run_v(
        sesi, run_2, setelan=setelan
    )
    assert diperiksa == 1

    ringkasan = layanan.ringkasan_rekonsiliasi_batas(sesi, kdprov="33", kdkab="3301")
    assert ringkasan["total_pasang"] == 3  # 3301 bertetangga dengan 3302, 3305, 3329
    assert ringkasan["belum_clean"] == 1
    assert ringkasan["menunggu_tetangga"] == 2

    # Multi-kdkab dan multi-status
    ringkasan_multi = layanan.ringkasan_rekonsiliasi_batas(
        sesi,
        kdprov="33",
        kdkab=["3301", "3302"],
        status_filter=["belum_clean", "clean"],
    )
    assert len(ringkasan_multi["baris"]) == 1
    baris_3301_3302 = ringkasan_multi["baris"][0]
    assert baris_3301_3302["waktu_a"] is not None
    assert baris_3301_3302["waktu_b"] is not None
    assert baris_3301_3302["pengunggah_a"] == "Petugas Cilacap"
    assert baris_3301_3302["pengunggah_b"] == "Petugas Banyumas"
    assert baris_3301_3302["ada_peta_a"] is True
    assert baris_3301_3302["ada_peta_b"] is True

    detail = layanan.detail_rekonsiliasi_batas(sesi, "3301", "3302")
    assert detail["status"] == "belum_clean"
    assert detail["jumlah_overlap"] == 1
    assert detail["ada_geojson"] is True
    assert detail["waktu_a"] is not None
    assert detail["waktu_b"] is not None
    assert detail["ada_peta_a"] is True
    assert detail["ada_peta_b"] is True
    assert len(detail["temuan"]) == 1
    assert detail["temuan"][0]["idsubsls_a"] == "3301010001000100"
    assert detail["temuan"][0]["idsubsls_b"] == "3302010001000100"

    jalur_geo, nama_geo = layanan.jalur_unduh_geojson_batas(sesi, "3301", "3302")
    assert nama_geo == "QC_Batas_3301_3302.geojson"
    isi_geo = json.loads(jalur_geo.read_text(encoding="utf-8"))
    assert isi_geo["type"] == "FeatureCollection"
    assert len(isi_geo["features"]) == 1

    jalur_peta_a, nama_peta_a = layanan.jalur_unduh_peta_batas(
        sesi, "3301", "3302", "3301"
    )
    assert jalur_peta_a == berkas_3301
    assert "3301" in nama_peta_a

    jalur_peta_b, nama_peta_b = layanan.jalur_unduh_peta_batas(
        sesi, "3301", "3302", "3302"
    )
    assert jalur_peta_b == berkas_3302
    assert "3302" in nama_peta_b


def test_ambang_luas_minimum_bawaan_nol_menangkap_overlap_mikro() -> None:
    """Ambang 0 (bawaan) mencatat overlap mikroskopis, sama seperti QGIS.

    Dengan ambang lebih besar, irisan selebar sepersekian nanometer itu
    dibuang sehingga hasil PointSE lebih ramping daripada Topology Checker.
    """
    a = shapely.box(109.0, -7.5, 109.01, -7.49)
    b = shapely.box(109.01 - 1e-13, -7.5, 109.02, -7.4999)
    atr_a = [{"idsls": "33010100010001", "idsubsls": "3301010001000100", "nmsls": "A"}]
    atr_b = [{"idsls": "33020100010001", "idsubsls": "3302010001000100", "nmsls": "B"}]

    hasil_nol = rekonsiliasi_batas.periksa_batas_dua_geometri(
        "3301", "3302", [a], atr_a, [b], atr_b, luas_min_m2=0.0
    )
    assert hasil_nol.jumlah_overlap == 1
    assert hasil_nol.temuan[0].jenis == "overlap"
    assert hasil_nol.temuan[0].luas_m2 < 0.001

    hasil_ambang = rekonsiliasi_batas.periksa_batas_dua_geometri(
        "3301", "3302", [a], atr_a, [b], atr_b, luas_min_m2=1e-6
    )
    assert hasil_ambang.jumlah_overlap == 0


def test_pengaturan_luas_min_batas_bawaan_dan_simpan(sesi) -> None:
    """Pengaturan ambang: bawaan 0, tersimpan sebagai teks, nilai rusak diabaikan."""
    from app import pengaturan

    assert pengaturan.baca_luas_min_batas(sesi) == 0.0

    assert pengaturan.tulis_luas_min_batas(sesi, 1e-6, oleh="admin") == 1e-6
    sesi.commit()
    assert pengaturan.baca_luas_min_batas(sesi) == 1e-6

    pengaturan.tulis_nilai(sesi, KUNCI_LUAS_MIN_BATAS, "bukan angka")
    sesi.commit()
    assert pengaturan.baca_luas_min_batas(sesi) == 0.0


def test_ringkasan_memuat_ambang_toleransi(sesi) -> None:
    """Ringkasan yang dibaca semua peran memuat ambang toleransi yang berlaku."""
    assert layanan.ringkasan_rekonsiliasi_batas(sesi)["luas_min_m2"] == 0.0

    pengaturan.tulis_luas_min_batas(sesi, 1e-6, oleh="admin")
    sesi.commit()
    assert (
        layanan.ringkasan_rekonsiliasi_batas(sesi)["luas_min_m2"] == 0.000001
    )


def test_jalankan_ulang_semua_batas_memakai_ambang_baru(tmp_path, sesi, setelan) -> None:
    """Periksa ulang semua pasangan hanya menyentuh pasangan yang petanya lengkap."""
    def _tulis_geojson(jalur, fitur_list):
        jalur.parent.mkdir(parents=True, exist_ok=True)
        jalur.write_text(
            json.dumps({"type": "FeatureCollection", "features": fitur_list}),
            encoding="utf-8",
        )

    berkas_3301 = tmp_path / "peta_3301.geojson"
    berkas_3302 = tmp_path / "peta_3302.geojson"
    _tulis_geojson(
        berkas_3301,
        [
            {
                "type": "Feature",
                "properties": {
                    "idsls": "33010100010001",
                    "idsubsls": "3301010001000100",
                    "nmsls": "RT 001 RW 001",
                },
                "geometry": json.loads(
                    shapely.to_geojson(shapely.box(109.000, -7.500, 109.0102, -7.490))
                ),
            }
        ],
    )
    _tulis_geojson(
        berkas_3302,
        [
            {
                "type": "Feature",
                "properties": {
                    "idsls": "33020100010001",
                    "idsubsls": "3302010001000100",
                    "nmsls": "RT 005 RW 002",
                },
                "geometry": json.loads(
                    shapely.to_geojson(shapely.box(109.010, -7.500, 109.020, -7.490))
                ),
            }
        ],
    )

    for kode, berkas, nama in (
        ("3301", berkas_3301, "Petugas Cilacap"),
        ("3302", berkas_3302, "Petugas Banyumas"),
    ):
        sesi.add(
            Run(
                tipe=TIPE_V,
                kdprov="33",
                kdkab=kode,
                status=STATUS_SUKSES,
                tanggal_data=date(2026, 11, 10),
                user=nama,
                nama_file_input=berkas.name,
                nama_file_peta=berkas.name,
                berkas_input=str(berkas),
                berkas_peta=str(berkas),
                semester="2026_1",
            )
        )
    sesi.commit()

    kemajuan: list[tuple[int, int]] = []
    ringkas = rekonsiliasi_batas.jalankan_ulang_semua_batas(
        sesi,
        setelan,
        luas_min_m2=0.0,
        progres=lambda sudah, total: kemajuan.append((sudah, total)),
    )

    assert ringkas["total"] == 1
    assert ringkas["bersih"] == 0
    assert ringkas["belum_clean"] == 1
    assert ringkas["gagal"] == 0
    assert kemajuan[-1] == (1, 1)

    pasang = sesi.scalars(select(RekonsiliasiBatasPasang)).all()
    assert len(pasang) == 1
    assert (pasang[0].kdkab_a, pasang[0].kdkab_b) == ("3301", "3302")
    assert pasang[0].jumlah_overlap == 1


def test_api_pengaturan_dan_jalankan_ulang_batas(klien, sesi) -> None:
    """Admin dapat membaca/mengubah ambang dan mengantrekan pemeriksaan ulang."""
    awal = klien.get("/rekonsiliasi-batas/pengaturan")
    assert awal.status_code == 200
    assert awal.json()["luas_min_m2"] == 0.0
    assert awal.json()["jalankan"] is None

    ubah = klien.put(
        "/rekonsiliasi-batas/pengaturan", json={"luas_min_m2": 0.000001}
    )
    assert ubah.status_code == 200
    assert ubah.json()["luas_min_m2"] == 0.000001

    minta = klien.post("/rekonsiliasi-batas/jalankan-ulang")
    assert minta.status_code == 202
    assert minta.json()["status"] == "menunggu"
    assert minta.json()["luas_min_m2"] == 0.000001

    ganda = klien.post("/rekonsiliasi-batas/jalankan-ulang")
    assert ganda.status_code == 409

    status = klien.get("/rekonsiliasi-batas/jalankan-ulang")
    assert status.status_code == 200
    assert status.json()["status"] == "menunggu"

    negatif = klien.put("/rekonsiliasi-batas/pengaturan", json={"luas_min_m2": -1})
    assert negatif.status_code == 422
