"""Utilitas data uji QGIS di ``docs/`` (dipakai tes T1/T2 dan skrip ukur).

Data uji tidak ikut di-commit, jadi tes yang memakainya harus dilewati bila
file-nya tidak ada (lihat ``ada_data_uji``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import geopandas as gpd
import pandas as pd

AKAR_REPO = Path(__file__).resolve().parents[2]
DIR_DOCS = AKAR_REPO / "docs"

TITIK_GPKG = (
    DIR_DOCS / "Titik Bangunan dan SLS" / "3307" / "Landmark Bangunan" / "landmark_202523307.gpkg"
)
PETA_GEOJSON = (
    DIR_DOCS / "Titik Bangunan dan SLS" / "3307" / "Peta SLS SubSLS" / "Final_SLS_202513307.geojson"
)
OUTPUT_A_GPKG = DIR_DOCS / "hasil_identifikasi_titik_model1.gpkg"
OUTPUT_B_GPKG = DIR_DOCS / "hasil_pengecekan_posisi_model2.gpkg"

LAYER_TITIK = "geotag"
LAYER_OUTPUT_A = "hasil_identifikasi_titik"
LAYER_OUTPUT_B = "hasil_pengecekan_titik_hasil_penggeseran"

# Kolom yang di output QGIS tersimpan sebagai TEXT (artefak refactor fields),
# padahal isinya angka; dibandingkan secara angka saat verifikasi.
KOLOM_NUMERIK: tuple[str, ...] = (
    "flag_psls",
    "flag_repair_initial",
    "flag_repair",
    "latitude_origin",
    "longitude_origin",
    "jumlah_usaha_ditemukan",
    "kk",
    "btt",
    "bku",
    "bttk",
    "bbtt",
    "usaha",
)

_SENTINEL = object()

# Kolom keluaran Proses B yang di QGIS tersimpan sebagai TEXT padahal isinya
# angka (flag_edit_atr_repair, latitude_origin, ...); dibandingkan sebagai angka.
KOLOM_NUMERIK_B: tuple[str, ...] = KOLOM_NUMERIK + (
    "flag_position",
    "flag_edit_atr_repair",
    "latitude_edited",
    "longitude_edited",
)


def ada_data_uji() -> bool:
    """True bila semua file data uji Proses A tersedia."""
    return TITIK_GPKG.exists() and PETA_GEOJSON.exists() and OUTPUT_A_GPKG.exists()


def ada_data_uji_b() -> bool:
    """True bila data uji Proses A *dan* keluaran Proses B dari QGIS tersedia."""
    return ada_data_uji() and OUTPUT_B_GPKG.exists()


def muat_titik() -> gpd.GeoDataFrame:
    """Baca titik bangunan (layer ``geotag``)."""
    return gpd.read_file(TITIK_GPKG, layer=LAYER_TITIK)


def muat_peta() -> gpd.GeoDataFrame:
    """Baca peta batas wilkerstat (GeoJSON)."""
    return gpd.read_file(PETA_GEOJSON)


def muat_output_a() -> gpd.GeoDataFrame:
    """Baca output Proses A dari QGIS sebagai pembanding."""
    return gpd.read_file(OUTPUT_A_GPKG, layer=LAYER_OUTPUT_A)


def muat_output_b() -> gpd.GeoDataFrame:
    """Baca output Proses B dari QGIS sebagai pembanding."""
    return gpd.read_file(OUTPUT_B_GPKG, layer=LAYER_OUTPUT_B)


def bandingkan(
    hasil: pd.DataFrame,
    qgis: pd.DataFrame,
    kolom: Sequence[str],
    kolom_numerik: Sequence[str] = KOLOM_NUMERIK,
) -> dict[str, object]:
    """Bandingkan hasil Proses A dengan output QGIS, dicocokkan per assignment_id.

    Returns
    -------
    dict
        ``baris_hasil``, ``baris_qgis``, ``hanya_di_hasil``, ``hanya_di_qgis``,
        ``beda_per_kolom`` (jumlah baris berbeda per kolom), dan ``beda_total``.
    """
    a = hasil.set_index("assignment_id").sort_index()
    b = qgis.set_index("assignment_id").sort_index()

    laporan: dict[str, object] = {
        "baris_hasil": int(len(a)),
        "baris_qgis": int(len(b)),
        "hanya_di_hasil": int(len(a.index.difference(b.index))),
        "hanya_di_qgis": int(len(b.index.difference(a.index))),
    }

    a = a.reindex(b.index)
    # assignment_id sudah jadi index, tidak perlu dibandingkan lagi.
    kolom = [k for k in kolom if k != "assignment_id"]
    kolom_numerik = set(kolom_numerik)
    beda_per_kolom: dict[str, int] = {}
    id_beda_per_kolom: dict[str, pd.Index] = {}
    for nama in kolom:
        x, y = a[nama], b[nama]
        if nama in kolom_numerik:
            x = pd.to_numeric(x, errors="coerce")
            y = pd.to_numeric(y, errors="coerce")
            beda = (x != y) & ~(x.isna() & y.isna())
        else:
            xs = x.astype("object").where(x.notna(), _SENTINEL)
            ys = y.astype("object").where(y.notna(), _SENTINEL)
            beda = xs != ys
        jumlah = int(beda.sum())
        beda_per_kolom[nama] = jumlah
        if jumlah:
            id_beda_per_kolom[nama] = b.index[beda]

    laporan["beda_per_kolom"] = beda_per_kolom
    laporan["id_beda_per_kolom"] = id_beda_per_kolom
    laporan["beda_total"] = int(sum(beda_per_kolom.values()))
    return laporan
