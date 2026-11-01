"""Jarak pergeseran titik dari posisinya di Master GS (berkas A).

``flag_position`` dari model QGIS hanya membandingkan ``latitude`` dan
menganggap perbedaan sekecil apa pun (termasuk getaran GPS beberapa sentimeter)
sebagai "digeser". Modul ini menghitung jarak datar sebenarnya dari **kedua**
koordinat supaya menu pencermatan titik hanya memunculkan pergeseran yang
berarti (:data:`JARAK_GESER_MIN_M`).

Modul sengaja tidak mengimpor pandas/geopandas/numpy supaya aman dipakai API
(yang tidak boleh memuat pustaka berat saat startup). Versi vektor untuk worker
ada di :func:`app.worker.tambah_kolom_jarak`.
"""

from __future__ import annotations

import math

#: Ambang pergeseran yang dianggap pengamatan (meter). Di bawah ini dianggap
#: getaran GPS/pembulatan koordinat, bukan pergeseran yang perlu dicermati.
JARAK_GESER_MIN_M = 10.0

#: Jari-jari bumi rata-rata (meter) untuk rumus haversine.
R_BUMI_M = 6_371_008.8


def jarak_meter(
    lat_asal: float | None,
    lon_asal: float | None,
    lat_edit: float | None,
    lon_edit: float | None,
) -> float | None:
    """Jarak dua koordinat (derajat) dalam meter; ``None`` bila ada yang kosong.

    Memakai rumus haversine: cukup akurat (< 0,5%) untuk jarak puluhan meter di
    Indonesia dan tidak butuh proyeksi.
    """
    if lat_asal is None or lon_asal is None or lat_edit is None or lon_edit is None:
        return None
    try:
        lat1 = math.radians(float(lat_asal))
        lon1 = math.radians(float(lon_asal))
        lat2 = math.radians(float(lat_edit))
        lon2 = math.radians(float(lon_edit))
    except (TypeError, ValueError):
        return None

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * R_BUMI_M * math.asin(min(1.0, math.sqrt(a)))


def perlu_diamati(jarak: float | None) -> bool:
    """True bila pergeseran cukup jauh untuk dicatat sebagai pengamatan."""
    return jarak is not None and jarak >= JARAK_GESER_MIN_M