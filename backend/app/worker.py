"""Worker pemroses job Proses A/B (T3).

Aturan yang dipenuhi modul ini:

- job diambil dengan ``SELECT ... FOR UPDATE SKIP LOCKED`` (MySQL 8) supaya aman
  dijalankan oleh beberapa worker sekaligus;
- hanya satu job aktif per (kdprov, kdkab, tipe): job yang (kdprov, kdkab, tipe)-nya
  sedang berstatus ``jalan`` dilewati; kalau ada beberapa job antre untuk
  (kdprov, kdkab, tipe) yang sama, semuanya tetap dikerjakan **berurutan** (yang
  paling lama dulu) dan tidak ada job yang ditandai batal/digantikan;
- dimensi wilayah di-upsert dari peta yang diunggah (``app.wilayah``), lalu
  ``titik_hasil`` menyimpan ``wilayah_asal_id``/``wilayah_edit_id`` saja;
- hasil disimpan ke ``titik_hasil`` per batch :data:`UKURAN_BATCH` (10.000) baris,
  dan progres (``runs.jumlah_baris``) diperbarui tiap batch;
- setelah sukses, satu transaksi: rekap per desa dan kabupaten/kota dihitung dengan
  query GROUP BY (``app.rekap``), ``titik_hasil`` dirampingkan -- hanya titik yang
  perlu perhatian dan hanya run baseline + sukses terakhir per kabupaten/tipe --
  lalu status jadi ``sukses``;
- berkas mentah run yang ``titik_hasil``-nya dipangkas ikut dihapus dari disk
  (hanya baseline dan yang terbaru yang disimpan);
- job gagal: hasil separuh dibuang, status ``gagal``, dan pesan galat dicatat.

Jalankan sebagai proses terpisah::

    .venv\\Scripts\\python.exe -m app.worker

Jumlah worker bersamaan diatur ``MAX_WORKERS`` (default 1, lihat ``.env``).
Dengan lebih dari satu worker, dua job berbeda kabupaten/tipe jalan paralel; kalau
dua job dengan (kdprov, kdkab, tipe) yang sama sempat terklaim bersamaan (jendela
balapan sempit pada ``SKIP LOCKED``), hasilnya tetap konsisten karena keduanya
dikerjakan berurutan dan yang selesai terakhir menyimpan datanya sebagai "sukses
terakhir".
"""

from __future__ import annotations

