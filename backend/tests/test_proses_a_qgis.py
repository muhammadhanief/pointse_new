"""Tes Proses A terhadap output QGIS asli (data uji di ``docs/``).

Dilewati otomatis bila data uji tidak ada, dan ditandai ``slow`` karena
memproses seluruh kabupaten (397 ribu titik).

Seluruh data penuh dimuat dan dihitung **sekali per sesi** lewat fixture
ber-scope ``session``, supaya tiap tes tidak mengulang baca file dan
``proses_a``.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd
import pytest

from app.proses_a import KOLOM_HASIL, proses_a

import qgis_data

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not qgis_data.ada_data_uji(), reason="data uji docs/ tidak tersedia"),
]

# Hasil pengukuran pada data uji kdkab 3307 (lihat scripts/ukur_proses_a.py).
BARIS_OUTPUT_QGIS = 397_364


@pytest.fixture(scope="session")
def titik() -> gpd.GeoDataFrame:
    """Titik bangunan (layer ``geotag``), dimuat sekali per sesi tes."""
    return qgis_data.muat_titik()


@pytest.fixture(scope="session")
def peta() -> gpd.GeoDataFrame:
    """Peta batas wilkerstat, dimuat sekali per sesi tes."""
    return qgis_data.muat_peta()


@pytest.fixture(scope="session")
def output_qgis() -> gpd.GeoDataFrame:
    """Output Proses A dari QGIS sebagai pembanding, dimuat sekali per sesi."""
    return qgis_data.muat_output_a()


@pytest.fixture(scope="session")
def hasil(titik: gpd.GeoDataFrame, peta: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Hasil ``proses_a`` atas data penuh, dihitung sekali per sesi tes."""
    return proses_a(titik, peta)


@pytest.fixture(scope="session")
def laporan(
    hasil: gpd.GeoDataFrame, output_qgis: gpd.GeoDataFrame
) -> dict[str, Any]:
    """Laporan pembandingan hasil kita dengan output QGIS."""
    return qgis_data.bandingkan(hasil, output_qgis, KOLOM_HASIL)


def test_proses_a_sama_dengan_output_qgis(laporan: dict[str, Any]) -> None:
    """Jumlah baris dan semua kolom sama dengan output QGIS, kecuali flag_psls.

    ``flag_psls`` dikecualikan karena di file input ada 79 ``assignment_id``
    ganda: pasangan barisnya identik kecuali ``flag_psls`` (0 vs 1), sehingga
    baris mana yang tersisa setelah penghapusan duplikat mengikuti urutan file
    (lihat ``test_duplikat_memakai_baris_pertama_di_input``). Selisihnya diuji
    terpisah di ``test_beda_flag_psls_hanya_pada_assignment_id_duplikat``.
    """
    assert laporan["baris_hasil"] == laporan["baris_qgis"] == BARIS_OUTPUT_QGIS
    assert laporan["hanya_di_hasil"] == 0, "ada assignment_id yang tidak ada di output QGIS"
    assert laporan["hanya_di_qgis"] == 0, "ada assignment_id QGIS yang tidak dihasilkan"

    beda = {
        kolom: jumlah
        for kolom, jumlah in laporan["beda_per_kolom"].items()
        if jumlah and kolom != "flag_psls"
    }
    assert not beda, f"kolom yang tidak sama dengan output QGIS: {beda}"


def test_beda_flag_psls_hanya_pada_assignment_id_duplikat(
    titik: gpd.GeoDataFrame, laporan: dict[str, Any]
) -> None:
    """Selisih flag_psls hanya terjadi pada assignment_id yang ganda di input."""
    id_beda = laporan["id_beda_per_kolom"].get("flag_psls")
    duplikat = set(titik.loc[titik["assignment_id"].duplicated(keep=False), "assignment_id"])

    assert id_beda is not None, "seharusnya ada selisih flag_psls pada data uji ini"
    assert len(id_beda) <= len(duplikat)
    assert set(id_beda) <= duplikat, "ada selisih flag_psls di luar assignment_id duplikat"
    assert laporan["beda_total"] == len(id_beda)


def test_urutan_hasil_seperti_qgis(hasil: gpd.GeoDataFrame, peta: gpd.GeoDataFrame) -> None:
    """Baris terkelompok per poligon (urutan peta) dan titik tak cocok di akhir.

    Kolom ``idsubsls_origin`` dihitung per poligon, jadi urutannya harus
    non-decreasing terhadap urutan poligon di peta. Ini yang dilakukan
    ``joinattributesbylocation`` (iterasi peta) + ``mergevectorlayers``.
    """
    posisi_peta = {k: i for i, k in enumerate(peta["idsubsls"])}
    cocok = hasil["idsubsls_origin"].notna().to_numpy()
    urutan_poligon = hasil.loc[cocok, "idsubsls_origin"].map(posisi_peta)

    assert not urutan_poligon.isna().any()
    nilai = urutan_poligon.to_numpy()
    assert (nilai[1:] >= nilai[:-1]).all(), "baris tidak terkelompok per urutan peta"
    assert cocok[: cocok.sum()].all(), "titik tak cocok tidak ditaruh di akhir"


def test_duplikat_memakai_baris_pertama_di_input(
    titik: gpd.GeoDataFrame, hasil: gpd.GeoDataFrame
) -> None:
    """Aturan yang dipilih: untuk assignment_id ganda, dipakai kemunculan pertama.

    Model QGIS hanya mempertahankan baris pertama yang ditemui
    (``removeduplicatesbyattribute``), tanpa aturan lain. Untuk data uji ini
    kemunculan pertama di file adalah baris dengan ``flag_psls`` = 0.
    """
    ganda = titik[titik["assignment_id"].duplicated(keep=False)]
    pertama = ganda.drop_duplicates("assignment_id", keep="first").set_index("assignment_id")
    nilai_hasil = hasil.set_index("assignment_id")["flag_psls"].reindex(pertama.index)

    assert len(pertama) == 79
    assert (
        pd.to_numeric(nilai_hasil, errors="coerce")
        == pd.to_numeric(pertama["flag_psls"], errors="coerce")
    ).all()


def test_jumlah_baris_duplikat_dibuang(
    titik: gpd.GeoDataFrame, hasil: gpd.GeoDataFrame
) -> None:
    """Jumlah baris hasil = jumlah titik unik assignment_id (duplikat dibuang)."""
    assert len(hasil) == titik["assignment_id"].nunique()
    assert hasil["assignment_id"].is_unique
