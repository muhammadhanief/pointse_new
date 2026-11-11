"""Deteksi daftar pasangan kabupaten/kota yang berbatasan langsung dari peta SLS Proses A.

Membaca poligon ``berkas_peta`` dari run ``TIPE_A`` sukses terakhir per
kabupaten/kota di database, lalu mencari pasangan kabupaten yang poligon
terluarnya berjarak <= ~200 meter (0.002 derajat).

Cara pakai di server::

    cd /opt/pointse/backend
    sudo -u pointse /opt/pointse/backend/.venv/bin/python \\
        /opt/pointse/backend/scripts/cek_tetangga_kab.py \\
        --env-file /etc/pointse/pointse.env
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import select

AKAR_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR_BACKEND))


def daftar_run_peta_terakhir(sesi) -> dict[str, object]:
    """Ambil satu run dengan ``berkas_peta`` ada di disk untuk tiap kabupaten."""
    from app import layanan
    from app.models import STATUS_SUKSES, TIPE_A, TIPE_V, Run

    semua = sesi.scalars(
        select(Run)
        .where(Run.tipe.in_([TIPE_A, TIPE_V]))
        .order_by(Run.id.asc())
    ).all()
    pilihan: dict[str, Run] = {}
    for satu in semua:
        if not satu.berkas_peta or not Path(satu.berkas_peta).is_file():
            continue
        kode = layanan.kode_kabupaten(satu.kdprov, satu.kdkab)
        sebelumnya = pilihan.get(kode)
        # Utamakan TIPE_A yang sukses; gunakan TIPE_V sebagai cadangan bila A tidak ada
        if sebelumnya is None:
            pilihan[kode] = satu
        elif satu.tipe == TIPE_A and satu.status == STATUS_SUKSES:
            pilihan[kode] = satu
        elif sebelumnya.tipe != TIPE_A:
            pilihan[kode] = satu
    return pilihan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=None,
        help="Berkas environment server, mis. /etc/pointse/pointse.env",
    )
    parser.add_argument(
        "--jarak-derajat",
        type=float,
        default=0.002,
        help="Ambang jarak poligon antar-kabupaten dalam derajat (default: 0.002 ~ 220m)",
    )
    args = parser.parse_args(argv)

    if args.env_file:
        from app.master_impor import muat_env

        muat_env(args.env_file)

    import pyogrio
    import shapely

    from app import layanan
    from app.db import get_sessionmaker

    t0 = time.perf_counter()
    SessionLocal = get_sessionmaker()
    with SessionLocal() as sesi:
        runs_per_kab = daftar_run_peta_terakhir(sesi)

    if not runs_per_kab:
        print("Tidak ditemukan berkas peta SLS di database/disk.")
        return 1

    print(f"Memuat geometri poligon SLS dari {len(runs_per_kab)} kabupaten/kota...")
    data_kab: dict[str, tuple[str, object, object]] = {}
    for kode in sorted(runs_per_kab):
        run = runs_per_kab[kode]
        nama_kab = layanan.NAMA_KABUPATEN_33.get(kode, kode)
        try:
            df = pyogrio.read_dataframe(
                str(run.berkas_peta),
                layer=run.layer_peta or None,
                columns=[],
            )
            geoms = df.geometry.values
            geoms = geoms[~shapely.is_empty(geoms) & ~shapely.is_missing(geoms)]
            if len(geoms) == 0:
                print(f"  [!] {kode} ({nama_kab}): geometri kosong")
                continue
            bounds = shapely.total_bounds(geoms)
            kotak = shapely.box(*bounds).buffer(args.jarak_derajat * 2)
            data_kab[kode] = (nama_kab, geoms, kotak)
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] Gagal membaca {kode} ({run.berkas_peta}): {exc}")

    print(f"\nHasil deteksi tetangga ({len(data_kab)} kab/kota):\n" + "=" * 72)
    pohon_kab = {kode: shapely.STRtree( data_kab[kode][1] ) for kode in data_kab}
    pasangan_unik: list[tuple[str, str, int, int]] = []
    peta_tetangga: dict[str, list[str]] = {kode: [] for kode in sorted(data_kab)}

    kode_urut = sorted(data_kab)
    for i, a in enumerate(kode_urut):
        nm_a, geoms_a, box_a = data_kab[a]
        tree_a = pohon_kab[a]
        for b in kode_urut[i + 1 :]:
            nm_b, geoms_b, box_b = data_kab[b]
            if not shapely.intersects(box_a, box_b):
                continue
            idx_b, idx_a = tree_a.query(
                geoms_b, predicate="dwithin", distance=args.jarak_derajat
            )
            jml_a = len(set(idx_a))
            jml_b = len(set(idx_b))
            if jml_a > 0 and jml_b > 0:
                pasangan_unik.append((a, b, jml_a, jml_b))
                peta_tetangga[a].append(f"{b} {nm_b} ({jml_a} SLS)")
                peta_tetangga[b].append(f"{a} {nm_a} ({jml_b} SLS)")

    for kode in kode_urut:
        nm_a = data_kab[kode][0]
        daftar = peta_tetangga[kode]
        print(f"{kode} - {nm_a} ({len(daftar)} tetangga):")
        for item in daftar:
            print(f"    -> {item}")

    durasi = time.perf_counter() - t0
    print("=" * 72)
    print(
        f"Total pasangan perbatasan unik: {len(pasangan_unik)} pasang "
        f"| Waktu hitung: {durasi:.1f} detik"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
