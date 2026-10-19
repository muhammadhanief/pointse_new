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

import argparse
import logging
import shutil
import signal
import threading
from datetime import timedelta
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
    bindparam,
    delete,
    func,
    insert,
    select,
    text,
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
from app.potongan import baca_potongan
from app.proses_a import pastikan_crs4326, proses_a, proses_a_potongan
from app.proses_b import proses_b, proses_b_potongan


logger = logging.getLogger("pointse.worker")

#: Hasil disimpan ke basis data per potongan sebesar ini (PRD §8).
UKURAN_BATCH = 10_000

#: Skala kunci urutan sementara: ``posisi_poligon * SKALA + nomor_urut_titik``.
#: Nomor titik per kabupaten < 1 miliar dan poligon < 1 juta (lihat PRD).
SKALA_URUT = 10**9
POSISI_TAK_COCOK = 10**6

#: Geseran sementara saat merapikan ``urut`` (harus di atas kunci mode potongan).
GESER_URUT = 10**16

#: Nama tabel sementara pemetaan urut (per koneksi basis data).
TABEL_URUT = "_pointse_urut_sementara"

#: Nama kunci advisory worker ``--once`` (MariaDB ``GET_LOCK``).
NAMA_KUNCI_WORKER = "pointse_worker_once"

#: Pesan untuk job ``jalan`` yang heartbeat-nya kedaluwarsa (server mati).
PESAN_TERHENTI = "proses terhenti, kemungkinan dimatikan server"


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
        run.heartbeat_at = sekarang()
        sesi.commit()

    if len(siap) == 0:
        run.jumlah_baris = 0
    return jumlah


def kunci_potongan(hasil: gpd.GeoDataFrame) -> list[int]:
    """Kunci urutan sementara untuk hasil satu potongan.

    Kuncinya meniru urutan keluaran :func:`app.proses_a.proses_a`/:func:`app.proses_b.proses_b`:
    ``posisi_poligon * SKALA_URUT + nomor_urut_titik``, dan titik yang tidak
    cocok memakai ``POSISI_TAK_COCOK`` (selalu di akhir). Nilainya unik per
    titik, jadi bisa dipakai sebagai kunci utama sementara dan untuk memilih
    baris yang bertahan pada ``assignment_id`` ganda.
    """
    posisi = pd.to_numeric(hasil["_posisi"], errors="coerce").fillna(POSISI_TAK_COCOK)
    urut = pd.to_numeric(hasil["_urut"], errors="coerce").fillna(0)
    return [
        int(nilai_posisi) * SKALA_URUT + int(nilai_urut)
        for nilai_posisi, nilai_urut in zip(posisi, urut)
    ]


def kunci_tersimpan(
    sesi: Session, run_id: int, daftar_id: list[str]
) -> dict[str, int]:
    """Kunci ``urut`` baris yang sudah tersimpan untuk ``assignment_id`` tertentu.

    Dipakai untuk dedup lintas potongan: baris yang baru hanya menggantikan
    baris lama bila kuncinya lebih kecil (lebih awal pada urutan hasil). Dicari
    per batch (pecahan 500 id) supaya perintah ``IN`` tidak terlalu panjang.
    """
    hasil: dict[str, int] = {}
    for mulai in range(0, len(daftar_id), 500):
        potongan = daftar_id[mulai : mulai + 500]
        for assignment_id, urut in sesi.execute(
            select(TitikHasil.assignment_id, TitikHasil.urut).where(
                TitikHasil.run_id == run_id,
                TitikHasil.assignment_id.in_(potongan),
            )
        ):
            hasil[str(assignment_id)] = int(urut)
    return hasil


def jumlah_tersimpan(sesi: Session, run_id: int) -> int:
    """Jumlah baris unik yang sudah ada di ``titik_hasil`` untuk satu run."""
    return int(
        sesi.scalar(
            select(func.count())
            .select_from(TitikHasil)
            .where(TitikHasil.run_id == run_id)
        )
        or 0
    )


