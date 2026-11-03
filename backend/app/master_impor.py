"""Impor master SLS 2026 S1 dari Excel ke database (sekali jalan per kab).

Jalankan dari folder ``backend``::

    .venv/Scripts/python -m app.master_impor --sumber ../2026\\ Semester\\ 1/Peta\\ SLS...
    .venv/Scripts/python -m app.master_impor --sumber <dir-akar> --kdkab 3312

Tiap kabupaten: baca ``Master/msubsls_26_1_<kdkab>.xlsx`` (atau langsung di
``<kdkab>/``), buang baris tanpa ``idsubsls`` 16 digit, hapus baris lama
kabupaten itu, lalu sisipkan yang baru dalam satu transaksi. Keluar bukan-nol
bila ada kabupaten yang berkasnya hilang/rusak.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import delete, insert


def daftar_kabupaten(akar: Path, hanya: str | None = None) -> list[str]:
    """Kode kab yang punya folder di bawah akar (atau satu kode bila diminta)."""
    if hanya:
        kode = str(hanya).strip()
        return [kode] if (akar / kode).is_dir() else []
    return sorted(p.name for p in akar.iterdir() if p.is_dir() and p.name.strip())


def impor_kabupaten(sesi, akar: Path, kode: str) -> dict[str, object]:
    """Impor satu kabupaten; kembalikan hitungan {baris, disimpan, dilewati}."""
    from app import validasi_sls
    from app.models import MasterSls2026S1

    jalur, _ = validasi_sls.jalur_master(akar, kode)
    if not jalur.is_file():
        raise FileNotFoundError(f"master tidak ditemukan: {jalur}")
    pasangan, total_baris, dilewati, contoh_lewat = validasi_sls.baca_master_impor(
        jalur
    )
    sesi.execute(delete(MasterSls2026S1).where(MasterSls2026S1.kdkab == kode))
    if pasangan:
        sesi.execute(
            insert(MasterSls2026S1),
            [
                {
                    "kdprov": kode[:2],
                    "kdkab": kode,
                    "idsls": idsls,
                    "idsubsls": subsls,
                    "nmsls": nama,
                }
                for (idsls, subsls), nama in pasangan.items()
            ],
        )
    sesi.commit()
    return {
        "kdkab": kode,
        "baris": total_baris,
        "disimpan": len(pasangan),
        "dilewati": dilewati,
        "contoh_dilewati": contoh_lewat,
    }


def utama(argv: list[str] | None = None) -> int:
    """Titik masuk CLI; kembalikan kode keluar proses."""
    from app.config import get_settings
    from app.db import get_sessionmaker

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sumber",
        default=None,
        help="Folder akar master per kab (default: dir_master_sls_2026_s1)",
    )
    parser.add_argument("--kdkab", default=None, help="Hanya satu kab, mis. 3312")
    args = parser.parse_args(argv)

    setelan = get_settings()
    akar = Path(args.sumber) if args.sumber else Path(setelan.dir_master_sls_2026_s1)
    sesi_pabrik = get_sessionmaker()
    gagal = 0
    with sesi_pabrik() as sesi:
        for kode in daftar_kabupaten(akar, args.kdkab):
            try:
                hasil = impor_kabupaten(sesi, akar, kode)
            except (FileNotFoundError, ValueError, OSError) as galat:
                print(f"LEWAT {kode}: {galat}", file=sys.stderr)
                gagal += 1
                continue
            contoh = (
                f" contoh: {', '.join(str(x) for x in hasil['contoh_dilewati'])}"
                if hasil["contoh_dilewati"]
                else ""
            )
            print(
                f"OK {kode}: {hasil['disimpan']} pasangan "
                f"({hasil['dilewati']} baris dilewati{contoh})"
            )
    if not daftar_kabupaten(akar, args.kdkab):
        print(f"tidak ada folder kabupaten di: {akar}", file=sys.stderr)
        return 1
    return 1 if gagal else 0


if __name__ == "__main__":
    raise SystemExit(utama())
