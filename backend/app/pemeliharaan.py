"""Pemeliharaan ``titik_hasil`` di luar jalur job.

Job sukses **tidak** lagi memangkas apa pun: transaksi sukses hanya menulis
rekap, status, dan ``detail_tersedia``. Perampingan dikerjakan di sini supaya

- transaksi job tetap pendek (dua worker tidak saling menunggu kunci baris --
  MySQL ``1205``),
- kegagalan kerja bersih-bersih tidak pernah membatalkan job user.

Dua pekerjaan yang dilakukan:

1. **Run lama** (selain baseline dan sukses terakhir per kabupaten/kota+tipe):
   ``detail_tersedia`` diset 0 lebih dulu, baru barisnya dihapus per batch.
2. **Run yang disimpan**: buang baris titik yang tidak perlu perhatian
   (``perlu_perhatian``), sekali saja per run (penanda ``runs.titik_ramping``).

Semua langkah idempoten: aman dijalankan berulang, dan kalau gagal (mis. database
sibuk) cukup dicoba lagi pada putaran berikutnya.

Contoh dari folder ``backend``::

    .venv/bin/python -m app.pemeliharaan --sekali
    .venv/bin/python -m app.pemeliharaan --sekali --batas 100 --ukuran-batch 2000
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.models import STATUS_SUKSES, Run, TitikHasil
from app.rekap import perlu_perhatian

logger = logging.getLogger(__name__)

#: Baris dihapus per statement (kunci baris tidak ditahan lama).
UKURAN_BATCH = 5000

#: Jumlah run diproses per putaran (membagi pekerjaan besar ke beberapa putaran).
BATAS_RUN = 50


@dataclass
class Ringkasan:
    """Hasil satu putaran pemeliharaan."""

    run_dipangkas: list[int] = field(default_factory=list)
    run_dirampingkan: list[int] = field(default_factory=list)
    baris_dihapus: int = 0
    berkas_dihapus: list[str] = field(default_factory=list)


class KunciPemeliharaan:
    """Kunci antar-proses supaya hanya satu pemeliharaan berjalan.

    Memakai ``fcntl.flock`` pada ``<DIR_UNGGAHAN>/.pemeliharaan.lock``; di
    Windows (lingkungan tes) kunci dilewati karena tidak ada ``fcntl``.
    """

    def __init__(self, akar: str | Path) -> None:
        self.jalur = Path(akar) / ".pemeliharaan.lock"
        self.berkas: Any = None

    def ambil(self) -> bool:
        try:
            import fcntl
        except ImportError:  # pragma: no cover - hanya Windows
            return True
        self.jalur.parent.mkdir(parents=True, exist_ok=True)
        berkas = self.jalur.open("w")
        try:
            fcntl.flock(berkas, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            berkas.close()
            return False
        self.berkas = berkas
        return True

    def lepas(self) -> None:
        if self.berkas is None:
            return
        try:
            import fcntl

            fcntl.flock(self.berkas, fcntl.LOCK_UN)
        except (ImportError, OSError):  # pragma: no cover - hanya Windows
            pass
        self.berkas.close()
        self.berkas = None


def _hapus_baris(
    sesi: Session,
    run_id: int,
    syarat: object | None,
    ukuran_batch: int,
) -> int:
    """Hapus baris satu run per batch ``urut``; kembalikan jumlah baris.

    ``syarat`` = ``None`` berarti semua baris run itu (dipakai untuk run lama).
    """
    jumlah = 0
    while True:
        kueri = select(TitikHasil.urut).where(TitikHasil.run_id == run_id)
        if syarat is not None:
            kueri = kueri.where(syarat)
        urut = list(sesi.scalars(kueri.order_by(TitikHasil.urut).limit(ukuran_batch)))
        if not urut:
            break
        sesi.execute(
            delete(TitikHasil).where(
                TitikHasil.run_id == run_id, TitikHasil.urut.in_(urut)
            )
        )
        sesi.commit()
        jumlah += len(urut)
        if len(urut) < ukuran_batch:
            break
    return jumlah


def rampingkan_run(sesi: Session, run_id: int, ukuran_batch: int = UKURAN_BATCH) -> int:
    """Buang titik yang tidak perlu perhatian dari run yang disimpan."""
    jumlah = _hapus_baris(sesi, run_id, ~perlu_perhatian(), ukuran_batch)
    sesi.execute(
        update(Run)
        .where(Run.id == run_id)
        .values(titik_ramping=1, detail_tersedia=1)
    )
    sesi.commit()
    return jumlah


def pangkas_run(sesi: Session, run_id: int, ukuran_batch: int = UKURAN_BATCH) -> int:
    """Hapus seluruh baris run lama; tandai detail tidak tersedia lebih dulu."""
    sesi.execute(update(Run).where(Run.id == run_id).values(detail_tersedia=0))
    sesi.commit()
    return _hapus_baris(sesi, run_id, None, ukuran_batch)


def kelompok_sukses(sesi: Session) -> list[tuple[str, str, str]]:
    """Daftar ``(kdprov, kdkab, tipe)`` yang punya run sukses."""
    return [
        (str(kdprov), str(kdkab), str(tipe))
        for kdprov, kdkab, tipe in sesi.execute(
            select(Run.kdprov, Run.kdkab, Run.tipe)
            .where(Run.status == STATUS_SUKSES)
            .distinct()
            .order_by(Run.kdprov, Run.kdkab, Run.tipe)
        )
    ]


def jalankan(
    sesi: Session,
    batas: int = BATAS_RUN,
    ukuran_batch: int = UKURAN_BATCH,
) -> Ringkasan:
    """Satu putaran pemeliharaan (tanpa kunci; lihat :func:`jalankan_pemeliharaan`)."""
    ringkasan = Ringkasan()
    sisa = max(0, batas)

    for kdprov, kdkab, tipe in kelompok_sukses(sesi):
        if sisa <= 0:
            break
        ids = list(
            sesi.scalars(
                select(Run.id)
                .where(
                    Run.kdprov == kdprov,
                    Run.kdkab == kdkab,
                    Run.tipe == tipe,
                    Run.status == STATUS_SUKSES,
                    # Run yang detailnya sudah dipangkas tidak dihitung lagi,
                    # supaya putaran berikutnya tidak mengulang pekerjaan sama.
                    Run.detail_tersedia == 1,
                )
                .order_by(Run.id)
            )
        )
        if not ids:
            continue
        disimpan = {ids[0], ids[-1]}
        buang = [satu for satu in ids if satu not in disimpan]

        for run_id in buang:
            if sisa <= 0:
                break
            ringkasan.baris_dihapus += pangkas_run(sesi, run_id, ukuran_batch)
            ringkasan.run_dipangkas.append(run_id)
            sisa -= 1

        for run_id in sorted(disimpan):
            if sisa <= 0:
                break
            sudah = sesi.scalar(
                select(Run.titik_ramping).where(Run.id == run_id)
            )
            if sudah:
                continue
            ringkasan.baris_dihapus += rampingkan_run(sesi, run_id, ukuran_batch)
            ringkasan.run_dirampingkan.append(run_id)
            sisa -= 1

    return ringkasan


def jalankan_pemeliharaan(
    setelan: Settings | None = None,
    batas: int = BATAS_RUN,
    ukuran_batch: int = UKURAN_BATCH,
    sesi_pabrik: sessionmaker[Session] | None = None,
) -> Ringkasan | None:
    """Jalankan pemeliharaan dengan kunci; ``None`` bila proses lain sedang jalan."""
    setelan = setelan or get_settings()
    sesi_pabrik = sesi_pabrik or get_sessionmaker()
    kunci = KunciPemeliharaan(setelan.dir_unggahan)
    if not kunci.ambil():
        logger.info("pemeliharaan dilewati: proses lain sedang memangkas")
        return None
    try:
        with sesi_pabrik() as sesi:
            ringkasan = jalankan(sesi, batas=batas, ukuran_batch=ukuran_batch)
        # Berkas mentah: hapus folder run yang dipangkas, atau (bila disk menipis)
        # run tertua yang berkasnya boleh dibuang.
        from app.worker import pangkas_berkas

        with sesi_pabrik() as sesi:
            ringkasan.berkas_dihapus = pangkas_berkas(
                sesi,
                ringkasan.run_dipangkas,
                Path(setelan.dir_unggahan),
                setelan,
            )
        return ringkasan
    finally:
        kunci.lepas()


def utama(argv: list[str] | None = None) -> int:
    """Titik masuk CLI ``python -m app.pemeliharaan``."""
    pengurai = argparse.ArgumentParser(
        prog="python -m app.pemeliharaan",
        description="Rapikan titik_hasil di luar jalur job.",
    )
    pengurai.add_argument(
        "--sekali",
        action="store_true",
        help="jalankan satu putaran lalu keluar (untuk cron)",
    )
    pengurai.add_argument(
        "--batas",
        type=int,
        default=BATAS_RUN,
        help=f"jumlah run diproses per putaran (default {BATAS_RUN})",
    )
    pengurai.add_argument(
        "--ukuran-batch",
        type=int,
        default=UKURAN_BATCH,
        help=f"baris dihapus per statement (default {UKURAN_BATCH})",
    )
    argumen = pengurai.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    ringkasan = jalankan_pemeliharaan(
        batas=argumen.batas, ukuran_batch=argumen.ukuran_batch
    )
    if ringkasan is None:
        print("Pemeliharaan dilewati: proses lain sedang memangkas.")
        return 0
    print(
        f"Run dipangkas: {len(ringkasan.run_dipangkas)} "
        f"{ringkasan.run_dipangkas}\n"
        f"Run dirampingkan: {len(ringkasan.run_dirampingkan)} "
        f"{ringkasan.run_dirampingkan}\n"
        f"Baris dihapus: {ringkasan.baris_dihapus}\n"
        f"Berkas dihapus: {ringkasan.berkas_dihapus or 'tidak ada'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(utama())