def simpan_potongan(
    sesi: Session, run: Run, hasil: gpd.GeoDataFrame, id_wilayah: dict[str, int]
) -> None:
    """Simpan hasil satu potongan langsung ke ``titik_hasil`` per batch.

    ``assignment_id`` lintas potongan tidak di-upsert buta: kunci ``urut``
    baris lama dibaca dulu, lalu baris baru disisipkan atau menggantikan baris
    lama hanya kalau kuncinya lebih kecil. Cara ini portabel (MySQL & SQLite)
    dan menghasilkan pemenang yang sama dengan ``proses_a``/``proses_b``.
    """
    siap = tambah_kolom_wilayah(hasil, id_wilayah)
    kunci = kunci_potongan(siap)
    kolom_ganti = [
        kolom.name
        for kolom in TitikHasil.__table__.columns
        if kolom.name not in ("run_id", "assignment_id")
    ]

    for mulai in range(0, len(siap), UKURAN_BATCH):
        potongan = siap.iloc[mulai : mulai + UKURAN_BATCH]
        baris = siapkan_baris(potongan, run.id)
        for satu, nilai in zip(baris, kunci[mulai : mulai + UKURAN_BATCH]):
            satu["urut"] = nilai

        if baris:
            # Kunci naik di dalam satu batch; buang duplikat dalam batch dulu.
            unik: dict[str, dict[str, Any]] = {}
            for satu in baris:
                unik.setdefault(str(satu["assignment_id"]), satu)
            baris = list(unik.values())

            lama = kunci_tersimpan(sesi, run.id, [str(satu["assignment_id"]) for satu in baris])
            sisip = [
                satu
                for satu in baris
                if str(satu["assignment_id"]) not in lama
            ]
            ganti = [
                satu
                for satu in baris
                if str(satu["assignment_id"]) in lama
                and int(satu["urut"]) < lama[str(satu["assignment_id"])]
            ]
            if sisip:
                sesi.execute(insert(TitikHasil), sisip)
            if ganti:
                sesi.execute(
                    update(TitikHasil.__table__)
                    .where(
                        TitikHasil.__table__.c.run_id == bindparam("b_run_id"),
                        TitikHasil.__table__.c.assignment_id
                        == bindparam("b_assignment_id"),
                    )
                    .values({nama: bindparam(nama) for nama in kolom_ganti}),
                    [
                        {
                            **{nama: satu[nama] for nama in kolom_ganti},
                            "b_run_id": satu["run_id"],
                            "b_assignment_id": satu["assignment_id"],
                        }
                        for satu in ganti
                    ],
                )

        run.heartbeat_at = sekarang()
        run.jumlah_baris = jumlah_tersimpan(sesi, run.id)
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
        # Berkas input run A bisa menunjuk geotag master (permanen); jangan
        # menghapus foldernya. Folder peta tetap dipangkas.
        jalur_hapus = {Path(run.berkas_peta).resolve().parent}
        if run.geotag_master_id is None:
            jalur_hapus.add(Path(run.berkas_input).resolve().parent)
        for jalur in jalur_hapus:
            if jalur != akar and akar in jalur.parents and jalur.exists():
                shutil.rmtree(jalur, ignore_errors=True)
                terhapus.append(str(jalur))
    return terhapus


def proses_potongan(sesi: Session, run: Run, setelan: Settings) -> int:
    """Jalankan Proses A/B dengan titik dibaca per potongan (hemat memori).

    Peta tetap dibaca utuh (dipakai semua potongan), sedangkan titik dibaca
    ``PROSES_CHUNK_TITIK`` baris sekali lewat :func:`app.potongan.baca_potongan`.
    Hasil tiap potongan langsung disimpan ke ``titik_hasil`` per batch
    :data:`UKURAN_BATCH`; dedup ``assignment_id`` lintas potongan dikerjakan
    basis data (baris dengan kunci urut terkecil yang menang).
    """
    peta = gpd.read_file(run.berkas_peta, layer=run.layer_peta)
    if run.tipe != TIPE_A:
        # Model Proses B tidak punya node reproject; siapkan CRS di lapisan ini.
        peta = pastikan_crs4326(peta, "peta")
    wilayah.upsert(sesi, wilayah.baris_dari_peta(peta))
    run.heartbeat_at = sekarang()
    sesi.commit()

    id_wilayah: dict[str, int] = {}
    for urut_awal, titik_potongan in baca_potongan(
        run.berkas_input, run.layer_input, setelan.proses_chunk_titik
    ):
        if run.tipe == TIPE_A:
            hasil = proses_a_potongan(titik_potongan, peta, urut_awal)
        else:
            hasil = proses_b_potongan(
                pastikan_crs4326(titik_potongan, "titik"), peta, urut_awal
            )

        # Hanya kode yang belum pernah dimuat pada job ini yang ditanyakan.
        kode_baru = kode_hasil(hasil) - set(id_wilayah)
        if kode_baru:
            id_wilayah.update(wilayah.peta_id(sesi, kode_baru))

        simpan_potongan(sesi, run, hasil, id_wilayah)

    if run.jumlah_baris is None:
        run.jumlah_baris = 0
        sesi.commit()
    return int(run.jumlah_baris)


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
    run.heartbeat_at = sekarang()
    run.pesan = None
    sesi.commit()
    return run


