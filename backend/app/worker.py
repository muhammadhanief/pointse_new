"""Worker pemroses job Proses A/B (T3).

Aturan yang dipenuhi modul ini:

- job diambil dengan ``SELECT ... FOR UPDATE SKIP LOCKED`` (MySQL 8) supaya aman
  dijalankan oleh beberapa worker sekaligus;
- hanya satu job aktif per (kdkab, tipe): job yang (kdkab, tipe)-nya sedang
  berstatus ``jalan`` dilewati; kalau ada beberapa job antre untuk (kdkab, tipe)
  yang sama, yang **terbaru** dikerjakan dan sisanya ditandai ``digantikan``;
- hasil disimpan ke ``titik_hasil`` per batch :data:`UKURAN_BATCH` (10.000) baris,
  dan progres (``runs.jumlah_baris``) diperbarui tiap batch;
- job gagal: hasil separuh dibuang, status ``gagal``, dan pesan galat dicatat.

Jalankan sebagai proses terpisah::

    .venv\\Scripts\\python.exe -m app.worker

Jumlah worker bersamaan diatur ``MAX_WORKERS`` (default 1, lihat ``.env``).
Dengan lebih dari satu worker, dua job berbeda kabupaten/tipe jalan paralel; kalau
dua job dengan (kdkab, tipe) yang sama sempat terklaim bersamaan (jendela balapan
sempit pada ``SKIP LOCKED``), hasilnya tetap konsisten karena job yang selesai
terakhir menggantikan hasil job yang lain.
"""

from __future__ import annotations

import logging
import signal
import threading
from typing import Any

