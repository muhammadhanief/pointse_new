"""Tambahkan penjelasan pada pesan galat job lama yang sudah tersimpan.

Perbaikan :func:`app.worker.pesan_galat` hanya berlaku untuk job yang gagal
**setelah** worker diperbarui; pesan job lama masih berupa galat mentah. Skrip
ini menambahkan penjelasan penyebabnya (kolom wajib kosong, nilai terlalu
panjang, data ganda) di depan pesan lama tanpa menghapus teks mentahnya.

Contoh dari folder ``backend``::

    .venv/bin/python -m scripts.perbaiki_pesan              # pratinjau
    .venv/bin/python -m scripts.perbaiki_pesan --terapkan   # simpan

Prosesnya ringan: satu query ke tabel ``runs`` (ratusan baris) lalu olah teks
di memori, jadi biasanya selesai di bawah satu detik.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.models import Run
from app.worker import pesan_galat

#: Penanda yang dipakai :func:`app.worker.pesan_galat`; pesan yang sudah
#: memuatnya tidak diproses lagi supaya skrip aman dijalankan berulang.
PENANDA = "Pesan galat mentah:"

#: Batas panjang ``runs.pesan`` yang juga dipakai worker.
BATAS_PESAN = 2000


def perbaiki_pesan_lama(
    sesi: Session, terapkan: bool = False
) -> list[tuple[int, str]]:
    """Rapikan pesan galat lama; kembalikan daftar ``(run_id, pesan baru)``.

    ``terapkan=False`` hanya menghitung (pratinjau) tanpa menyimpan apa pun.
    """
    hasil: list[tuple[int, str]] = []
    for run in sesi.scalars(select(Run).where(Run.pesan.is_not(None))).all():
        lama = (run.pesan or "").strip()
        if not lama or PENANDA in lama:
            continue
        baru = pesan_galat(Exception(lama), run)[:BATAS_PESAN]
        if baru == lama:
            continue
        hasil.append((run.id, baru))
        if terapkan:
            run.pesan = baru
    if terapkan and hasil:
        sesi.commit()
    return hasil


def utama() -> int:
    """Titik masuk CLI."""
    pengurai = argparse.ArgumentParser(
        description="Tambahkan penjelasan pada pesan galat job lama."
    )
    pengurai.add_argument(
        "--terapkan",
        action="store_true",
        help="simpan perubahan (tanpa ini hanya pratinjau)",
    )
    pengurai.add_argument(
        "--contoh",
        type=int,
        default=10,
        help="jumlah pesan yang ditampilkan sebagai contoh (default 10)",
    )
    argumen = pengurai.parse_args()

    with get_sessionmaker()() as sesi:
        hasil = perbaiki_pesan_lama(sesi, terapkan=argumen.terapkan)

    kata = "diperbarui" if argumen.terapkan else "akan diperbarui"
    print(f"{len(hasil)} pesan galat {kata}.")
    for run_id, pesan in hasil[: argumen.contoh]:
        print(f"\n#{run_id}: {pesan[:400]}")
    if not argumen.terapkan and hasil:
        print("\nJalankan lagi dengan --terapkan untuk menyimpan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(utama())
