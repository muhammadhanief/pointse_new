"""Ukur waktu per tahap + puncak RSS Proses A (tanpa basis data).

Contoh pemakaian dari folder ``backend``::

    .venv\\Scripts\\python.exe scripts\\ukur_proses_a.py ^
        --titik "..\\docs\\Titik Bangunan dan SLS\\3307\\Landmark Bangunan\\landmark_202523307.gpkg" ^
        --peta "..\\docs\\Titik Bangunan dan SLS\\3307\\Peta SLS SubSLS\\Final_SLS_202513307.geojson" ^
        --chunk 50000

``--chunk 0`` (default) memproses seluruh titik sekaligus; nilai > 0 memakai
mode hemat memori yang sama dengan worker (baca per potongan + siapkan baris per
batch). Skrip ini **tidak** membuka basis data; hasil tiap batch dibuang setelah
dihitung supaya puncak RSS mencerminkan pemrosesan, bukan penyimpanan.

Puncak RSS dibaca dengan ``resource.getrusage(RUSAGE_SELF).ru_maxrss`` di
Linux/macOS. Di Windows modul ``resource`` tidak tersedia, jadi dipakai
``scripts/_memori.py`` (API ``K32GetProcessMemoryInfo`` lewat ``ctypes``) —
tanpa ``psutil``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import geopandas as gpd

AKAR = Path(__file__).resolve().parents[1]
DIR_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(AKAR))
sys.path.insert(0, str(DIR_SCRIPTS))

import _memori  # noqa: E402

from app import worker as modul_worker  # noqa: E402
from app.potongan import baca_potongan  # noqa: E402
from app.proses_a import proses_a, proses_a_potongan  # noqa: E402

try:  # Linux/macOS; Windows tidak punya modul resource
    import resource
except ImportError:  # pragma: no cover - hanya Windows
    resource = None  # type: ignore[assignment]


def puncak_rss_mb() -> float | None:
    """Puncak RSS proses dalam MB (``resource`` atau API Windows, tanpa psutil)."""
    if resource is not None:
        nilai = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Linux/BSD: kilobyte; macOS: byte.
        return nilai / 1024 if sys.platform != "darwin" else nilai / (1024 * 1024)
    return _memori.memori("PeakWorkingSetSize")


def _mb(nilai: float | None) -> str:
    return "n/a" if nilai is None else f"{nilai:,.0f} MB"


def _siapkan_baris(hasil: gpd.GeoDataFrame) -> None:
    """Tirukan persiapan batch worker (tanpa insert), lalu buang hasilnya."""
    siap = modul_worker.tambah_kolom_wilayah(hasil, {})
    for mulai in range(0, len(siap), modul_worker.UKURAN_BATCH):
        potongan = siap.iloc[mulai : mulai + modul_worker.UKURAN_BATCH]
        modul_worker.siapkan_baris(potongan, 0)


def ukur(
    berkas_titik: Path,
    berkas_peta: Path,
    chunk: int,
    layer_titik: str | None,
    layer_peta: str | None,
) -> int:
    """Jalankan pengukuran; kembalikan 0 kalau berhasil."""
    if not berkas_titik.exists():
        print(f"berkas titik tidak ditemukan: {berkas_titik}")
        return 1
    if not berkas_peta.exists():
        print(f"berkas peta tidak ditemukan: {berkas_peta}")
        return 1
    if chunk < 0:
        print("--chunk tidak boleh negatif")
        return 1

    print("=" * 78)
    print("UKUR PROSES A")
    print("=" * 78)
    print(f"python      : {sys.version.split()[0]}")
    print(f"titik       : {berkas_titik}")
    print(f"peta        : {berkas_peta}")
    print(f"chunk       : {chunk if chunk else '0 (tanpa pemecahan)'}")
    print(f"RSS awal    : {_mb(puncak_rss_mb())}")

    t0 = time.perf_counter()
    peta = gpd.read_file(berkas_peta, layer=layer_peta)
    t_peta = time.perf_counter() - t0
    print(f"\n[baca peta] {len(peta):,} poligon | {t_peta:,.1f} s | puncak RSS {_mb(puncak_rss_mb())}")

    t_baca = t_proses = t_siap = 0.0
    jumlah_titik = 0

    if chunk <= 0:
        t0 = time.perf_counter()
        titik = gpd.read_file(berkas_titik, layer=layer_titik)
        t_baca = time.perf_counter() - t0
        jumlah_titik = len(titik)
        print(f"[baca titik] {jumlah_titik:,} baris | {t_baca:,.1f} s | puncak RSS {_mb(puncak_rss_mb())}")

        t0 = time.perf_counter()
        hasil = proses_a(titik, peta)
        t_proses = time.perf_counter() - t0
        print(f"[proses] {len(hasil):,} baris | {t_proses:,.1f} s | puncak RSS {_mb(puncak_rss_mb())}")

        t0 = time.perf_counter()
        _siapkan_baris(hasil)
        t_siap = time.perf_counter() - t0
        print(f"[siapkan baris] {len(hasil):,} baris | {t_siap:,.1f} s | puncak RSS {_mb(puncak_rss_mb())}")
    else:
        nomor = 0
        iterator = baca_potongan(berkas_titik, layer_titik, chunk)
        while True:
            t0 = time.perf_counter()
            try:
                urut_awal, potongan = next(iterator)
            except StopIteration:
                break
            baca = len(potongan)
            t_baca_satu = time.perf_counter() - t0
            t_baca += t_baca_satu
            jumlah_titik += baca
            nomor += 1

            t0 = time.perf_counter()
            hasil = proses_a_potongan(potongan, peta, urut_awal)
            t_proses_satu = time.perf_counter() - t0
            t_proses += t_proses_satu

            t0 = time.perf_counter()
            _siapkan_baris(hasil)
            t_siap_satu = time.perf_counter() - t0
            t_siap += t_siap_satu

            print(
                f"[potongan {nomor:>3}] titik {urut_awal:,}..{urut_awal + baca - 1:,} "
                f"({baca:,}) | baca {t_baca_satu:,.2f} s | proses {t_proses_satu:,.2f} s "
                f"| siapkan {t_siap_satu:,.2f} s | puncak RSS {_mb(puncak_rss_mb())}"
            )

    total = t_peta + t_baca + t_proses + t_siap
    print("\n" + "-" * 78)
    print(f"titik diproses : {jumlah_titik:,}")
    print(f"baca peta      : {t_peta:,.1f} s")
    print(f"baca titik     : {t_baca:,.1f} s ({chunk or 'sekali'} baris per baca)")
    print(f"proses A       : {t_proses:,.1f} s")
    print(f"siapkan baris  : {t_siap:,.1f} s")
    print(f"total tahap    : {total:,.1f} s")
    print(f"PUNCAK RSS     : {_mb(puncak_rss_mb())}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Baca argumen lalu jalankan pengukuran."""
    parser = argparse.ArgumentParser(description="Ukur waktu + puncak RSS Proses A.")
    parser.add_argument("--titik", required=True, type=Path, help="berkas titik (GPKG/GeoJSON)")
    parser.add_argument("--peta", required=True, type=Path, help="berkas peta (GPKG/GeoJSON)")
    parser.add_argument(
        "--chunk",
        type=int,
        default=0,
        help="jumlah titik per potongan (0 = tanpa pemecahan)",
    )
    parser.add_argument("--layer-titik", default=None, help="nama layer berkas titik")
    parser.add_argument("--layer-peta", default=None, help="nama layer berkas peta")
    argumen = parser.parse_args(argv)
    return ukur(
        argumen.titik,
        argumen.peta,
        argumen.chunk,
        argumen.layer_titik,
        argumen.layer_peta,
    )


if __name__ == "__main__":
    raise SystemExit(main())
