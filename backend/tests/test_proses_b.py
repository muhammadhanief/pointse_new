"""Tes unit Proses B dengan data kecil buatan sendiri (tanpa data uji ``docs/``).

Fokusnya perilaku rumus flag sesuai model QGIS ``02 Pengecekan Titik.model3``,
termasuk kuirk model: ``flag_position`` hanya membandingkan **latitude**.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from app.proses_b import KOLOM_HASIL_B, proses_b

# Wilayah sama untuk semua poligon uji; yang membedakan hanya idsubsls.
WILAYAH = {
    "kdprov": "33",
    "nmprov": "JAWA TENGAH",
    "kdkab": "3307",
    "nmkab": "WONOSOBO",
    "kdkec": "330701",
    "nmkec": "MOJOTENGAH",
    "kddesa": "330701001",
    "nmdesa": "KALIBEBER",
    "idsls": "3307010010003900",
    "nmsls": "SLS 001",
}


def peta() -> gpd.GeoDataFrame:
    """Dua poligon SubSLS: A1 di kotak (0..1, 0..1) dan A2 di kotak (2..3, 0..1)."""
    baris = [
        {**WILAYAH, "idsubsls": "A1", "geometry": box(0.0, 0.0, 1.0, 1.0)},
        {**WILAYAH, "idsubsls": "A2", "geometry": box(2.0, 0.0, 3.0, 1.0)},
    ]
    return gpd.GeoDataFrame(baris, crs="EPSG:4326")


def titik(**ubah: object) -> gpd.GeoDataFrame:
    """Satu baris titik hasil pengolahan (keluaran Proses A) di dalam poligon A1."""
    nilai: dict[str, object] = {
        "assignment_id": "1",
        "unique_bang": "U1",
        "flag_psls": 0,
        "flag_repair_initial": 0,
        "flag_repair": 0,
        "level_6_full_code": "A1",
        "idsubsls_origin": "A1",
        "latitude_origin": 0.5,
        "longitude_origin": 0.5,
        "no_bang": "1",
        "kode_bang_value": 2,
        "ada_keluarga_value": 1,
        "ada_bang_usaha_value": 2,
        "jumlah_usaha_ditemukan": 0,
        "kk": 1,
        "btt": 1,
        "bku": 0,
        "bttk": 0,
        "bbtt": 0,
        "usaha": 0,
        "nama_usaha_bang": None,
        "geometry": Point(0.5, 0.5),
    }
    nilai.update(ubah)
    return gpd.GeoDataFrame([nilai], crs="EPSG:4326")


def gabung(*frames: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Gabung beberapa baris titik jadi satu GeoDataFrame (index dirapikan)."""
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def test_kolom_dan_urutan_hasil() -> None:
    """Keluaran memakai 35 kolom model QGIS (urutan sama) + geometri."""
    hasil = proses_b(titik(), peta())
    assert list(hasil.columns) == list(KOLOM_HASIL_B) + [
        "flag_repair_unggah",
        "geometry",
    ]
    assert hasil.crs is not None and hasil.crs.to_epsg() == 4326
    assert len(hasil) == 1


def test_titik_tidak_digeser_dan_tidak_diedit() -> None:
    """Titik apa adanya: tidak ada flag yang menyala, SLS hasil join sama."""
    hasil = proses_b(titik(), peta()).iloc[0]

    assert hasil["flag_position"] == 0
    assert hasil["flag_edit_atr_repair"] == 0
    assert hasil["flag_repair_initial"] == 0
    assert hasil["flag_repair"] == 0
    assert hasil["idsubsls_edited"] == "A1"
    assert hasil["idsubsls_origin"] == "A1"
    assert hasil["latitude_edited"] == 0.5
    assert hasil["longitude_edited"] == 0.5
    assert hasil["nmsls"] == "SLS 001"


def test_geser_latitude_menyalakan_flag_position() -> None:
    """Titik digeser (latitude berubah) di dalam poligon yang sama."""
    hasil = proses_b(titik(geometry=Point(0.5, 0.6)), peta()).iloc[0]

    assert hasil["latitude_edited"] == 0.6
    assert hasil["flag_position"] == 1
    assert hasil["idsubsls_edited"] == "A1"
    assert hasil["flag_repair_initial"] == 0


def test_geser_longitude_saja_flag_position_tetap_0() -> None:
    """Kuirk model yang direplikasi: ``flag_position`` hanya melihat latitude."""
    hasil = proses_b(titik(geometry=Point(0.9, 0.5)), peta()).iloc[0]

    assert hasil["longitude_edited"] == 0.9
    assert hasil["latitude_edited"] == 0.5
    assert hasil["flag_position"] == 0


def test_digeser_ke_sls_lain_belum_diperbaiki() -> None:
    """Pindah poligon, atribut tidak diedit, flag_repair masukan 1 → tetap 1."""
    hasil = proses_b(
        titik(
            level_6_full_code="A1",
            idsubsls_origin="A2",
            flag_repair_initial=1,
            flag_repair=1,
            latitude_origin=0.5,
            longitude_origin=2.5,
            geometry=Point(2.5, 0.9),
        ),
        peta(),
    ).iloc[0]

    assert hasil["idsubsls_origin"] == "A2"
    assert hasil["idsubsls_edited"] == "A2"
    assert hasil["flag_position"] == 1
    assert hasil["flag_edit_atr_repair"] == 0
    assert hasil["flag_repair_initial"] == 1
    assert hasil["flag_repair"] == 1


