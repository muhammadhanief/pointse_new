"""Ukur waktu + memori Proses A pada data uji penuh, lalu bandingkan output QGIS.

Jalankan dari folder ``backend``:

    .venv\\Scripts\\python.exe scripts\\ukur_proses_a.py

Skrip ini alat ukur, bukan bagian aplikasi.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

# Pakai utilitas data uji yang sama dengan tes (satu sumber kebenaran).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import qgis_data  # noqa: E402

from app.proses_a import KOLOM_HASIL, proses_a  # noqa: E402

import _memori as _modul_memori  # noqa: E402

# Alias pendek supaya pemakaian di bawah ringkas.
_memori = _modul_memori.memori
_mb = _modul_memori.mb


def main() -> int:
    if not qgis_data.ada_data_uji():
        print("Data uji tidak ada di docs/. Skrip ini butuh data uji penuh.")
        return 1

    print("=" * 78)
    print("UKUR PROSES A — data uji kdkab 3307")
    print("=" * 78)
    print(f"python : {sys.version.split()[0]}")
    print(f"memori awal (RSS)   : {_mb(_memori('WorkingSetSize'))}")

    t0 = time.perf_counter()
    titik = qgis_data.muat_titik()
    peta = qgis_data.muat_peta()
    t_baca = time.perf_counter() - t0
    print(f"\n[baca] titik {len(titik):,} baris | peta {len(peta):,} poligon")
    print(f"[baca] waktu {t_baca:,.1f} s | memori {_mb(_memori('WorkingSetSize'))}")

    t0 = time.perf_counter()
    hasil = proses_a(titik, peta)
    t_proses = time.perf_counter() - t0

    print(f"\n[proses] waktu {t_proses:,.1f} s")
    print(f"[proses] memori proses (RSS) : {_mb(_memori('WorkingSetSize'))}")
    print(f"[proses] memori puncak proses: {_mb(_memori('PeakWorkingSetSize'))}")
    print(f"[proses] hasil {len(hasil):,} baris")

    # ------- bandingkan dengan output QGIS -------
    t0 = time.perf_counter()
    qgis = qgis_data.muat_output_a()
    laporan = qgis_data.bandingkan(hasil, qgis, KOLOM_HASIL)
    t_banding = time.perf_counter() - t0

    print("\n" + "-" * 78)
    print("BANDINGKAN DENGAN OUTPUT QGIS (hasil_identifikasi_titik_model1.gpkg)")
    print("-" * 78)
    print(f"baris hasil : {laporan['baris_hasil']:,}")
    print(f"baris QGIS  : {laporan['baris_qgis']:,}")
    print(f"tanpa pasangan -> hanya di hasil: {laporan['hanya_di_hasil']:,}"
          f" | hanya di QGIS: {laporan['hanya_di_qgis']:,}")
    print(f"waktu bandingkan: {t_banding:,.1f} s")
    print("\nbaris berbeda per kolom:")
    for kolom, jumlah in laporan["beda_per_kolom"].items():  # type: ignore[union-attr]
        tanda = "OK " if jumlah == 0 else "BEDA"
        print(f"  [{tanda}] {kolom:<24} {jumlah:,}")
    print(f"\nTOTAL beda: {laporan['beda_total']:,}")

    # ------- info tambahan: asal selisih -------
    id_beda_psls = laporan["id_beda_per_kolom"].get("flag_psls")
    jumlah_beda_psls = 0 if id_beda_psls is None else len(id_beda_psls)
    duplikat = set(titik.loc[titik["assignment_id"].duplicated(keep=False), "assignment_id"])
    tanpa_wilayah = int(hasil["idsubsls_origin"].isna().sum())

    print(f"\nassignment_id ganda di input   : {len(duplikat):,}")
    print(f"selisih flag_psls              : {jumlah_beda_psls:,} baris "
          f"(semua dari assignment_id ganda: {id_beda_psls is not None and set(id_beda_psls) <= duplikat})")
    print(f"titik tanpa wilayah (tak cocok): {tanpa_wilayah:,} baris (flag_repair = 1)")

    semua_sama = laporan["beda_total"] == jumlah_beda_psls and semua_sama_selain_psls(laporan)
    print("\nVERDICT:", "SAMA dengan output QGIS (selisih hanya flag_psls pada assignment_id ganda)"
          if semua_sama else "ADA BEDA di luar flag_psls pada assignment_id ganda")
    return 0


def semua_sama_selain_psls(laporan: dict) -> bool:
    """True bila tidak ada kolom lain yang berbeda selain flag_psls."""
    return all(
        jumlah == 0
        for kolom, jumlah in laporan["beda_per_kolom"].items()
        if kolom != "flag_psls"
    )


if __name__ == "__main__":
    raise SystemExit(main())