def bersihkan_hasil(sesi: Session, run_id: int) -> None:
    """Buang sisa hasil/rekap satu job (job diulang atau gagal di tengah jalan)."""
    sesi.execute(delete(TitikHasil).where(TitikHasil.run_id == run_id))
    sesi.execute(delete(RekapDesa).where(RekapDesa.run_id == run_id))
    sesi.execute(delete(RekapKabupaten).where(RekapKabupaten.run_id == run_id))


def tandai_job_terhenti(sesi: Session, setelan: Settings) -> list[int]:
    """Tandai job ``jalan`` yang heartbeat-nya kedaluwarsa sebagai ``gagal``.

    Job seperti ini biasanya ditinggalkan proses yang mati (server dimatikan),
    sehingga selamanya menghalangi aturan "satu job aktif per kabupaten/tipe".
    Hasil separuhnya dibersihkan dan pesannya dibuat khusus supaya operator tahu
    job boleh diunggah ulang. Job ``jalan`` yang masih sehat (heartbeat baru)
    tidak disentuh.
    """
    batas = sekarang() - timedelta(minutes=setelan.job_timeout_menit)
    kandidat = list(
        sesi.scalars(
            select(Run).where(
                Run.status == STATUS_JALAN,
                func.coalesce(Run.heartbeat_at, Run.started_at, Run.created_at) < batas,
            )
        )
    )
    if not kandidat:
        return []

    ids = [run.id for run in kandidat]
    for run in kandidat:
        bersihkan_hasil(sesi, run.id)
        run.status = STATUS_GAGAL
        run.detail_tersedia = 0
        run.pesan = PESAN_TERHENTI
        run.finished_at = sekarang()
    sesi.commit()
    return ids


def siapkan_urut_penuh(sesi: Session, run_id: int) -> None:
    """Simpan peringkat urut **seluruh** hasil di tabel sementara.

    Dipanggil sebelum ``titik_hasil`` dirampingkan. Peringkatnya (0..n-1)
    adalah ``urut`` yang sama dengan mode tanpa potongan; setelah pemangkasan,
    baris yang tersisa memakai peringkat itu sehingga celah urutnya identik.
    """
    if sesi.get_bind().dialect.name == "sqlite":
        sesi.execute(text(f"DROP TABLE IF EXISTS {TABEL_URUT}"))
    else:
        # Hanya tabel sementara milik koneksi ini yang boleh dihapus.
        sesi.execute(text(f"DROP TEMPORARY TABLE IF EXISTS {TABEL_URUT}"))
    sesi.execute(
        text(
            f"CREATE TEMPORARY TABLE {TABEL_URUT} AS "  # noqa: S608 - nama tabel konstanta
            "SELECT assignment_id, ROW_NUMBER() OVER (ORDER BY urut) - 1 AS baru "
            "FROM titik_hasil WHERE run_id = :run"
        ),
        {"run": run_id},
    )


def terapkan_urut_penuh(sesi: Session, run_id: int) -> None:
    """Ganti ``urut`` sementara dengan peringkat penuh (setelah pemangkasan).

    Hanya baris run ini yang masih ada yang diperbarui (titik yang perlu
    perhatian). Nilai baru 0..n-1 tidak bentrok dengan nilai sementara karena
    baris digeser ``GESER_URUT`` lebih dulu; baris run lain tidak tersentuh.
    """
    sesi.execute(
        text("UPDATE titik_hasil SET urut = urut + :geser WHERE run_id = :run"),
        {"geser": GESER_URUT, "run": run_id},
    )
    dialek = sesi.get_bind().dialect.name
    if dialek == "sqlite":
        sesi.execute(
            text(
                "UPDATE titik_hasil SET urut = ("
                f"SELECT baru FROM {TABEL_URUT} "
                f"WHERE {TABEL_URUT}.assignment_id = titik_hasil.assignment_id"
                ") WHERE run_id = :run"
            ),
            {"run": run_id},
        )
        sesi.execute(text(f"DROP TABLE {TABEL_URUT}"))
    else:
        sesi.execute(
            text(
                "UPDATE titik_hasil JOIN "
                f"{TABEL_URUT} ON {TABEL_URUT}.assignment_id = titik_hasil.assignment_id "
                f"SET titik_hasil.urut = {TABEL_URUT}.baru "
                "WHERE titik_hasil.run_id = :run"
            ),
            {"run": run_id},
        )
        sesi.execute(text(f"DROP TEMPORARY TABLE {TABEL_URUT}"))


