"""Jalankan ulang validasi SLS 2026 S1 (run tipe V) terakhir per kabupaten/kota.

Berguna saat aturan validasi diperbarui (mis. penambahan Topology Checker)
agar job terakhir yang sudah terlanjur diunggah setiap kabupaten/kota ikut
diperiksa ulang tanpa petugas perlu mengunggah ulang berkasnya.

Contoh pemakaian di server::

    cd /opt/pointse/backend
    set -a && source /etc/pointse/pointse.env && set +a
    .venv/bin/python scripts/ulang_validasi_v.py
    .venv/bin/python scripts/ulang_validasi_v.py --kdkab 3316
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import select

AKAR_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR_BACKEND))

def daftar_run_terakhir(sesi, filter_kab: str | None = None) -> list[Run]:
    """Ambil satu run V dengan ``id`` terbesar untuk tiap kode kabupaten 4 digit."""
    from app import layanan
    from app.models import TIPE_V, Run

    daftar_filter = {
        k.strip() for k in (filter_kab or "").split(",") if k.strip()
    }
    semua = sesi.scalars(
        select(Run).where(Run.tipe == TIPE_V).order_by(Run.id.asc())
    ).all()
    terakhir_per_kab: dict[str, Run] = {}
    for satu in semua:
        kode = layanan.kode_kabupaten(satu.kdprov, satu.kdkab)
        if (
            daftar_filter
            and kode not in daftar_filter
            and (satu.kdkab or "") not in daftar_filter
        ):
            continue
        terakhir_per_kab[kode] = satu
    return [terakhir_per_kab[k] for k in sorted(terakhir_per_kab)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Proses ulang run validasi V terakhir per kabupaten/kota."
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Berkas environment server, mis. /etc/pointse/pointse.env",
    )
    parser.add_argument(
        "--kdkab",
        help="Hanya proses kabupaten/kota tertentu (bisa pisah koma, mis. 3321,3327,3372).",
        default=None,
    )
    args = parser.parse_args(argv)

    if args.env_file:
        from app.master_impor import muat_env

        muat_env(args.env_file)

    from app import layanan
    from app.db import get_sessionmaker
    from app.worker import proses_validasi_v, simpan_fase_akhir_v

    SessionLocal = get_sessionmaker()
    with SessionLocal() as sesi:
        daftar = daftar_run_terakhir(sesi, args.kdkab)
        if not daftar:
            print("Tidak ada run tipe V yang cocok.")
            return 0

        print(f"Ditemukan {len(daftar)} kabupaten/kota untuk diproses ulang:\n")
        gagal_baca = 0
        for urut, run in enumerate(daftar, start=1):
            kode = layanan.kode_kabupaten(run.kdprov, run.kdkab)
            berkas = Path(run.berkas_peta or "")
            print(
                f"[{urut}/{len(daftar)}] Kab {kode} | run #{run.id} | "
                f"berkas: {run.nama_file_peta}"
            )
            if not run.berkas_peta or not berkas.is_file():
                print(f"  -> DILEWATI: berkas tidak ditemukan di {run.berkas_peta}")
                gagal_baca += 1
                continue
            t0 = time.perf_counter()
            try:
                hasil = proses_validasi_v(sesi, run)
                simpan_fase_akhir_v(sesi, run, hasil)
                sesi.commit()
                durasi = time.perf_counter() - t0
                baris_topo = next(
                    (
                        b
                        for b in (run.pesan or "").splitlines()
                        if "Topology Checker" in b
                    ),
                    "-",
                )
                print(
                    f"  -> Selesai ({durasi:.1f}s) | status={run.status} | "
                    f"total_temuan={run.jumlah_baris} | {baris_topo}"
                )
            except Exception as exc:  # noqa: BLE001
                sesi.rollback()
                gagal_baca += 1
                print(f"  -> GAGAL memproses run #{run.id}: {exc}")

        print(
            f"\nSelesai memproses ulang {len(daftar) - gagal_baca}/{len(daftar)} "
            "kabupaten/kota."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