import geopandas as gpd
import pandas as pd
from sqlalchemy import (
    BigInteger,
    Float,
    Integer,
    Numeric,
    Select,
    SmallInteger,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.orm import Session, aliased, sessionmaker

from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.models import (
    STATUS_DIGANTIKAN,
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    Run,
    TitikHasil,
    sekarang,
)
from app.proses_a import pastikan_crs4326, proses_a
from app.proses_b import proses_b

logger = logging.getLogger("pointse.worker")

#: Hasil disimpan ke basis data per potongan sebesar ini (PRD §8).
UKURAN_BATCH = 10_000


def baca_masukan(run: Run) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Baca berkas titik dan peta job dari disk."""
    titik = gpd.read_file(run.berkas_input, layer=run.layer_input)
    peta = gpd.read_file(run.berkas_peta, layer=run.layer_peta)
    return titik, peta


def jalankan_proses(
    run: Run, titik: gpd.GeoDataFrame, peta: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Panggil Proses A atau Proses B sesuai tipe job."""
    if run.tipe == TIPE_A:
        return proses_a(titik, peta)
    # Model Proses B tidak punya node reproject, jadi CRS disiapkan di lapisan
    # ini (lihat catatan di app/proses_b.py).
    return proses_b(pastikan_crs4326(titik, "titik"), pastikan_crs4326(peta, "peta"))


def siapkan_baris(potongan: pd.DataFrame, run_id: int) -> list[dict[str, Any]]:
    """Ubah potongan hasil jadi baris siap-insert, tipe mengikuti model ORM."""
    data: dict[str, list[Any]] = {"run_id": [run_id] * len(potongan)}

    for kolom in TitikHasil.__table__.columns:
        if kolom.name in ("id", "run_id"):
            continue
        if kolom.name in potongan.columns:
            seri = potongan[kolom.name]
        else:
            seri = pd.Series([None] * len(potongan))

        if isinstance(kolom.type, (SmallInteger, Integer, BigInteger)):
            seri = pd.to_numeric(seri, errors="coerce").astype("Int64")
        elif isinstance(kolom.type, (Float, Numeric)):
            seri = pd.to_numeric(seri, errors="coerce")
        else:
            seri = seri.astype("string")

        # pd.NA/NaN -> None supaya tersimpan sebagai NULL di MySQL.
        data[kolom.name] = list(seri.astype(object).where(seri.notna(), None))

    return [dict(zip(data, nilai)) for nilai in zip(*data.values())]


def simpan_hasil(sesi: Session, run: Run, hasil: gpd.GeoDataFrame) -> int:
    """Simpan hasil ke ``titik_hasil`` per batch; kembalikan jumlah baris."""
    jumlah = 0
    for mulai in range(0, len(hasil), UKURAN_BATCH):
        potongan = hasil.iloc[mulai : mulai + UKURAN_BATCH]
        sesi.execute(insert(TitikHasil), siapkan_baris(potongan, run.id))
        jumlah += len(potongan)
        # Progres bisa dipantau dari runs.jumlah_baris selama job jalan.
        run.jumlah_baris = jumlah
        sesi.commit()

    if len(hasil) == 0:
        run.jumlah_baris = 0
    return jumlah


def gantikan_hasil_lama(sesi: Session, run: Run) -> None:
    """Buang hasil job lain untuk (kdkab, tipe) yang sama (aturan: hasil lama digantikan)."""
    lain = list(
        sesi.scalars(
            select(Run.id).where(
                Run.kdkab == run.kdkab, Run.tipe == run.tipe, Run.id != run.id
            )
        )
    )
    if not lain:
        return

    sesi.execute(delete(TitikHasil).where(TitikHasil.run_id.in_(lain)))
    sesi.execute(
        update(Run)
        .where(Run.id.in_(lain), Run.status == STATUS_SUKSES)
        .values(status=STATUS_DIGANTIKAN)
    )
    sesi.commit()


def kueri_klaim() -> Select[tuple[Run]]:
    """Kueri pengambilan job: ``FOR UPDATE SKIP LOCKED`` (MySQL 8) + satu job per (kdkab, tipe).

    Diurutkan dari id terbesar supaya kalau ada beberapa job antre untuk
    (kdkab, tipe) yang sama, yang **terbaru** yang dikerjakan.
    """
    lain = aliased(Run)
    sedang_jalan = (
        select(lain.id)
        .where(lain.status == STATUS_JALAN, lain.tipe == Run.tipe, lain.kdkab == Run.kdkab)
        .exists()
    )
    return (
        select(Run)
        .where(Run.status == STATUS_MENUNGGU, ~sedang_jalan)
        .order_by(Run.id.desc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def klaim_job(sesi: Session) -> Run | None:
    """Ambil satu job ``menunggu`` dengan ``FOR UPDATE SKIP LOCKED`` (MySQL 8).

    Job yang (kdkab, tipe)-nya sedang dikerjakan worker lain dilewati, begitu pula
    job antre lain untuk (kdkab, tipe) itu (ditandai ``digantikan``).
    """
    run = sesi.execute(kueri_klaim()).scalar_one_or_none()
    if run is None:
        return None

    run.status = STATUS_JALAN
    run.started_at = sekarang()
    run.pesan = None
    sesi.execute(
        update(Run)
        .where(
            Run.status == STATUS_MENUNGGU,
            Run.tipe == run.tipe,
            Run.kdkab == run.kdkab,
            Run.id != run.id,
        )
        .values(status=STATUS_DIGANTIKAN, pesan="digantikan job yang lebih baru")
    )
    sesi.commit()
    return run


def proses_satu_job(sesi_pabrik: sessionmaker[Session] | None = None) -> bool:
    """Ambil lalu jalankan satu job; ``False`` kalau tidak ada job antre."""
    sesi_pabrik = sesi_pabrik or get_sessionmaker()

    with sesi_pabrik() as sesi:
        run = klaim_job(sesi)
        if run is None:
            return False
        run_id, tipe, kdkab = run.id, run.tipe, run.kdkab

    logger.info("job %s (%s, kdkab %s) mulai dikerjakan", run_id, tipe, kdkab)
    try:
        with sesi_pabrik() as sesi:
            run = sesi.get(Run, run_id)
            if run is None:  # job dihapus saat sedang jalan
                logger.warning("job %s hilang saat dikerjakan", run_id)
                return True

            # Bersihkan sisa hasil percobaan sebelumnya (bila job diulang).
            sesi.execute(delete(TitikHasil).where(TitikHasil.run_id == run_id))
            sesi.commit()

            titik, peta = baca_masukan(run)
            hasil = jalankan_proses(run, titik, peta)
            jumlah = simpan_hasil(sesi, run, hasil)

            run.jumlah_baris = jumlah
            run.status = STATUS_SUKSES
            run.finished_at = sekarang()
            sesi.commit()
            gantikan_hasil_lama(sesi, run)
        logger.info("job %s sukses: %s baris", run_id, jumlah)
    except Exception as galat:  # noqa: BLE001 - pesan apa pun dicatat di runs.pesan
        logger.exception("job %s gagal", run_id)
        with sesi_pabrik() as sesi:
            sesi.execute(delete(TitikHasil).where(TitikHasil.run_id == run_id))
            sesi.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    status=STATUS_GAGAL,
                    pesan=str(galat)[:2000],
                    finished_at=sekarang(),
                )
            )
            sesi.commit()
    return True


def jalankan_worker(
    penghenti: threading.Event,
    sesi_pabrik: sessionmaker[Session] | None = None,
    setelan: Settings | None = None,
) -> None:
    """Loop worker: kerjakan job sampai ``penghenti`` diset."""
    setelan = setelan or get_settings()
    while not penghenti.is_set():
        try:
            ada_job = proses_satu_job(sesi_pabrik)
        except Exception:  # noqa: BLE001 - worker jangan mati karena satu galat
            logger.exception("worker gagal mengambil job")
            ada_job = False
        if not ada_job:
            penghenti.wait(setelan.interval_polling)
    logger.info("worker berhenti")


def mulai_worker(
    setelan: Settings | None = None, penghenti: threading.Event | None = None
) -> tuple[list[threading.Thread], threading.Event]:
    """Nyalakan ``MAX_WORKERS`` thread worker; kembalikan (thread, penghenti)."""
    setelan = setelan or get_settings()
    penghenti = penghenti or threading.Event()
    sesi_pabrik = get_sessionmaker()

    benang = [
        threading.Thread(
            target=jalankan_worker,
            args=(penghenti, sesi_pabrik, setelan),
            name=f"pointse-worker-{nomor + 1}",
            daemon=True,
        )
        for nomor in range(max(1, setelan.max_workers))
    ]
    for satu in benang:
        satu.start()
    logger.info("%s worker dinyalakan", len(benang))
    return benang, penghenti


def main() -> None:
    """Titik masuk worker terpisah: ``python -m app.worker``."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    setelan = get_settings()
    penghenti = threading.Event()

    def berhenti(_nomor: int, _frame: object) -> None:
        logger.info("sinyal berhenti diterima; menunggu job selesai")
        penghenti.set()

    signal.signal(signal.SIGINT, berhenti)
    signal.signal(signal.SIGTERM, berhenti)

    benang, _ = mulai_worker(setelan, penghenti)
    for satu in benang:
        satu.join()


if __name__ == "__main__":
    main()
