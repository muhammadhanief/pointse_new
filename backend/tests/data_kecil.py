"""Pembuat data uji kecil (tanpa memakai data besar di ``docs/``).

Dipakai tes API dan worker: cukup beberapa titik + dua poligon SubSLS supaya
hasil Proses A/B bisa diprediksi manual.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import Point, box

# Wilayah dasar semua poligon uji (kdkab 3307 = Wonosobo, sama seperti data uji asli).
WILAYAH: dict[str, str] = {
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

# Dua poligon SubSLS: A1 di kotak (0..1, 0..1), A2 di kotak (2..3, 0..1).
POLIGON: dict[str, tuple[float, float, float, float]] = {
    "A1": (0.0, 0.0, 1.0, 1.0),
    "A2": (2.0, 0.0, 3.0, 1.0),
}


def peta(
    ubah: dict[str, dict[str, str]] | None = None,
) -> gpd.GeoDataFrame:
    """Peta dua SubSLS; ``ubah`` bisa menimpa kolom wilayah per SubSLS."""
    baris = []
    for idsubsls, (x1, y1, x2, y2) in POLIGON.items():
        wilayah = {**WILAYAH, **(ubah or {}).get(idsubsls, {})}
        baris.append({**wilayah, "idsubsls": idsubsls, "geometry": box(x1, y1, x2, y2)})
    return gpd.GeoDataFrame(baris, crs="EPSG:4326")


def baris_titik_a(
    assignment_id: str = "1",
    level_6_full_code: str = "A1",
    latitude: float = 0.5,
    longitude: float = 0.5,
    **ubah: Any,
) -> dict[str, Any]:
    """Satu baris masukan Proses A (layer ``geotag``) di dalam SubSLS A1."""
    baris: dict[str, Any] = {
        "assignment_id": assignment_id,
        "unique_bang": f"U{assignment_id}",
        "flag_psls": 0,
        "level_6_full_code": level_6_full_code,
        "geotag_latitude": latitude,
        "geotag_longitude": longitude,
        "no_bang": f"{int(assignment_id):04d}",
        "kode_bang_value": "2",
        "ada_keluarga_value": "1",
        "ada_bang_usaha_value": "2",
        "count_usaha": "0",
        "nama_usaha_bang": None,
        "geometry": Point(longitude, latitude),
    }
    baris.update(ubah)
    return baris


def titik_a(*baris: dict[str, Any]) -> gpd.GeoDataFrame:
    """GeoDataFrame masukan Proses A."""
    return gpd.GeoDataFrame(list(baris), crs="EPSG:4326")


def baris_titik_b(
    assignment_id: str = "1",
    level_6_full_code: str = "A1",
    latitude_origin: float = 0.5,
    longitude_origin: float = 0.5,
    latitude: float | None = None,
    longitude: float | None = None,
    **ubah: Any,
) -> dict[str, Any]:
    """Satu baris masukan Proses B (keluaran Proses A yang sudah diedit/digeser)."""
    baris: dict[str, Any] = {
        "assignment_id": assignment_id,
        "unique_bang": f"U{assignment_id}",
        "flag_psls": 0,
        "flag_repair_initial": 0,
        "flag_repair": 0,
        "level_6_full_code": level_6_full_code,
        "idsubsls_origin": "A1",
        "latitude_origin": latitude_origin,
        "longitude_origin": longitude_origin,
        "no_bang": f"{int(assignment_id):04d}",
        "kode_bang_value": "2",
        "ada_keluarga_value": "1",
        "ada_bang_usaha_value": "2",
        "jumlah_usaha_ditemukan": "0",
        "kk": 1,
        "btt": 1,
        "bku": 0,
        "bttk": 0,
        "bbtt": 0,
        "usaha": "0",
        "nama_usaha_bang": None,
        "geometry": Point(
            longitude_origin if longitude is None else longitude,
            latitude_origin if latitude is None else latitude,
        ),
    }
    baris.update(ubah)
    return baris


def titik_b(*baris: dict[str, Any]) -> gpd.GeoDataFrame:
    """GeoDataFrame masukan Proses B."""
    return gpd.GeoDataFrame(list(baris), crs="EPSG:4326")


def tulis(gdf: gpd.GeoDataFrame, path: Path) -> Path:
    """Tulis GeoDataFrame ke GeoJSON dan kembalikan path-nya."""
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GeoJSON")
    return path
