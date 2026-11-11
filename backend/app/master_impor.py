"""Impor master SLS 2026 S1 dari Excel ke database (sekali jalan per kab).

Jalankan dari folder ``backend``::

    .venv/Scripts/python -m app.master_impor --sumber ../2026\\ Semester\\ 1/Peta\\ SLS...
    .venv/Scripts/python -m app.master_impor --sumber <dir-akar> --kdkab 3312

Tiap kabupaten: baca ``Master/msubsls_26_1_<kdkab>.xlsx`` (atau langsung di
``<kdkab>/``), buang baris tanpa ``idsubsls`` 16 digit, hapus baris lama
kabupaten itu, lalu sisipkan yang baru dalam satu transaksi. Keluar bukan-nol
bila ada kabupaten yang berkasnya hilang/rusak.
Di server, jalankan sebagai ``pointse`` dan beri ``--env-file`` (jangan
``source`` berkas env di bash: bash membuang tanda kutip di dalam nilai JSON
seperti ``CORS_ORIGINS``):

    sudo -u pointse .venv/bin/python -m app.master_impor \\
        --env-file /etc/pointse/pointse.env --kdkab 3312
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import delete, insert


def daftar_kabupaten(akar: Path, hanya: str | None = None) -> list[str]:
    """Kode kab yang punya folder di bawah akar (atau satu kode bila diminta)."""
    if hanya:
        kode = str(hanya).strip()
        return [kode] if (akar / kode).is_dir() else []
    return sorted(
        p.name
        for p in akar.iterdir()
        if p.is_dir() and p.name.strip() and p.name.strip() != "3300"
    )


def ekstrak_zip_master(
    jalur_zip: Path, tujuan: Path, hanya: str | None = None
) -> list[str]:
    """Ekstrak arsip ``33.zip`` ke folder ``tujuan`` (menghapus awalan ``33/``).

    Kembalikan daftar berkas relatif yang ditulis ulang karena isinya baru atau
    berbeda dari berkas yang sudah ada di ``tujuan``.
    """
    diubah: list[str] = []
    kode_filter = str(hanya).strip() if hanya else None
    with zipfile.ZipFile(jalur_zip) as arsip:
        for info in arsip.infolist():
            if info.is_dir():
                continue
            bagian = [b for b in Path(info.filename).parts if b not in ("", ".", "..")]
            if not bagian:
                continue
            if len(bagian) >= 2 and len(bagian[0]) == 2 and bagian[0].isdigit():
                bagian = bagian[1:]
            if not bagian:
                continue
            if kode_filter and bagian[0] != kode_filter:
                continue
            rel = Path(*bagian)
            target = tujuan / rel
            isi_baru = arsip.read(info.filename)
            isi_lama = target.read_bytes() if target.is_file() else None
            if isi_lama != isi_baru:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(isi_baru)
                diubah.append(rel.as_posix())
    return diubah


@contextmanager
def siapkan_akar_sumber(
    sumber: Path,
    ekstrak_ke: Path | None = None,
    hanya: str | None = None,
) -> Iterator[Path]:
    """Siapkan folder akar master dari direktori atau arsip ``.zip``."""
    if sumber.is_file() and sumber.suffix.lower() == ".zip":
        if ekstrak_ke is not None:
            ekstrak_zip_master(sumber, ekstrak_ke, hanya=hanya)
            yield ekstrak_ke
            return
        with tempfile.TemporaryDirectory(prefix="pointse_master_") as tmp_dir:
            tujuan = Path(tmp_dir)
            ekstrak_zip_master(sumber, tujuan, hanya=hanya)
            yield tujuan
            return
    if sumber.is_dir():
        sub_prov = [
            p
            for p in sumber.iterdir()
            if p.is_dir() and len(p.name) == 2 and p.name.isdigit()
        ]
        if len(sub_prov) == 1 and not any(
            p.is_dir() and len(p.name) == 4 and p.name.isdigit()
            for p in sumber.iterdir()
        ):
            yield sub_prov[0]
            return
    yield sumber


def impor_kabupaten(sesi, akar: Path, kode: str) -> dict[str, object]:
    """Impor satu kabupaten; kembalikan hitungan {baris, disimpan, dilewati}."""
    from app import validasi_sls
    from app.models import MasterSls2026S1

    jalur, jalur_hirarki = validasi_sls.jalur_master(akar, kode)
    if not jalur.is_file():
        raise FileNotFoundError(f"master tidak ditemukan: {jalur}")
    pasangan, total_baris, dilewati, contoh_lewat = validasi_sls.baca_master_impor(
        jalur, jalur_hirarki
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


def muat_env(jalur: str) -> None:
    """Muat berkas environment tanpa merusak nilai JSON di dalamnya.

    Sama seperti ``scripts/backfill_rekap_subsls.py``: ``source`` di bash
    membuang tanda kutip di dalam nilai, sehingga ``CORS_ORIGINS=[...]``
    ditolak pydantic-settings. Variabel yang sudah ada tidak ditimpa.
    """
    from dotenv import dotenv_values

    for kunci, nilai in dotenv_values(jalur).items():
        if nilai is not None and kunci not in os.environ:
            os.environ[kunci] = nilai


def utama(argv: list[str] | None = None) -> int:
    """Titik masuk CLI; kembalikan kode keluar proses."""
    from app.config import get_settings
    from app.db import get_sessionmaker

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=None,
        help="Berkas environment server, mis. /etc/pointse/pointse.env",
    )
    parser.add_argument(
        "--sumber",
        default=None,
        help="Folder akar master per kab atau berkas .zip (default: dir_master_sls_2026_s1)",
    )
    parser.add_argument(
        "--ekstrak-ke",
        default=None,
        help="Folder tujuan ekstraksi bila --sumber berupa .zip",
    )
    parser.add_argument(
        "--tanpa-db",
        action="store_true",
        help="Hanya ekstrak dan verifikasi berkas Excel tanpa menulis ke database",
    )
    parser.add_argument("--kdkab", default=None, help="Hanya satu kab, mis. 3312")
    args = parser.parse_args(argv)

    if args.env_file:
        muat_env(args.env_file)
    setelan = get_settings()
    sumber_awal = (
        Path(args.sumber) if args.sumber else Path(setelan.dir_master_sls_2026_s1)
    )
    ekstrak_ke = Path(args.ekstrak_ke) if args.ekstrak_ke else None

    from app import validasi_sls

    gagal = 0
    with siapkan_akar_sumber(sumber_awal, ekstrak_ke=ekstrak_ke, hanya=args.kdkab) as akar:
        daftar_kode = daftar_kabupaten(akar, args.kdkab)
        if not daftar_kode:
            print(f"tidak ada folder kabupaten di: {akar}", file=sys.stderr)
            return 1
        if args.tanpa_db:
            for kode in daftar_kode:
                try:
                    jalur, jalur_hirarki = validasi_sls.jalur_master(akar, kode)
                    if not jalur.is_file():
                        raise FileNotFoundError(f"master tidak ditemukan: {jalur}")
                    pasangan, _, dilewati, contoh_lewat = validasi_sls.baca_master_impor(
                        jalur, jalur_hirarki
                    )
                except (FileNotFoundError, ValueError, OSError) as galat:
                    print(f"LEWAT {kode}: {galat}", file=sys.stderr)
                    gagal += 1
                    continue
                contoh = (
                    f" contoh: {', '.join(str(x) for x in contoh_lewat)}"
                    if contoh_lewat
                    else ""
                )
                print(
                    f"VERIFIKASI {kode}: {len(pasangan)} pasangan "
                    f"({dilewati} baris dilewati{contoh})"
                )
            return 1 if gagal else 0

        sesi_pabrik = get_sessionmaker()
        with sesi_pabrik() as sesi:
            for kode in daftar_kode:
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
    return 1 if gagal else 0


if __name__ == "__main__":
    raise SystemExit(utama())