def proses_satu_job(
    sesi_pabrik: sessionmaker[Session] | None = None, setelan: Settings | None = None
) -> bool:
    """Ambil lalu jalankan satu job; ``False`` kalau tidak ada job antre."""
    sesi_pabrik = sesi_pabrik or get_sessionmaker()
    setelan = setelan or get_settings()

    with sesi_pabrik() as sesi:
        terhenti = tandai_job_terhenti(sesi, setelan)
        if terhenti:
            logger.warning("job terhenti ditandai gagal: %s", terhenti)
        run = klaim_job(sesi)
        if run is None:
            return False
        run_id, tipe, kdprov, kdkab = run.id, run.tipe, run.kdprov, run.kdkab

    logger.info("job %s (%s, %s/%s) mulai dikerjakan", run_id, tipe, kdprov, kdkab)
    potongan = setelan.proses_chunk_titik > 0
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

            if potongan:
                jumlah = proses_potongan(sesi, run, setelan)
            else:
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

            # Peringkat urut penuh dihitung sebelum titik tidak perlu perhatian
            # dibuang, supaya celah urut sama dengan mode tanpa potongan.
            if potongan:
                siapkan_urut_penuh(sesi, run_id)

            modul_rekap.simpan_rekap(sesi, run)

            run.jumlah_baris = jumlah
            run.jumlah_tanpa_wilayah = hitung_tanpa_wilayah(sesi, run_id)
            run.status = STATUS_SUKSES
            run.heartbeat_at = sekarang()
            run.finished_at = sekarang()
            # Satu transaksi: rekap + status sukses + pemangkasan titik_hasil.
            buang = modul_rekap.pangkas_titik_hasil(sesi, run)
            if potongan:
                terapkan_urut_penuh(sesi, run_id)
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


def ambil_kunci(sesi: Session, nama: str = NAMA_KUNCI_WORKER) -> bool:
    """Ambil advisory lock worker ``--once`` (MariaDB ``GET_LOCK``).

    Di SQLite/tes tidak ada ``GET_LOCK``; fungsi mengembalikan ``True`` (tidak
    ada dua proses cron yang perlu dijaga di lingkungan tes).
    """
    if sesi.get_bind().dialect.name not in ("mysql", "mariadb"):
        return True
    return bool(
        sesi.execute(text("SELECT GET_LOCK(:nama, 0)"), {"nama": nama}).scalar()
    )


def lepas_kunci(sesi: Session, nama: str = NAMA_KUNCI_WORKER) -> None:
    """Lepas advisory lock worker (koneksi sama dengan :func:`ambil_kunci`)."""
    if sesi.get_bind().dialect.name in ("mysql", "mariadb"):
        sesi.execute(text("SELECT RELEASE_LOCK(:nama)"), {"nama": nama})
        sesi.commit()


def jalankan_sekali(
    sesi_pabrik: sessionmaker[Session] | None = None, setelan: Settings | None = None
) -> bool:
    """Mode cron: ambil **paling banyak satu** job, proses, lalu keluar.

    Kunci advisory dipasang di koneksi terpisah selama job berjalan, sehingga
    dua pemanggilan cron (``python -m app.worker --once``) tidak memproses job
    bersamaan. Kembalian ``False`` kalau tidak ada job atau kunci dipegang
    proses lain.
    """
    sesi_pabrik = sesi_pabrik or get_sessionmaker()
    setelan = setelan or get_settings()

    with sesi_pabrik() as sesi:
        if not ambil_kunci(sesi):
            logger.info("worker --once lain sedang berjalan; keluar")
            return False
        try:
            return proses_satu_job(sesi_pabrik, setelan)
        finally:
            lepas_kunci(sesi)


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


def main(argv: list[str] | None = None) -> None:
    """Titik masuk worker terpisah: ``python -m app.worker [--once]``."""
    parser = argparse.ArgumentParser(
        prog="python -m app.worker",
        description="Worker pemroses job Proses A/B.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="ambil paling banyak satu job menunggu, proses, lalu keluar (untuk cron)",
    )
    argumen = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    setelan = get_settings()

    if argumen.once:
        diproses = jalankan_sekali(setelan=setelan)
        logger.info(
            "mode --once selesai: %s",
            "satu job diproses" if diproses else "tidak ada job (atau worker lain berjalan)",
        )
        return

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
