"""Tes mode potongan pada data uji penuh (Wonosobo, 397 ribu titik).

Dilewati otomatis bila data uji tidak ada. Tes ini membandingkan hasil
penggabungan potongan (urutan + dedup memakai :func:`app.worker.kunci_potongan`)
dengan hasil :func:`app.proses_a.proses_a` sekali jalan: harus identik, termasuk
urutan baris dan semua nilai kolom.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from app.potongan import baca_potongan
from app.proses_a import KOLOM_HASIL, proses_a, proses_a_potongan
from app.worker import kunci_potongan

import qgis_data

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not qgis_data.ada_data_uji(), reason="data uji docs/ tidak tersedia"),
]

#: Ukuran potongan uji; data uji berisi 397.443 titik.
UKURAN_POTONGAN = 50_000

#: Jumlah baris keluaran Proses A pada data uji (sama dengan output QGIS).
BARIS_OUTPUT = 397_364


def test_potongan_sama_dengan_sekali_jalan() -> None:
    """Gabungan potongan = hasil sekali jalan (baris, urutan, nilai, geometri)."""
    titik = qgis_data.muat_titik()
    peta = qgis_data.muat_peta()
    normal = proses_a(titik, peta).reset_index(drop=True)

    bagian: list[gpd.GeoDataFrame] = []
    for urut_awal, potongan in baca_potongan(
        str(qgis_data.TITIK_GPKG), qgis_data.LAYER_TITIK, UKURAN_POTONGAN
    ):
        hasil = proses_a_potongan(potongan, peta, urut_awal)
        hasil["_kunci"] = kunci_potongan(hasil)
        bagian.append(hasil)

    gabung = pd.concat(bagian, ignore_index=True)
    gabung = (
        gabung.sort_values("_kunci", kind="stable")
        .drop_duplicates("assignment_id", keep="first")
        .reset_index(drop=True)
    )

    assert len(normal) == BARIS_OUTPUT
    assert len(gabung) == len(normal)
    assert gabung["assignment_id"].tolist() == normal["assignment_id"].tolist()
    for kolom in KOLOM_HASIL:
        pd.testing.assert_series_equal(
            gabung[kolom], normal[kolom], check_dtype=False, check_names=False
        )
    np.testing.assert_allclose(gabung.geometry.x, normal.geometry.x)
    np.testing.assert_allclose(gabung.geometry.y, normal.geometry.y)
