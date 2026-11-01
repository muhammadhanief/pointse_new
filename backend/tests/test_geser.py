"""Tes jarak geser titik (ambang 10 m) dan hitungannya di worker."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from app import geser
from app.worker import tambah_kolom_jarak

#: 1 derajat di permukaan bumi (meter) untuk R = 6.371.008,8 m.
SATU_DERAJAT_M = 2 * math.pi * geser.R_BUMI_M / 360


def test_jarak_titik_sama_nol() -> None:
    assert geser.jarak_meter(-7.5, 110.5, -7.5, 110.5) == pytest.approx(0.0)


def test_jarak_geser_vertikal_dan_horizontal_dihitung() -> None:
    """Kedua arah dihitung (model QGIS hanya melihat latitude)."""
    vertikal = geser.jarak_meter(0.0, 0.0, 0.001, 0.0)
    horizontal = geser.jarak_meter(0.0, 0.0, 0.0, 0.001)
    assert vertikal == pytest.approx(0.001 * SATU_DERAJAT_M, rel=1e-6)
    assert horizontal == pytest.approx(vertikal, rel=1e-6)


def test_jarak_koordinat_kosong_none() -> None:
    assert geser.jarak_meter(None, 110.0, -7.0, 110.0) is None
    assert geser.jarak_meter(-7.0, 110.0, -7.0, None) is None


def test_ambang_sepuluh_meter() -> None:
    assert not geser.perlu_diamati(None)
    assert not geser.perlu_diamati(9.99)
    assert geser.perlu_diamati(10.0)
    assert geser.perlu_diamati(25.0)


def test_tambah_kolom_jarak_worker_vektor() -> None:
    """Versi worker menghitung kedua koordinat; koordinat kosong tetap NULL."""
    hasilk = pd.DataFrame(
        {
            "latitude_origin": [0.0, 0.0, 0.0, None],
            "longitude_origin": [0.0, 0.0, 0.0, 110.0],
            "latitude_edited": [0.0, 0.001, 0.0, -7.0],
            "longitude_edited": [0.0, 0.0, 0.001, 110.0],
        }
    )
    jarak = tambah_kolom_jarak(hasilk)

    assert jarak.iloc[0] == pytest.approx(0.0)
    assert jarak.iloc[1] == pytest.approx(0.001 * SATU_DERAJAT_M, abs=0.01)
    # Hanya longitude berubah: flag_position model tetap 0, tetapi jaraknya nyata.
    assert jarak.iloc[2] == pytest.approx(0.001 * SATU_DERAJAT_M, abs=0.01)
    assert pd.isna(jarak.iloc[3])


def test_tambah_kolom_jarak_proses_a_tanpa_kolom_edit() -> None:
    """Proses A tidak punya koordinat hasil edit: jarak tidak diisi."""
    hasilk = pd.DataFrame({"latitude_origin": [0.0], "longitude_origin": [0.0]})
    assert pd.isna(tambah_kolom_jarak(hasilk).iloc[0])