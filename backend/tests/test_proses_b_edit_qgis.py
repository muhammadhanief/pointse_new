"""Tes Proses B pada data uji yang benar-benar diedit (titik digeser + atribut diubah).

Berkas ``docs/Titik Bangunan dan SLS/3307/hasil_edit_runmodel2.gpkg`` adalah keluaran
model QGIS 02 atas data yang sudah diedit: enam titik dipindah (``flag_position`` = 1)
dan ``flag_repair``-nya diubah manual (``flag_edit_atr_repair`` = 1). Kasus inilah yang
belum tercakup ``test_proses_b_qgis.py`` (data uji di sana tanpa penggeseran/editan),
sehingga bersama tes itu PRD §9 untuk Proses B terpenuhi.

Berkas masukan model tidak ada di ``docs/`` (hanya keluarannya), jadi masukannya
disusun ulang dari keluaran Proses A lewat :func:`qgis_data.muat_input_b_edit`;
lihat penjelasan dan alasan penolakan tafsir lain di fungsi tersebut. Sama seperti tes
data penuh lain: dilewati bila data uji tidak ada dan ditandai ``slow`` (data dimuat
dan dihitung sekali per sesi).
"""

from __future__ import annotations

import geopandas as gpd
import pytest

from app.proses_b import KOLOM_HASIL_B, proses_b

import qgis_data

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not qgis_data.ada_data_uji_b_edit(), reason="data uji docs/ tidak tersedia"
    ),
]

BARIS_OUTPUT_QGIS = 397_364
#: Titik yang digeser/diedit manual pada data uji ini.
JUMLAH_DIEDIT = 6


@pytest.fixture(scope="session")
def titik() -> gpd.GeoDataFrame:
    """Masukan Proses B "sudah diedit", disusun sekali per sesi tes."""
    return qgis_data.muat_input_b_edit()


@pytest.fixture(scope="session")
def peta() -> gpd.GeoDataFrame:
    """Peta batas wilkerstat, dimuat sekali per sesi tes."""
    return qgis_data.muat_peta()


@pytest.fixture(scope="session")
def output_qgis() -> gpd.GeoDataFrame:
    """Keluaran model QGIS 02 pada data yang sudah diedit (pembanding)."""
    return qgis_data.muat_output_b_edit()


@pytest.fixture(scope="session")
def hasil(titik: gpd.GeoDataFrame, peta: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Hasil ``proses_b`` atas data penuh, dihitung sekali per sesi tes."""
    return proses_b(titik, peta)


@pytest.fixture(scope="session")
def laporan(
    hasil: gpd.GeoDataFrame, output_qgis: gpd.GeoDataFrame
) -> dict[str, object]:
    """Laporan pembandingan hasil kita dengan keluaran QGIS."""
    return qgis_data.bandingkan(hasil, output_qgis, KOLOM_HASIL_B, qgis_data.KOLOM_NUMERIK_B)


def test_kasus_uji_memang_ada_editan(output_qgis: gpd.GeoDataFrame) -> None:
    """Pastikan data uji ini memang memuat titik digeser + atribut diubah manual."""
    position = qgis_data._kolom_angka(output_qgis, "flag_position")
    edit = qgis_data._kolom_angka(output_qgis, "flag_edit_atr_repair")

    assert int((position == 1).sum()) == JUMLAH_DIEDIT
    assert int((edit == 1).sum()) == JUMLAH_DIEDIT
    # titik yang atributnya diedit manual semuanya sudah "tidak perlu diperbaiki"
    assert set(qgis_data._kolom_angka(output_qgis, "flag_repair")[edit == 1].unique()) == {0}


def test_proses_b_sama_dengan_output_qgis_edit(laporan: dict[str, object]) -> None:
    """Jumlah baris, semua kolom, dan himpunan assignment_id sama dengan QGIS."""
    assert laporan["baris_hasil"] == laporan["baris_qgis"] == BARIS_OUTPUT_QGIS
    assert laporan["hanya_di_hasil"] == 0, "ada assignment_id yang tidak ada di keluaran QGIS"
    assert laporan["hanya_di_qgis"] == 0, "ada assignment_id QGIS yang tidak dihasilkan"

    beda = {kolom: jumlah for kolom, jumlah in laporan["beda_per_kolom"].items() if jumlah}
    assert not beda, f"kolom yang tidak sama dengan keluaran QGIS: {beda}"


def test_flag_penggeseran_dan_editan_sesuai_qgis(
    hasil: gpd.GeoDataFrame, output_qgis: gpd.GeoDataFrame
) -> None:
    """``flag_position``/``flag_edit_atr_repair`` = 1 pada titik yang sama dengan QGIS."""
    kiri = hasil.set_index("assignment_id")
    kanan = output_qgis.set_index("assignment_id")

    for nama in ("flag_position", "flag_edit_atr_repair", "flag_repair"):
        assert (
            set(kiri.index[qgis_data._kolom_angka(kiri, nama) == 1])
            == set(kanan.index[qgis_data._kolom_angka(kanan, nama) == 1])
        ), f"titik dengan {nama} = 1 berbeda dari keluaran QGIS"
    assert int((qgis_data._kolom_angka(hasil, "flag_position") == 1).sum()) == JUMLAH_DIEDIT


def test_titik_digeser_masuk_subsls_tugasnya(hasil: gpd.GeoDataFrame) -> None:
    """Titik yang digeser berakhir di SubSLS penugasannya (``flag_repair`` jadi 0)."""
    kiri = hasil.set_index("assignment_id")
    digeser = kiri.index[qgis_data._kolom_angka(kiri, "flag_position") == 1]

    assert len(digeser) == JUMLAH_DIEDIT
    assert (kiri.loc[digeser, "level_6_full_code"] == kiri.loc[digeser, "idsubsls_edited"]).all()
    assert (kiri.loc[digeser, "flag_repair"] == 0).all()
    assert (kiri.loc[digeser, "flag_repair_initial"] == 0).all()
    # perbandingan model asli memakai latitude: nilainya memang berubah
    assert (
        kiri.loc[digeser, "latitude_edited"] != kiri.loc[digeser, "latitude_origin"]
    ).all()