import logging
import shutil
import signal
import threading
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from sqlalchemy import (
    Float,
    Integer,
    Numeric,
    Select,
    SmallInteger,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.orm import Session, aliased, sessionmaker

from app import rekap as modul_rekap
from app import wilayah
from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.models import (
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    RekapDesa,
    RekapKabupaten,
    Run,
    TitikHasil,
    Wilayah,
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


def kode_hasil(hasil: gpd.GeoDataFrame) -> set[str]:
    """Kode SubSLS yang dipakai hasil (agar bisa dimuat dari tabel ``wilayah``)."""
    kode: set[str] = set()
    for kolom in ("level_6_full_code", "idsubsls_origin", "idsubsls_edited"):
        if kolom in hasil.columns:
            seri = hasil[kolom].dropna().astype("string").str.strip()
            kode.update(nilai for nilai in seri.unique() if nilai)
    return kode


def tambah_kolom_wilayah(
    hasil: gpd.GeoDataFrame, id_wilayah: dict[str, int]
) -> gpd.GeoDataFrame:
    """Tambahkan ``wilayah_asal_id``/``wilayah_edit_id`` dari kode hasil proses."""
    keluaran = hasil.copy()
    for kolom_db, kolom_proses in (
        ("wilayah_asal_id", "idsubsls_origin"),
        ("wilayah_edit_id", "idsubsls_edited"),
    ):
        if kolom_proses in hasil.columns:
            seri = hasil[kolom_proses].map(lambda kode: id_wilayah.get(wilayah.bersih(kode)))
        else:  # Proses A tidak punya idsubsls_edited
            seri = pd.Series([None] * len(hasil), index=hasil.index)
        keluaran[kolom_db] = seri.astype("Int64")
    return keluaran


def siapkan_baris(
    potongan: pd.DataFrame, run_id: int, urut_awal: int = 0
) -> list[dict[str, Any]]:
    """Ubah potongan hasil jadi baris siap-insert, tipe mengikuti model ORM."""
    data: dict[str, list[Any]] = {
        "run_id": [run_id] * len(potongan),
        "urut": list(range(urut_awal, urut_awal + len(potongan))),
    }

    for kolom in TitikHasil.__table__.columns:
        if kolom.name in ("run_id", "urut"):
            continue
        if kolom.name in potongan.columns:
            seri = potongan[kolom.name]
        else:
            seri = pd.Series([None] * len(potongan), index=potongan.index)

        if isinstance(kolom.type, (SmallInteger, Integer)):
            seri = pd.to_numeric(seri, errors="coerce").astype("Int64")
        elif isinstance(kolom.type, (Float, Numeric)):
            seri = pd.to_numeric(seri, errors="coerce")
        else:
            seri = seri.astype("string")

        # pd.NA/NaN -> None supaya tersimpan sebagai NULL di MySQL.
        data[kolom.name] = list(seri.astype(object).where(seri.notna(), None))

    return [dict(zip(data, nilai)) for nilai in zip(*data.values())]


def simpan_hasil(
    sesi: Session, run: Run, hasil: gpd.GeoDataFrame, id_wilayah: dict[str, int]
) -> int:
    """Simpan hasil ke ``titik_hasil`` per batch; kembalikan jumlah baris."""
    siap = tambah_kolom_wilayah(hasil, id_wilayah)
    jumlah = 0
    for mulai in range(0, len(siap), UKURAN_BATCH):
        potongan = siap.iloc[mulai : mulai + UKURAN_BATCH]
        sesi.execute(insert(TitikHasil), siapkan_baris(potongan, run.id, urut_awal=mulai))
        jumlah += len(potongan)
        # Progres bisa dipantau dari runs.jumlah_baris selama job jalan.
        run.jumlah_baris = jumlah
        sesi.commit()

    if len(siap) == 0:
        run.jumlah_baris = 0
    return jumlah


def hitung_tanpa_wilayah(sesi: Session, run_id: int) -> int:
    """Jumlah titik hasil yang tidak masuk/jatuh di poligon wilkerstat mana pun."""
    return int(
        sesi.scalar(
            select(func.count())
            .select_from(TitikHasil)
            .where(
                TitikHasil.run_id == run_id,
                TitikHasil.wilayah_asal_id.is_(None),
                TitikHasil.wilayah_edit_id.is_(None),
            )
        )
        or 0
    )


def pangkas_berkas(sesi: Session, run_ids: list[int], akar: Path) -> list[str]:
    """Hapus folder berkas mentah run yang ``titik_hasil``-nya sudah dipangkas.

    Hanya folder di dalam ``akar`` (folder unggahan) yang dihapus, dan berkas run
    dengan status lain (``menunggu``/``jalan``/``gagal``) tidak pernah ikut karena
    :func:`app.rekap.pangkas_titik_hasil` hanya mengembalikan run sukses. Baris
    ``runs`` tetap menyimpan nama berkasnya sebagai riwayat.
    """
    if not run_ids:
        return []
    akar = akar.resolve()
    terhapus: list[str] = []
    for run in sesi.scalars(select(Run).where(Run.id.in_(run_ids))):
        for jalur in {
            Path(run.berkas_input).resolve().parent,
            Path(run.berkas_peta).resolve().parent,
        }:
            if jalur != akar and akar in jalur.parents and jalur.exists():
                shutil.rmtree(jalur, ignore_errors=True)
                terhapus.append(str(jalur))
    return terhapus


def kueri_klaim() -> Select[tuple[Run]]:
    """Kueri pengambilan job: ``FOR UPDATE SKIP LOCKED`` (MySQL 8) + satu job per kab/tipe.

    Satu job aktif per (kdprov, kdkab, tipe): job yang (kdprov, kdkab, tipe)-nya
    sedang berstatus ``jalan`` dilewati. Diurutkan dari id terkecil (urutan unggah)
    supaya job antre lama tetap dikerjakan **berurutan** dan tidak ada yang
    dibatalkan; run yang sukses terakhir jadi run dengan id terbesar.
    """
    lain = aliased(Run)
    sedang_jalan = (
        select(lain.id)
        .where(
            lain.status == STATUS_JALAN,
            lain.tipe == Run.tipe,
            lain.kdprov == Run.kdprov,
            lain.kdkab == Run.kdkab,
        )
        .exists()
    )
    return (
        select(Run)
        .where(Run.status == STATUS_MENUNGGU, ~sedang_jalan)
        .order_by(Run.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def klaim_job(sesi: Session) -> Run | None:
    """Ambil satu job ``menunggu`` dengan ``FOR UPDATE SKIP LOCKED`` (MySQL 8).

    Job yang (kdprov, kdkab, tipe)-nya sedang dikerjakan worker lain dilewati; job
    antre lain untuk kabupaten/tipe itu dibiarkan ``menunggu`` (dikerjakan
    berurutan, tidak ada yang ditandai batal).
    """
    run = sesi.execute(kueri_klaim()).scalar_one_or_none()
    if run is None:
        return None

    run.status = STATUS_JALAN
    run.started_at = sekarang()
    run.pesan = None
    sesi.commit()
    return run


def bersihkan_hasil(sesi: Session, run_id: int) -> None:
    """Buang sisa hasil/rekap satu job (job diulang atau gagal di tengah jalan)."""
    sesi.execute(delete(TitikHasil).where(TitikHasil.run_id == run_id))
    sesi.execute(delete(RekapDesa).where(RekapDesa.run_id == run_id))
    sesi.execute(delete(RekapKabupaten).where(RekapKabupaten.run_id == run_id))


def proses_satu_job(
    sesi_pabrik: sessionmaker[Session] | None = None, setelan: Settings | None = None
) -> bool:
    """Ambil lalu jalankan satu job; ``False`` kalau tidak ada job antre."""
    sesi_pabrik = sesi_pabrik or get_sessionmaker()
    setelan = setelan or get_settings()

    with sesi_pabrik() as sesi:
        run = klaim_job(sesi)
        if run is None:
            return False
        run_id, tipe, kdprov, kdkab = run.id, run.tipe, run.kdprov, run.kdkab

    logger.info("job %s (%s, %s/%s) mulai dikerjakan", run_id, tipe, kdprov, kdkab)
    buang: list[int] = []
    try:
        with sesi_pabrik() as sesi:
            run = sesi.get(Run, run_id)
            if run is None:  # job dihapus saat sedang jalan
                logger.warning("job %s hilang saat dikerjakan", run_id)
                return True

            # Bersihkan sisa hasil percobaan sebelumnya (bila job diulang).
            bersihkan_hasil(sesi, run_id)
            sesi.commit()

            titik, peta = baca_masukan(run)
            # Dimensi wilayah di-upsert dari peta (nama wilayah hanya di sini).
            wilayah.upsert(sesi, wilayah.baris_dari_peta(peta))
            sesi.commit()

            hasil = jalankan_proses(run, titik, peta)
            id_wilayah = wilayah.peta_id(sesi, kode_hasil(hasil))
            sesi.commit()

            # Semua titik disimpan dulu supaya rekap bisa dihitung lewat query
            # GROUP BY; sisanya dirampingkan di akhir (satu transaksi).
            jumlah = simpan_hasil(sesi, run, hasil, id_wilayah)
            modul_rekap.simpan_rekap(sesi, run)

            run.jumlah_baris = jumlah
            run.jumlah_tanpa_wilayah = hitung_tanpa_wilayah(sesi, run_id)
            run.status = STATUS_SUKSES
            run.finished_at = sekarang()
            # Satu transaksi: rekap + status sukses + pemangkasan titik_hasil.
            buang = modul_rekap.pangkas_titik_hasil(sesi, run)
            sesi.commit()
        logger.info(
            "job %s sukses: %s baris (titik_hasil run lain dipangkas: %s)",
            run_id,
            jumlah,
            buang or "tidak ada",
        )
        if buang:
            with sesi_pabrik() as sesi:
                terhapus = pangkas_berkas(sesi, buang, Path(setelan.dir_unggahan))
            logger.info("berkas mentah dihapus: %s", terhapus)
    except Exception as galat:  # noqa: BLE001 - pesan apa pun dicatat di runs.pesan
        logger.exception("job %s gagal", run_id)
        with sesi_pabrik() as sesi:
            bersihkan_hasil(sesi, run_id)
            sesi.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    status=STATUS_GAGAL,
                    detail_tersedia=0,
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
            ada_job = proses_satu_job(sesi_pabrik, setelan)
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
