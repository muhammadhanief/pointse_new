"""Worker pemroses job Proses A/B (T3).

Aturan yang dipenuhi modul ini:

- job diambil dengan ``SELECT ... FOR UPDATE SKIP LOCKED`` (MySQL 8) supaya aman
  dijalankan oleh beberapa worker sekaligus;
- hanya satu job aktif per (kdkab, tipe): job yang (kdkab, tipe)-nya sedang
  berstatus ``jalan`` dilewati; kalau ada beberapa job antre untuk (kdkab, tipe)
  yang sama, yang **terbaru** dikerjakan dan sisanya ditandai ``digantikan``;
- dimensi wilayah di-upsert dari peta yang diunggah (``app.wilayah``), lalu
  ``titik_hasil`` menyimpan ``wilayah_asal_id``/``wilayah_edit_id`` saja;
- hasil disimpan ke ``titik_hasil`` per batch :data:`UKURAN_BATCH` (10.000) baris,
  dan progres (``runs.jumlah_baris``) diperbarui tiap batch;
- setelah sukses, rekap per SubSLS (dasar ``tugas`` dan ``posisi``) dihitung
  dengan query GROUP BY dan disimpan sebagai snapshot di ``rekap_subsls``;
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
    Float,
    Integer,
    Numeric,
    Select,
    SmallInteger,
    and_,
    case,
    delete,
    func,
    insert,
    literal,
    or_,
    select,
    update,
)
from sqlalchemy.orm import Session, aliased, sessionmaker

from app import wilayah
from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    STATUS_DIGANTIKAN,
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    RekapSubsls,
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


def _kasus(syarat: object) -> object:
    """``CASE WHEN syarat THEN 1 ELSE 0 END`` portabel (MySQL & SQLite)."""
    return case((syarat, 1), else_=0)


def _jumlah_kasus(syarat: object) -> object:
    """``SUM(CASE WHEN syarat THEN 1 ELSE 0 END)``, 0 kalau tidak ada baris."""
    return func.coalesce(func.sum(_kasus(syarat)), 0)


def _kolom_hitungan() -> tuple[object, ...]:
    """Kolom hitungan rekap (indikator progres PRD §5), urut seperti ``KOLOM_REKAP``.

    ``flag_edit_atr_repair`` NULL (Proses A tidak punya kolom itu) dianggap 0, jadi
    titik ``flag_repair`` = 0 pada Proses A masuk ``benar_awal``.
    """
    tanpa_tindakan = or_(
        TitikHasil.flag_edit_atr_repair.is_(None), TitikHasil.flag_edit_atr_repair == 0
    )
    ditindak = and_(TitikHasil.flag_repair == 0, TitikHasil.flag_edit_atr_repair == 1)
    tak_masuk_poligon = and_(
        TitikHasil.wilayah_asal_id.is_(None), TitikHasil.wilayah_edit_id.is_(None)
    )
    return (
        func.count(),
        _jumlah_kasus(TitikHasil.flag_repair == 1),
        _jumlah_kasus(and_(ditindak, TitikHasil.flag_repair_initial == 0)),
        _jumlah_kasus(and_(ditindak, TitikHasil.flag_repair_initial == 1)),
        _jumlah_kasus(and_(TitikHasil.flag_repair == 0, tanpa_tindakan)),
        _jumlah_kasus(TitikHasil.flag_position == 1),
        _jumlah_kasus(tak_masuk_poligon),
    )


#: Kolom tujuan ``rekap_subsls`` yang diisi dari :func:`_kolom_hitungan`.
KOLOM_REKAP: list[str] = [
    "run_id",
    "wilayah_id",
    "dasar",
    "jumlah",
    "belum",
    "ditindak_posisi_benar",
    "ditindak_posisi_salah",
    "benar_awal",
    "digeser",
    "tanpa_wilayah",
]


def simpan_rekap(sesi: Session, run: Run) -> None:
    """Simpan snapshot rekap per SubSLS untuk dasar ``tugas`` dan ``posisi``.

    Dua-duanya dihitung dengan satu query GROUP BY (PRD §7: rekap dihitung lewat
    query, bukan di Python). Dasar ``tugas`` memakai ``level_6_full_code`` titik
    (wilayah penugasan), dasar ``posisi`` memakai wilayah hasil join peta
    (``wilayah_edit_id`` bila ada, kalau tidak ``wilayah_asal_id``).

    Titik yang tidak bisa dipetakan ke wilayah pada dasar itu dihitung pada baris
    ``wilayah_id`` NULL -- kategori "(tanpa wilayah)" -- supaya foreign key tidak
    pernah gagal dan jumlah tiap dasar tetap sama dengan ``runs.jumlah_baris``:
    dasar ``tugas`` join-nya dibiarkan LEFT (``level_6_full_code`` kosong atau tidak
    ada di tabel ``wilayah``), dasar ``posisi`` tidak disaring (titik di luar semua
    poligon).
    """
    sesi.execute(delete(RekapSubsls).where(RekapSubsls.run_id == run.id))

    hitungan = _kolom_hitungan()
    tugas = (
        select(literal(run.id), Wilayah.id, literal(DASAR_TUGAS), *hitungan)
        .select_from(TitikHasil)
        .join(Wilayah, Wilayah.idsubsls == TitikHasil.level_6_full_code, isouter=True)
        .where(TitikHasil.run_id == run.id)
        .group_by(Wilayah.id)
    )
    sesi.execute(insert(RekapSubsls).from_select(KOLOM_REKAP, tugas))

    posisi = func.coalesce(TitikHasil.wilayah_edit_id, TitikHasil.wilayah_asal_id)
    dasar_posisi = (
        select(literal(run.id), posisi, literal(DASAR_POSISI), *hitungan)
        .where(TitikHasil.run_id == run.id)
        .group_by(posisi)
    )
    sesi.execute(insert(RekapSubsls).from_select(KOLOM_REKAP, dasar_posisi))
    sesi.commit()


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


def gantikan_hasil_lama(sesi: Session, run: Run) -> None:
    """Buang ``titik_hasil`` job lain untuk (kdkab, tipe) yang sama.

    Aturan "hasil lama digantikan" hanya menyangkut isi ``titik_hasil``: baris
    ``runs`` job lama **tetap ada** (statusnya jadi ``digantikan``) dan snapshot
    ``rekap_subsls``-nya sengaja dibiarkan supaya riwayat rekap masih bisa
    dibandingkan.
    """
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
            sesi.execute(delete(RekapSubsls).where(RekapSubsls.run_id == run_id))
            sesi.commit()

            titik, peta = baca_masukan(run)
            # Dimensi wilayah di-upsert dari peta (nama wilayah hanya di sini).
            wilayah.upsert(sesi, wilayah.baris_dari_peta(peta))
            sesi.commit()

            hasil = jalankan_proses(run, titik, peta)
            id_wilayah = wilayah.peta_id(sesi, kode_hasil(hasil))
            sesi.commit()

            jumlah = simpan_hasil(sesi, run, hasil, id_wilayah)
            simpan_rekap(sesi, run)

            run.jumlah_baris = jumlah
            run.jumlah_tanpa_wilayah = hitung_tanpa_wilayah(sesi, run_id)
            run.status = STATUS_SUKSES
            run.finished_at = sekarang()
            sesi.commit()
            gantikan_hasil_lama(sesi, run)
        logger.info("job %s sukses: %s baris", run_id, jumlah)
    except Exception as galat:  # noqa: BLE001 - pesan apa pun dicatat di runs.pesan
        logger.exception("job %s gagal", run_id)
        with sesi_pabrik() as sesi:
            sesi.execute(delete(TitikHasil).where(TitikHasil.run_id == run_id))
            sesi.execute(delete(RekapSubsls).where(RekapSubsls.run_id == run_id))
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