def test_pindah_ke_sls_yang_sesuai_menjadi_sudah_diperbaiki() -> None:
    """Titik yang dulu salah SLS lalu dipindah ke SLS yang benar → flag_repair 0."""
    hasil = proses_b(
        titik(
            level_6_full_code="A1",
            idsubsls_origin="A2",
            flag_repair_initial=1,
            flag_repair=1,
            longitude_origin=2.5,
            geometry=Point(0.5, 0.5),
        ),
        peta(),
    ).iloc[0]

    assert hasil["idsubsls_edited"] == "A1"
    assert hasil["flag_repair_initial"] == 0
    assert hasil["flag_repair"] == 0


def test_flag_repair_tidak_diubah_pada_atribut_yang_sudah_diedit() -> None:
    """Atribut flag_repair diedit manual (1→0) → flag_edit_atr_repair 1, nilai tetap."""
    hasil = proses_b(
        titik(flag_repair_initial=1, flag_repair=0), peta()
    ).iloc[0]

    assert hasil["flag_edit_atr_repair"] == 1
    assert hasil["flag_repair_initial"] == 0  # hasil join baru: sudah sesuai
    assert hasil["flag_repair"] == 0


def test_titik_di_luar_peta() -> None:
    """Titik tak menyentuh poligon mana pun: wilayah kosong, flag_repair_initial 1."""
    hasil = proses_b(titik(geometry=Point(9.0, 9.0)), peta()).iloc[0]

    assert pd.isna(hasil["idsubsls_edited"])
    assert pd.isna(hasil["kdprov"])
    assert pd.isna(hasil["nmdesa"])
    assert hasil["flag_position"] == 1
    assert hasil["flag_repair_initial"] == 1
    assert hasil["flag_repair"] == 1


def test_latitude_origin_kosong_menyalakan_flag_position() -> None:
    """Latitude kosong (NULL) di QGIS → ``if(NULL, 0, 1)`` → 1."""
    hasil = proses_b(titik(latitude_origin=None), peta()).iloc[0]
    assert hasil["flag_position"] == 1


def test_flag_repair_kosong_tidak_menyalakan_flag_edit_atr() -> None:
    """NULL != NULL di QGIS menghasilkan NULL, jadi flag_edit_atr_repair 0."""
    hasil = proses_b(titik(flag_repair=None, flag_repair_initial=None), peta()).iloc[0]

    assert hasil["flag_edit_atr_repair"] == 0
    assert pd.isna(hasil["flag_repair"])


def test_latitude_origin_teks_dibandingkan_sebagai_angka() -> None:
    """Latitude_origin bertipe teks (artefak QGIS) tetap dibandingkan sebagai angka."""
    hasil = proses_b(titik(latitude_origin="-7.4162721", geometry=Point(0.5, -7.4162721)), peta())
    assert hasil["flag_position"].iloc[0] == 0


def test_duplikat_assignment_id_memakai_baris_pertama() -> None:
    """Duplikat ``assignment_id`` dibuang, kemunculan pertama yang dipakai."""
    pertama = titik(assignment_id="7", no_bang="1")
    kedua = titik(assignment_id="7", no_bang="2", geometry=Point(0.6, 0.5))
    hasil = proses_b(gabung(pertama, kedua), peta())

    assert len(hasil) == 1
    assert hasil["no_bang"].iloc[0] == "1"


def test_urutan_per_poligon_lalu_tak_cocok_di_akhir() -> None:
    """Urutan baris mengikuti urutan poligon peta, titik tak cocok paling akhir."""
    baris = gabung(
        titik(assignment_id="2", level_6_full_code="A2", idsubsls_origin="A2",
              latitude_origin=0.5, longitude_origin=2.5, geometry=Point(2.5, 0.5)),
        titik(assignment_id="1"),
        titik(assignment_id="3", geometry=Point(9.0, 9.0)),
    )
    hasil = proses_b(baris, peta())

    assert list(hasil["assignment_id"]) == ["1", "2", "3"]


def test_index_titik_dipertahankan() -> None:
    """Index masukan dipakai lagi di keluaran (memudahkan pemanggil)."""
    baris = titik()
    baris.index = [42]
    hasil = proses_b(baris, peta())
    assert list(hasil.index) == [42]


def test_masukan_tidak_diubah() -> None:
    """Fungsi murni: masukan tidak dimodifikasi."""
    data_titik, data_peta = titik(), peta()
    salinan_titik, salinan_peta = data_titik.copy(), data_peta.copy()

    proses_b(data_titik, data_peta)

    pd.testing.assert_frame_equal(data_titik, salinan_titik)
    pd.testing.assert_frame_equal(data_peta, salinan_peta)


def test_kolom_kurang_ditolak() -> None:
    """Kolom wajib yang hilang langsung ditolak, bukan diam-diam kosong."""
    with pytest.raises(ValueError, match="nama_usaha_bang"):
        proses_b(titik().drop(columns=["nama_usaha_bang"]), peta())


def test_bukan_geodataframe_ditolak() -> None:
    """Masukan harus GeoDataFrame."""
    with pytest.raises(TypeError, match="titik"):
        proses_b(pd.DataFrame({"assignment_id": [1]}), peta())
    with pytest.raises(TypeError, match="peta"):
        proses_b(titik(), pd.DataFrame({"idsubsls": ["A1"]}))
