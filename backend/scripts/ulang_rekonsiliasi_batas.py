"""Hitung ulang Rekonsiliasi Batas (Gap & Overlap) untuk seluruh pasangan tetangga run V.

Memeriksa 74 pasangan kabupaten/kota bertetangga di Jawa Tengah yang keduanya
sudah memiliki run ``TIPE_V`` dengan berkas peta tersedia di disk.

Cara pakai di server::

    cd /opt/pointse/backend
    sudo -u pointse /opt/pointse/backend/.venv/bin/python \\
        /opt/pointse/backend/scripts/ulang_rekonsiliasi_batas.py \\
        --env-file /etc/pointse/pointse.env
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

AKAR_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR_BACKEND))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=None,
        help="Berkas environment server, mis. /etc/pointse/pointse.env",
    )
    parser.add_argument(
        "--kdkab",
        default=None,
        help="Saring hanya pasangan yang melibatkan kab/kota ini (pisah koma, mis. 3302,3303)",
    )
    args = parser.parse_args(argv)

    if args.env_file:
        from app.master_impor import muat_env

        muat_env(args.env_file)

    from app import layanan, rekonsiliasi_batas
    from app.config import get_settings
    from app.db import get_sessionmaker

    setelan = get_settings()
    SessionLocal = get_sessionmaker()

    filter_kab = {
        layanan.kode_kabupaten("33", k.strip())
        for k in (args.kdkab or "").split(",")
        if k.strip()
    }

    with SessionLocal() as sesi:
        runs_v = rekonsiliasi_batas.run_v_terakhir_per_kab(sesi, kdprov="33")
        kandidat_pasang = [
            (a, b)
            for a, b in rekonsiliasi_batas.PASANGAN_TETANGGA_33
            if (not filter_kab or a in filter_kab or b in filter_kab)
            and a in runs_v
            and b in runs_v
            and runs_v[a].berkas_peta
            and Path(runs_v[a].berkas_peta).is_file()
            and runs_v[b].berkas_peta
            and Path(runs_v[b].berkas_peta).is_file()
        ]

        if not kandidat_pasang:
            print(
                f"Belum ada pasangan tetangga yang kedua kabupatennya sudah memiliki run V di disk "
                f"(kabupaten dengan run V saat ini: {len(runs_v)})."
            )
            return 0

        print(
            f"Menghitung rekonsiliasi batas untuk {len(kandidat_pasang)} pasangan tetangga...\n"
        )
        cache_geom: dict[str, tuple[list, list]] = {}
        sukses = 0
        for urut, (a, b) in enumerate(kandidat_pasang, start=1):
            run_a = runs_v[a]
            run_b = runs_v[b]
            nm_a = layanan.NAMA_KABUPATEN_33.get(a, a)
            nm_b = layanan.NAMA_KABUPATEN_33.get(b, b)
            t0 = time.perf_counter()
            try:
                if a not in cache_geom:
                    cache_geom[a] = rekonsiliasi_batas._baca_geometri_dan_atribut_berkas(
                        run_a.berkas_peta, run_a.layer_peta
                    )
                if b not in cache_geom:
                    cache_geom[b] = rekonsiliasi_batas._baca_geometri_dan_atribut_berkas(
                        run_b.berkas_peta, run_b.layer_peta
                    )
                geom_a, atr_a = cache_geom[a]
                geom_b, atr_b = cache_geom[b]
                hasil = rekonsiliasi_batas.periksa_batas_dua_geometri(
                    a, b, geom_a, atr_a, geom_b, atr_b
                )
                rekonsiliasi_batas.simpan_hasil_pasang(
                    sesi,
                    setelan,
                    kdprov="33",
                    kdkab_a=a,
                    kdkab_b=b,
                    run_a=run_a,
                    run_b=run_b,
                    hasil=hasil,
                )
                sesi.commit()
                durasi = time.perf_counter() - t0
                sukses += 1
                status_teks = "CLEAN" if hasil.bersih else "BELUM CLEAN"
                print(
                    f"[{urut}/{len(kandidat_pasang)}] {a} ({nm_a}) <-> {b} ({nm_b}) | "
                    f"{status_teks} | overlap={hasil.jumlah_overlap} ({hasil.total_luas_overlap_m2:.1f} m²) "
                    f"| gap={hasil.jumlah_gap} ({hasil.total_luas_gap_m2:.1f} m²) | {durasi:.2f}s"
                )
            except Exception as exc:  # noqa: BLE001
                sesi.rollback()
                print(f"[{urut}/{len(kandidat_pasang)}] GAGAL {a} <-> {b}: {exc}")

        print(
            f"\nSelesai: {sukses}/{len(kandidat_pasang)} pasangan perbatasan berhasil diperbarui."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
