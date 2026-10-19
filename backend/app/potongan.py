"""Baca titik per potongan dari disk (mode hemat memori).

Dipakai worker saat ``PROSES_CHUNK_TITIK`` > 0. Titik dibaca lewat
``pyogrio.skip_features``/``max_features`` supaya hanya satu potongan yang
berada di memori; peta tetap dibaca utuh dan dipakai untuk semua potongan.
"""

from __future__ import annotations

from collections.abc import Iterator

import geopandas as gpd
import pyogrio


def jumlah_titik(berkas: str, layer: str | None = None) -> int:
    """Jumlah fitur (titik) pada berkas masukan."""
    return int(pyogrio.read_info(berkas, layer=layer)["features"])


def baca_potongan(
    berkas: str, layer: str | None = None, ukuran: int = 0
) -> Iterator[tuple[int, gpd.GeoDataFrame]]:
    """Hasilkan ``(nomor_urut_awal, potongan)`` per ``ukuran`` baris.

    ``ukuran`` 0/negatif berarti satu potongan berisi seluruh berkas (dipakai
    jalur tanpa pemecahan). Nomor urut awal dimulai dari 0 dan naik sebesar
    ``len(potongan)``, sehingga urutan titik di potongan sama dengan urutan
    baris di berkas asal.
    """
    total = jumlah_titik(berkas, layer)
    if ukuran <= 0:
        if total:
            yield 0, pyogrio.read_dataframe(berkas, layer=layer)
        return

    for mulai in range(0, total, ukuran):
        yield mulai, pyogrio.read_dataframe(
            berkas,
            layer=layer,
            skip_features=mulai,
            max_features=ukuran,
        )
