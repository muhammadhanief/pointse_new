"""Tes Proses B terhadap output QGIS asli (data uji di ``docs/``).

Dilewati otomatis bila data uji tidak ada, dan ditandai ``slow`` karena
memproses seluruh kabupaten (397 ribu titik). Data penuh dimuat dan dihitung
**sekali per sesi** lewat fixture ber-scope ``session``.

Dua catatan penting soal data uji ini:

1. Model 02 memakai "peta wilkerstat lama lapangan" yang tidak ada di ``docs/``;
   yang tersedia hanya ``Final_SLS_202513307.geojson``. Peta itu dipakai di sini
   karena pada output QGIS semua ``idsubsls_edited`` sama dengan
   ``idsubsls_origin`` (hasil join peta di Proses A), jadi join-nya memang
   menghasilkan SubSLS yang sama. Bila kelak ada file peta lama yang asli,
   ganti ``qgis_data.PETA_GEOJSON`` pada fixture ``peta`` dan ulangi tes.
2. Masukan titik = keluaran Proses A (``hasil_identifikasi_titik_model1.gpkg``),
   yaitu kasus "tidak ada titik yang digeser dan tidak ada atribut yang diedit":
   di file keluaran QGIS semua ``flag_position`` = 0 dan semua
   ``flag_edit_atr_repair`` = 0. Kasus titik yang benar-benar digeser/diedit diuji
   terpisah di ``test_proses_b_edit_qgis.py`` (berkas
   ``docs/Titik Bangunan dan SLS/3307/hasil_edit_runmodel2.gpkg``), jadi PRD §9 untuk
   Proses B terpenuhi oleh gabungan kedua tes ini.
"""

from __future__ import annotations

import geopandas as gpd
import pytest

from app.proses_b import KOLOM_HASIL_B, proses_b

import qgis_data

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not qgis_data.ada_data_uji_b(), reason="data uji docs/ tidak tersedia"),
]

BARIS_OUTPUT_QGIS = 397_364


@pytest.fixture(scope="session")
def titik() -> gpd.GeoDataFrame:
    """Masukan Proses B: titik hasil pengolahan (keluaran Proses A), sekali per sesi."""
    return qgis_data.muat_output_a()


@pytest.fixture(scope="session")
def peta() -> gpd.GeoDataFrame:
    """Peta batas wilkerstat, dimuat sekali per sesi tes."""
    return qgis_data.muat_peta()


@pytest.fixture(scope="session")
def output_qgis() -> gpd.GeoDataFrame:
    """Output Proses B dari QGIS sebagai pembanding."""
    return qgis_data.muat_output_b()


@pytest.fixture(scope="session")
def hasil(titik: gpd.GeoDataFrame, peta: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Hasil ``proses_b`` atas data penuh, dihitung sekali per sesi tes."""
    return proses_b(titik, peta)


@pytest.fixture(scope="session")
def laporan(
    hasil: gpd.GeoDataFrame, output_qgis: gpd.GeoDataFrame
) -> dict[str, object]:
    """Laporan pembandingan hasil kita dengan output QGIS."""
    return qgis_data.bandingkan(hasil, output_qgis, KOLOM_HASIL_B, qgis_data.KOLOM_NUMERIK_B)


def test_kasus_uji_memang_tanpa_titik_digeser(output_qgis: gpd.GeoDataFrame) -> None:
    """Pastikan data uji ini memang kasus "tidak ada yang digeser/diedit".

    Kalau tes ini gagal, berarti ada file keluaran Proses B lain dan tes
    berikutnya di bawah sudah menguji kasus penggeseran.
    """
    assert set(output_qgis["flag_position"].unique()) == {0}
    assert set(output_qgis["flag_edit_atr_repair"].astype(int).unique()) == {0}


def test_proses_b_sama_dengan_output_qgis(laporan: dict[str, object]) -> None:
    """Jumlah baris, semua kolom, dan himpunan assignment_id sama dengan QGIS."""
    assert laporan["baris_hasil"] == laporan["baris_qgis"] == BARIS_OUTPUT_QGIS
    assert laporan["hanya_di_hasil"] == 0, "ada assignment_id yang tidak ada di output QGIS"
    assert laporan["hanya_di_qgis"] == 0, "ada assignment_id QGIS yang tidak dihasilkan"

    beda = {kolom: jumlah for kolom, jumlah in laporan["beda_per_kolom"].items() if jumlah}
    assert not beda, f"kolom yang tidak sama dengan output QGIS: {beda}"


def test_urutan_hasil_seperti_qgis(hasil: gpd.GeoDataFrame, peta: gpd.GeoDataFrame) -> None:
    """Baris terkelompok per poligon peta (urutan peta) dan titik tak cocok di akhir."""
    posisi_peta = {k: i for i, k in enumerate(peta["idsubsls"])}
    cocok = hasil["idsubsls_edited"].notna().to_numpy()
    urutan_poligon = hasil.loc[cocok, "idsubsls_edited"].map(posisi_peta)

    assert not urutan_poligon.isna().any()
    nilai = urutan_poligon.to_numpy()
    assert (nilai[1:] >= nilai[:-1]).all(), "baris tidak terkelompok per urutan peta"
    assert cocok[: cocok.sum()].all(), "titik tak cocok tidak ditaruh di akhir"


def test_jumlah_baris_dan_assignment_id_unik(
    titik: gpd.GeoDataFrame, hasil: gpd.GeoDataFrame
) -> None:
    """Jumlah baris = jumlah assignment_id unik, duplikat dibuang seperti model."""
    assert len(hasil) == titik["assignment_id"].nunique()
    assert hasil["assignment_id"].is_unique
