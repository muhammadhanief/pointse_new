"""Worker pemroses job Proses A/B (T3).

Aturan yang dipenuhi modul ini:

- job diambil dengan ``SELECT ... FOR UPDATE SKIP LOCKED`` (MySQL 8) supaya aman
  dijalankan oleh beberapa worker sekaligus;
- hanya satu job aktif per (kdprov, kdkab, tipe): job yang (kdprov, kdkab, tipe)-nya
  sedang berstatus ``jalan`` dilewati; kalau ada beberapa job antre untuk
  (kdprov, kdkab, tipe) yang sama, semuanya tetap dikerjakan **berurutan** (yang
  paling lama dulu) dan tidak ada job yang ditandai batal/digantikan;
- job B ditahan selama masih ada job A untuk kabupaten/kota yang sama dengan id
  lebih kecil yang belum selesai, lalu sumber A-nya ditentukan ulang tepat sebelum
  diproses (A sukses terbaru) beserta petanya, supaya B tidak memakai peta A lama;
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

    .venv/bin/python -m app.worker --once
    .venv/bin/python -m app.worker --loop

``--loop`` mem-poll setiap ``WORKER_POLL_DETIK`` detik dan berhenti rapi saat
menerima SIGTERM/SIGINT: batch yang sedang disimpan diselesaikan lebih dulu, job
dikembalikan ke ``menunggu``, lalu proses keluar. Satu proses worker memegang
``fcntl.flock`` pada ``WORKER_LOCK_FILE`` sehingga ``--once`` dari cron tidak
berjalan bersamaan dengan service.

Pekerjaan paralel bisa lewat dua cara:

- ``MAX_WORKERS`` di ``.env`` menyalakan beberapa thread di dalam satu proses
  (dipakai saat ``WORKER_ENABLED=true`` di API). Anggaran memori dihitung dari
  RSS proses, jadi semua thread berbagi satu ``WORKER_MEM_BUDGET_MB``.
- Service produksi ``--loop`` mengabaikan ``MAX_WORKERS`` karena memakai satu
  proses per unit. Worker tambahan dijalankan sebagai proses terpisah dengan
  ``WORKER_LOCK_FILE`` sendiri (unit template ``deploy/pointse-worker@.service``),
  sehingga tiap proses punya anggaran memori sendiri.

Dengan lebih dari satu worker, dua job berbeda kabupaten/kota jalan paralel. Job
untuk kabupaten/kota yang sama tidak pernah dikerjakan bersamaan: klaim menahan
satu job per kabupaten (lihat :func:`kueri_klaim`) dan diverifikasi ulang setelah
commit (lihat :func:`klaim_job`), karena A dan B sekabupaten memakai baris
``wilayah`` yang sama dan hanya akan menimbulkan lock wait.

Pemangkasan ``titik_hasil`` **tidak** dikerjakan di jalur job; tugas itu ada di
:mod:`app.pemeliharaan` supaya transaksi sukses tetap pendek.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import re
import signal
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from sqlalchemy import (
    Engine,
    Float,
    Integer,
    Numeric,
    Select,
    SmallInteger,
    bindparam,
    delete,
    func,
    insert,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, aliased, sessionmaker

from app import geser as modul_geser
from app import rekap as modul_rekap
from app import wilayah
from app.anomali import simpan_anomali
from app.config import Settings, get_settings
from app.db import get_sessionmaker
from app.kunci import KunciBerkas, jalur_kunci
from app.models import (
    ARAH_MASTER,
    ARAH_PETA,
    SEMESTER_SLS_2026_1,
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    TIPE_V,
    WORKER_BERHENTI,
    WORKER_JALAN,
    WORKER_MENANGGUR,
    AnomaliTitik,
    RekapDesa,
    RekapKabupaten,
    RekapSubsls,
    Run,
    TitikHasil,
    ValidasiSlsUnmatch,
    Wilayah,
    WorkerEvent,
    WorkerHeartbeat,
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

#: Pesan untuk job ``jalan`` yang heartbeat-nya kedaluwarsa (server mati).
PESAN_TERHENTI = "proses terhenti, kemungkinan dimatikan server"

#: Job dianggap yatim bila tidak ada heartbeat worker yang menyebutnya selama
#: ini (detik). Worker yang mati berhenti memperbarui ``worker_heartbeat``.
AMBANG_YATIM_DETIK = 300

#: Kunci bernama MySQL yang menyerialkan fase akhir job antar worker.
KUNCI_FASE_AKHIR = "pointse:fase_akhir"

#: Lama menunggu kunci fase akhir (detik). Kunci bernama milik satu koneksi, jadi
#: pemegangnya yang mati melepas kunci itu sendiri; menunggu lama lebih murah
#: daripada job gagal lalu diulang operator.
TUNGGU_KUNCI_FASE_AKHIR_DETIK = 3600

#: Pesan saat worker berhenti rapi di tengah job.
PESAN_DIHENTIKAN = "worker dihentikan, job dikembalikan ke antrean"

#: Pesan saat RSS worker melewati ``WORKER_MEM_BUDGET_MB``.
PESAN_ANGGARAN_MEMORI = (
    "worker melewati anggaran memori; job dihentikan agar server tidak OOM"
)

#: Pola galat MySQL yang sering muncul saat menyimpan hasil proses.
_POLA_KOLOM_WAJIB = re.compile(
    r"\(1364, \"Field '([^']+)' doesn't have a default value\"\)"
)
_POLA_TERLALU_PANJANG = re.compile(r"\(1406, \"Data too long for column '([^']+)'")
_POLA_DUPLIKAT = re.compile(r"\(1062, \"Duplicate entry '([^']*)' for key '([^']+)'")
_POLA_LOCK_WAIT = re.compile(r"\(1205, ['\"]Lock wait timeout exceeded")
_POLA_DEADLOCK = re.compile(r"\(1213, ['\"]Deadlock found")


def _sebut_berkas(run: Run | None) -> str:
    """Sebutan berkas yang sedang diproses untuk pesan galat."""
    if run is None:
        return "berkas yang diunggah"
    return f"berkas Proses {run.tipe} ({run.nama_file_input})"


def _jelaskan_galat(mentah: str, run: Run | None = None) -> str | None:
    """Penjelasan galat basis data yang umum; ``None`` bila tidak dikenali."""
    berkas = _sebut_berkas(run)

    cocok = _POLA_KOLOM_WAJIB.search(mentah)
    if cocok:
        kolom = cocok.group(1)
        return (
            f"Kolom wajib '{kolom}' tidak terisi saat menyimpan hasil, jadi basis "
            f"data menolak barisnya. Penyebab paling sering: {berkas} tidak memuat "
            f"kolom '{kolom}' (namanya berbeda atau kolomnya hilang), sehingga "
            "nilainya kosong. Periksa kolom pada berkas lalu unggah ulang."
        )

    cocok = _POLA_TERLALU_PANJANG.search(mentah)
    if cocok:
        kolom = cocok.group(1)
        return (
            f"Nilai kolom '{kolom}' terlalu panjang untuk kolom basis data "
            f"(melebihi batas). Periksa {berkas}: ada nilai yang formatnya tidak "
            "sesuai atau salah saat diekspor."
        )

    cocok = _POLA_DUPLIKAT.search(mentah)
    if cocok:
        return (
            f"Ada data ganda pada kunci unik '{cocok.group(2)}' (nilai "
            f"'{cocok.group(1)}'). {berkas.capitalize()} memuat baris yang sama "
            "dua kali untuk kunci itu."
        )

    if _POLA_LOCK_WAIT.search(mentah):
        return (
            "Basis data menunggu kunci baris terlalu lama (lock wait timeout): "
            "ada proses lain yang sedang mengubah baris yang sama. Data tidak "
            "rusak; job bisa diunggah ulang."
        )

    if _POLA_DEADLOCK.search(mentah):
        return (
            "Basis data mendeteksi deadlock: dua proses saling menunggu kunci "
            "baris. Data tidak rusak; job bisa diunggah ulang."
        )

    return None


def pesan_galat(galat: BaseException, run: Run | None = None) -> str:
    """Pesan galat untuk ``runs.pesan``: penjelasan singkat + galat mentah.

    Galat mentah selalu disertakan (walau sudah ada penjelasan) supaya penyebab
    teknis -- SQL, nama kolom, nilai baris -- masih bisa ditelusuri.
    """
    mentah = str(galat).strip() or repr(galat)
    penjelasan = _jelaskan_galat(mentah, run)
    if not penjelasan:
        return mentah
    return f"{penjelasan}\n\nPesan galat mentah: {mentah}"


def worker_id_untuk(nama: str | None = None) -> str:
    """Identitas worker yang stabil untuk satu proses/thread."""
    bagian = nama or threading.current_thread().name
    return f"{socket.gethostname()}:{os.getpid()}:{bagian}"[:80]


def pangkas_event(sesi: Session, setelan: Settings) -> None:
    """Buang event lama dan batasi jumlah baris agar tabel tidak membengkak."""
    batas = sekarang() - timedelta(days=setelan.worker_event_retensi_hari)
    sesi.execute(delete(WorkerEvent).where(WorkerEvent.created_at < batas))
    if setelan.worker_event_maks <= 0:
        return
    batas_id = sesi.scalar(
        select(WorkerEvent.id)
        .order_by(WorkerEvent.id.desc())
        .offset(setelan.worker_event_maks - 1)
        .limit(1)
    )
    if batas_id is not None:
        sesi.execute(delete(WorkerEvent).where(WorkerEvent.id < batas_id))


def catat_event(
    sesi: Session,
    *,
    worker_id: str | None,
    jenis: str,
    pesan: str,
    run_id: int | None = None,
    level: str = "info",
    setelan: Settings | None = None,
) -> WorkerEvent:
    """Tambahkan satu kejadian worker; pemanggil yang melakukan commit."""
    event = WorkerEvent(
        worker_id=worker_id,
        run_id=run_id,
        level=level,
        jenis=jenis,
        pesan=pesan[:4000],
    )
    sesi.add(event)
    if setelan is not None:
        pangkas_event(sesi, setelan)
    return event


def _catat_event_aman(
    sesi_pabrik: sessionmaker[Session],
    setelan: Settings,
    *,
    worker_id: str | None,
    jenis: str,
    pesan: str,
    run_id: int | None = None,
    level: str = "info",
) -> None:
    """Tulis event di sesi terpisah; kegagalan event tidak boleh mematikan job."""
    try:
        with sesi_pabrik() as sesi:
            catat_event(
                sesi,
                worker_id=worker_id,
                jenis=jenis,
                pesan=pesan,
                run_id=run_id,
                level=level,
                setelan=setelan,
            )
            sesi.commit()
    except Exception:  # noqa: BLE001 - event hanya informasi operasional
        logger.exception("gagal menulis event worker %s", jenis)


def perbarui_heartbeat_worker(
    sesi: Session,
    worker_id: str,
    *,
    status: str,
    run_id: int | None = None,
) -> None:
    """Upsert denyut worker di ``worker_heartbeat`` (commit oleh pemanggil)."""
    waktu = sekarang()
    baris = sesi.get(WorkerHeartbeat, worker_id)
    if baris is None:
        sesi.add(
            WorkerHeartbeat(
                worker_id=worker_id,
                pid=os.getpid(),
                run_id=run_id,
                hostname=socket.gethostname()[:128],
                status=status,
                started_at=waktu,
                heartbeat_at=waktu,
            )
        )
        return
    baris.pid = os.getpid()
    baris.run_id = run_id
    baris.hostname = socket.gethostname()[:128]
    baris.status = status
    baris.heartbeat_at = waktu


def _set_worker_idle(
    sesi_pabrik: sessionmaker[Session], worker_id: str
) -> None:
    """Tandai worker menganggur setelah satu job selesai/gagal."""
    try:
        with sesi_pabrik() as sesi:
            perbarui_heartbeat_worker(sesi, worker_id, status=WORKER_MENANGGUR)
            sesi.commit()
    except Exception:  # noqa: BLE001
        logger.exception("gagal memperbarui heartbeat worker %s", worker_id)


def _set_worker_berhenti(
    sesi_pabrik: sessionmaker[Session], worker_id: str
) -> None:
    """Tandai worker berhenti (mode sekali atau loop selesai)."""
    try:
        with sesi_pabrik() as sesi:
            perbarui_heartbeat_worker(sesi, worker_id, status=WORKER_BERHENTI)
            sesi.commit()
    except Exception:  # noqa: BLE001
        logger.exception("gagal menandai worker berhenti %s", worker_id)


class WorkerDihentikan(RuntimeError):
    """Sinyal SIGTERM diterima; berhenti setelah batch yang sedang berjalan."""


class AnggaranMemori(RuntimeError):
    """RSS worker melewati batas yang dikonfigurasi."""


def baca_rss_mb() -> float | None:
    """Baca RSS proses dari ``/proc/self/statm`` (Linux); ``None`` bila tak ada."""
    try:
        with open("/proc/self/statm", encoding="ascii") as berkas:
            halaman = int(berkas.read().split()[1])
        return halaman * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def cek_berhenti(
    penghenti: threading.Event | None,
    setelan: Settings | None = None,
) -> None:
    """Hentikan job setelah batch bila diminta, atau bila memori melewati batas."""
    if penghenti is not None and penghenti.is_set():
        raise WorkerDihentikan
    if setelan is not None and setelan.worker_mem_budget_mb > 0:
        rss = baca_rss_mb()
        if rss is not None and rss > setelan.worker_mem_budget_mb:
            raise AnggaranMemori(
                f"RSS {rss:.0f} MiB > {setelan.worker_mem_budget_mb} MiB"
            )


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


def tambah_kolom_jarak(hasil: gpd.GeoDataFrame) -> pd.Series:
    """Jarak (meter) titik hasil edit dari posisi asal, vektor tanpa baris.

    Hanya Proses B yang punya kolom ``latitude_edited``/``longitude_edited``;
    Proses A menghasilkan ``None``. Rumusnya sama dengan
    :func:`app.geser.jarak_meter` (haversine), tetapi dihitung dengan numpy
    supaya ratusan ribu titik tidak perlu di-``map`` di Python.
    """
    kolom = (
        "latitude_origin",
        "longitude_origin",
        "latitude_edited",
        "longitude_edited",
    )
    if not all(nama in hasil.columns for nama in kolom):
        return pd.Series([None] * len(hasil), index=hasil.index, dtype="float64")

    lat1, lon1, lat2, lon2 = (
        np.radians(
            pd.to_numeric(hasil[nama], errors="coerce").to_numpy(dtype="float64")
        )
        for nama in kolom
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    jarak = 2 * modul_geser.R_BUMI_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    # NaN koordinat -> NaN jarak (tersimpan NULL), bukan 0.
    jarak[np.isnan(a)] = np.nan
    return pd.Series(jarak, index=hasil.index)


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
    keluaran["jarak_geser_m"] = tambah_kolom_jarak(hasil)
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
    sesi: Session,
    run: Run,
    hasil: gpd.GeoDataFrame,
    id_wilayah: dict[str, int],
    setelan: Settings | None = None,
    penghenti: threading.Event | None = None,
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
        # SIGTERM/anggaran memori baru dihormati setelah batch ini utuh.
        cek_berhenti(penghenti, setelan)

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
    sesi: Session,
    run: Run,
    hasil: gpd.GeoDataFrame,
    id_wilayah: dict[str, int],
    setelan: Settings | None = None,
    penghenti: threading.Event | None = None,
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
        # SIGTERM/anggaran memori baru dihormati setelah batch ini utuh.
        cek_berhenti(penghenti, setelan)


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


def pangkas_berkas(
    sesi: Session,
    run_ids: list[int],
    akar: Path,
    setelan: Settings | None = None,
) -> list[str]:
    """Hapus folder berkas mentah run lama (default: hanya saat disk menipis).

    Dengan ``SIMPAN_BERKAS_MENTAH`` (bawaan), berkas mentah semua run disimpan
    supaya tombol unduh tetap berfungsi. Penghapusan baru terjadi bila ruang
    disk bebas turun di bawah ``BERKAS_MIN_FREE_MB``: run tertua dihapus lebih
    dulu, sedangkan run terbaru per (provinsi, kabupaten, tipe) dan berkas
    geotag master selalu dipertahankan. Bila opsi itu dimatikan, perilaku lama
    berlaku: folder run di ``run_ids`` (yang ``titik_hasil``-nya dipangkas)
    langsung dihapus.

    Hanya folder di dalam ``akar`` (folder unggahan) yang dihapus, dan berkas run
    dengan status lain (``menunggu``/``jalan``/``gagal``) tidak pernah ikut karena
    :mod:`app.pemeliharaan` hanya mengirim id run sukses yang dipangkas. Baris
    ``runs`` tetap menyimpan nama berkasnya sebagai riwayat.
    """
    setelan = setelan or get_settings()
    akar = akar.resolve()
    jaga = setelan.simpan_berkas_mentah
    if jaga and ruang_bebas_mb(akar) >= setelan.berkas_min_free_mb:
        return []
    if jaga:
        kandidat = kandidat_hapus_berkas(sesi)
    elif run_ids:
        kandidat = list(sesi.scalars(select(Run).where(Run.id.in_(run_ids))))
    else:
        return []

    terhapus: list[str] = []
    for run in kandidat:
        if jaga and ruang_bebas_mb(akar) >= setelan.berkas_min_free_mb:
            break
        # Berkas input run A bisa menunjuk geotag master (permanen); jangan
        # menghapus foldernya. Folder peta tetap dipangkas.
        jalur_hapus = {Path(run.berkas_peta).resolve().parent}
        if run.geotag_master_id is None and run.berkas_input:
            jalur_hapus.add(Path(run.berkas_input).resolve().parent)
        for jalur in jalur_hapus:
            if jalur != akar and akar in jalur.parents and jalur.exists():
                shutil.rmtree(jalur, ignore_errors=True)
                terhapus.append(str(jalur))
    return terhapus


def ruang_bebas_mb(jalur: Path) -> int:
    """Ruang disk bebas (MB) pada sistem berkas ``jalur``; 0 bila tidak terbaca."""
    try:
        return int(shutil.disk_usage(jalur).free // (1024 * 1024))
    except OSError:
        return 0


def kandidat_hapus_berkas(sesi: Session) -> list[Run]:
    """Run sukses yang berkasnya boleh dibuang saat disk menipis, terlama dulu.

    Run terbaru per (provinsi, kabupaten, tipe) dipertahankan supaya unduhan dan
    proses ulang tetap tersedia; run dengan geotag master tidak pernah dihapus
    karena berkas input-nya milik master.
    """
    runs = list(
        sesi.scalars(select(Run).where(Run.status == STATUS_SUKSES).order_by(Run.id))
    )
    terbaru: dict[tuple[str, str, str], int] = {}
    for run in runs:
        terbaru[(run.kdprov, run.kdkab, run.tipe)] = run.id
    simpan = set(terbaru.values())
    return [
        run
        for run in runs
        if run.id not in simpan and run.geotag_master_id is None
    ]


def proses_potongan(
    sesi: Session,
    run: Run,
    setelan: Settings,
    penghenti: threading.Event | None = None,
) -> int:
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
    cek_berhenti(penghenti, setelan)

    id_wilayah: dict[str, int] = {}
    for urut_awal, titik_potongan in baca_potongan(
        run.berkas_input, run.layer_input, setelan.proses_chunk_titik
    ):
        cek_berhenti(penghenti, setelan)
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

        simpan_potongan(sesi, run, hasil, id_wilayah, setelan, penghenti)

    if run.jumlah_baris is None:
        run.jumlah_baris = 0
        sesi.commit()
    return int(run.jumlah_baris)


def kueri_klaim() -> Select[tuple[Run]]:
    """Kueri pengambilan job: ``FOR UPDATE SKIP LOCKED`` (MySQL 8) + satu job per kab.

    Satu job aktif per (kdprov, kdkab) -- **tanpa memandang tipe**. Proses A dan B
    untuk kabupaten/kota yang sama memakai baris ``wilayah`` yang sama, jadi
    menjalankannya bersamaan hanya menimbulkan lock wait (MySQL 1205). Job yang
    kabupatennya sedang dikerjakan dilewati. Diurutkan dari id terkecil (urutan
    unggah) supaya job antre lama tetap dikerjakan **berurutan** dan tidak ada
    yang dibatalkan; run yang sukses terakhir jadi run dengan id terbesar.

    Job B juga ditahan selama masih ada Proses A untuk kabupaten/kota yang sama
    dengan id lebih kecil yang belum selesai. Tanpa penjaga ini, worker kedua
    bisa menjalankan B bersamaan dengan A-nya sehingga B memakai peta A lama.
    """
    lain = aliased(Run)
    sedang_jalan = (
        select(lain.id)
        .where(
            lain.status == STATUS_JALAN,
            lain.kdprov == Run.kdprov,
            lain.kdkab == Run.kdkab,
        )
        .exists()
    )
    a_tertunda = (
        select(lain.id)
        .where(
            lain.tipe == TIPE_A,
            lain.kdprov == Run.kdprov,
            lain.kdkab == Run.kdkab,
            lain.id < Run.id,
            lain.status.in_((STATUS_MENUNGGU, STATUS_JALAN)),
        )
        .exists()
    )
    return (
        select(Run)
        .where(
            Run.status == STATUS_MENUNGGU,
            ~sedang_jalan,
            or_(Run.tipe == TIPE_A, ~a_tertunda),
        )
        .order_by(Run.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def klaim_job(sesi: Session) -> Run | None:
    """Ambil satu job ``menunggu`` dengan ``FOR UPDATE SKIP LOCKED`` (MySQL 8).

    Job yang kabupaten/kotanya sedang dikerjakan worker lain dilewati; job antre
    lain untuk kabupaten itu dibiarkan ``menunggu`` (dikerjakan berurutan, tidak
    ada yang ditandai batal).

    Setelah klaim, kepemilikan diverifikasi ulang: dua worker bisa lolos saringan
    ``sedang_jalan`` pada jendela balapan sempit (keduanya membaca snapshot
    sebelum status lawannya di-commit). Yang kalah -- id run lebih besar --
    dikembalikan ke ``menunggu`` supaya tidak ada dua job sekabupaten menulis
    baris ``wilayah`` bersamaan.
    """
    run = sesi.execute(kueri_klaim()).scalar_one_or_none()
    if run is None:
        return None

    run.status = STATUS_JALAN
    run.started_at = sekarang()
    run.heartbeat_at = sekarang()
    run.pesan = None
    sesi.commit()

    if _ada_job_sekabupaten_lebih_dulu(sesi, run):
        run.status = STATUS_MENUNGGU
        run.started_at = None
        run.heartbeat_at = None
        sesi.commit()
        logger.info("job %s ditunda: kabupaten %s sedang dikerjakan job lain", run.id, run.kdkab)
        return None
    return run


def _ada_job_sekabupaten_lebih_dulu(sesi: Session, run: Run) -> bool:
    """True bila ada job ``jalan`` lain di kabupaten/kota yang sama dengan id kecil."""
    lain = sesi.scalar(
        select(func.count())
        .select_from(Run)
        .where(
            Run.status == STATUS_JALAN,
            Run.kdprov == run.kdprov,
            Run.kdkab == run.kdkab,
            Run.id < run.id,
        )
    )
    return bool(lain)


def sumber_a_untuk_b(sesi: Session, run: Run) -> Run | None:
    """Run A sukses terbaru **sebelum** job B ini untuk kabupaten/kota yang sama."""
    return sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_A,
            Run.status == STATUS_SUKSES,
            Run.kdprov == run.kdprov,
            Run.kdkab == run.kdkab,
            Run.id < run.id,
        )
        .order_by(Run.id.desc())
        .limit(1)
    ).first()


def ikat_ulang_sumber_a(sesi: Session, run: Run) -> Run | None:
    """Tentukan ulang sumber A job B tepat sebelum job dikerjakan.

    Sumber A dicatat saat unggah memakai "A sukses terakhir" pada detik itu.
    Karena A bisa masih antre berjam-jam, B sering terikat ke A lama beserta
    petanya, lalu ditolak rekap yang memakai A terbaru. Di sini sumber dipilih
    ulang: A sukses terbaru dengan id lebih kecil dari B (urutan unggah), lalu
    petanya disalin ke folder job. Nama berkas dipertahankan karena layer
    GeoJSON diturunkan dari nama berkas. Tanpa A yang lebih baru, job dibiarkan.
    """
    if run.tipe != TIPE_B:
        return None
    sumber = sumber_a_untuk_b(sesi, run)
    if sumber is None or sumber.id == run.sumber_run_a_id:
        return sumber
    asal = Path(sumber.berkas_peta) if sumber.berkas_peta else None
    if asal is None or not asal.is_file():
        logger.warning(
            "job %s: peta A %s tidak tersedia; tetap memakai sumber A %s",
            run.id,
            sumber.id,
            run.sumber_run_a_id,
        )
        return None
    tujuan = Path(run.berkas_peta).parent / asal.name if run.berkas_peta else asal
    if asal.resolve() != tujuan.resolve():
        shutil.copy2(asal, tujuan)
    run.berkas_peta = str(tujuan)
    run.nama_file_peta = sumber.nama_file_peta or asal.name
    run.layer_peta = sumber.layer_peta
    run.sumber_run_a_id = sumber.id
    logger.info(
        "job %s: sumber A diikat ulang ke %s (peta %s)",
        run.id,
        sumber.id,
        tujuan.name,
    )
    return sumber


def proses_validasi_v(
    sesi: Session, run: Run, setelan: Settings | None = None
) -> tuple[int, str, bool]:
    """Jalankan validasi SLS 2026 S1 untuk satu run V; kembalikan (baris, pesan, lolos).

    Menulis ``validasi_sls_unmatch`` dan menandai ``runs.semester``. Tidak
    menyentuh ``wilayah``/``titik_hasil``/rekap (steril dari SE2026).
    """
    from app import validasi_sls

    setelan = setelan or get_settings()
    kode = layanan_kode_kab(run)
    hasil = validasi_sls.validasi_berkas(
        run.berkas_peta, run.layer_peta, setelan.dir_master_sls_2026_s1, kode
    )
    unmatch = [
        *hasil.matching.unmatch_peta,
        *hasil.matching.unmatch_master,
        *hasil.matching.unmatch_sub_peta,
        *hasil.matching.unmatch_sub_master,
    ]
    sesi.execute(delete(ValidasiSlsUnmatch).where(ValidasiSlsUnmatch.run_id == run.id))
    sesi.execute(
        insert(ValidasiSlsUnmatch),
        [
            {
                "run_id": run.id,
                "arah": satu.arah,
                "level": satu.level,
                "idsls": satu.idsls,
                "nmsls": satu.nmsls,
                "alasan": satu.alasan,
            }
            for satu in unmatch
        ],
    )
    return len(unmatch), hasil.pesan, hasil.lolos


def layanan_kode_kab(run: Run) -> str:
    """Kode kabupaten 4 digit untuk run (mendukung kode pendek peta)."""
    from app import layanan

    return layanan.kode_kabupaten(run.kdprov, run.kdkab)


def simpan_fase_akhir_v(sesi: Session, run: Run, hasil: tuple[int, str, bool]) -> None:
    """Tutup run V: jumlah unmatch + status sukses/gagal + pesan 3 blok."""
    jumlah, pesan, lolos = hasil
    run.jumlah_baris = jumlah
    run.jumlah_tanpa_wilayah = 0
    run.pesan = pesan
    run.semester = run.semester or SEMESTER_SLS_2026_1
    run.status = STATUS_SUKSES if lolos else STATUS_GAGAL
    run.heartbeat_at = sekarang()
    run.finished_at = sekarang()
    run.detail_tersedia = 0
    sesi.commit()


def bersihkan_hasil(sesi: Session, run_id: int) -> None:
    """Buang sisa hasil/rekap satu job (job diulang atau gagal di tengah jalan)."""
    sesi.execute(delete(TitikHasil).where(TitikHasil.run_id == run_id))
    sesi.execute(delete(RekapDesa).where(RekapDesa.run_id == run_id))
    sesi.execute(delete(RekapKabupaten).where(RekapKabupaten.run_id == run_id))
    sesi.execute(delete(RekapSubsls).where(RekapSubsls.run_id == run_id))
    # Unmatch run V ikut dibuang supaya run ulang tidak menampilkan sisa lama.
    sesi.execute(delete(ValidasiSlsUnmatch).where(ValidasiSlsUnmatch.run_id == run_id))
    # Anomali job B ikut dibuang supaya menu tidak menampilkan hasil lama saat
    # run diproses ulang (kalau gagal di tengah, tidak ada sisa yang menyesatkan).
    sesi.execute(delete(AnomaliTitik).where(AnomaliTitik.run_b_id == run_id))
    sesi.execute(
        update(Run)
        .where(Run.id == run_id)
        .values(anomali_versi=0, jumlah_anomali=None)
    )


def tandai_job_terhenti(
    sesi: Session, setelan: Settings, worker_id: str | None = None
) -> list[int]:
    """Tandai job ``jalan`` yang heartbeat-nya kedaluwarsa sebagai ``gagal``.

    Job seperti ini biasanya ditinggalkan proses yang mati (server dimatikan),
    sehingga selamanya menghalangi aturan "satu job aktif per kabupaten/tipe".
    Hasil separuhnya dibersihkan dan pesannya dibuat khusus supaya operator tahu
    job boleh diunggah ulang. Job ``jalan`` yang masih sehat (heartbeat baru)
    tidak disentuh.

    Dengan dua worker, job yang baru saja sukses bisa terbaca ``jalan`` oleh
    worker lain (baris ``runs``-nya sedang dikunci transaksi penutup). Karena itu
    kandidat dibaca ulang dengan ``FOR UPDATE`` (baca data terkini, bukan snapshot
    transaksi) dan job yang sudah punya ``finished_at`` tidak pernah disentuh.
    """
    batas = sekarang() - timedelta(minutes=setelan.job_timeout_menit)
    # Worker yang mati (restart/deploy) berhenti memperbarui ``worker_heartbeat``;
    # job yang dipegangnya jadi yatim dan harus segera ditandai gagal, bukan
    # menunggu JOB_TIMEOUT_MENIT yang sengaja longgar untuk job besar.
    segar = sekarang() - timedelta(seconds=AMBANG_YATIM_DETIK)
    # Daftar run yang dipegang worker hidup dibaca terpisah: kalau subquery-nya
    # ikut di kunci ``FOR UPDATE``, baris ``worker_heartbeat`` worker lain bisa
    # tersentuh lock dan heartbeat-nya justru membeku.
    dipegang = list(
        sesi.scalars(
            select(WorkerHeartbeat.run_id).where(
                WorkerHeartbeat.run_id.is_not(None),
                WorkerHeartbeat.heartbeat_at >= segar,
            )
        )
    )
    kandidat = list(
        sesi.scalars(
            select(Run)
            .where(
                Run.status == STATUS_JALAN,
                Run.finished_at.is_(None),
                or_(
                    func.coalesce(Run.heartbeat_at, Run.started_at, Run.created_at)
                    < batas,
                    Run.id.not_in(dipegang),
                ),
            )
            .with_for_update(skip_locked=True)
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
        catat_event(
            sesi,
            worker_id=worker_id,
            run_id=run.id,
            level="warning",
            jenis="job_terhenti",
            pesan=f"Job {run.id} ditandai gagal: {PESAN_TERHENTI}",
            setelan=setelan,
        )
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


@contextmanager
def kunci_fase_akhir(bind: Engine) -> Iterator[None]:
    """Serialkan fase akhir job antar worker (hanya MySQL/MariaDB).

    Fase akhir menulis ulang kolom kunci utama ``titik_hasil.urut`` dan menyapu
    ``titik_hasil``/``wilayah`` satu run sekaligus. Bila dua worker menjalankan
    fase akhir bersamaan, keduanya saling menunggu kunci baris sampai ``lock wait
    timeout`` (1205); itulah yang membuat worker tambahan menghentikan pekerjaan
    yang sedang menyimpan batch, bukan mempercepat antrean.

    Kuncinya dipasang di koneksi tersendiri (bukan koneksi job) supaya tidak ikut
    transaksi job, dan MySQL melepasnya sendiri bila proses pemegangnya mati.
    Dialek lain (SQLite di tes) tidak punya ``GET_LOCK``: tanpa kunci.
    """
    if bind.dialect.name not in ("mysql", "mariadb"):
        yield
        return
    koneksi = bind.connect()
    try:
        dapat = koneksi.execute(
            text("SELECT GET_LOCK(:nama, :detik)"),
            {"nama": KUNCI_FASE_AKHIR, "detik": TUNGGU_KUNCI_FASE_AKHIR_DETIK},
        ).scalar()
        if not dapat:
            raise RuntimeError(
                f"tidak memperoleh kunci {KUNCI_FASE_AKHIR} dalam "
                f"{TUNGGU_KUNCI_FASE_AKHIR_DETIK} detik"
            )
        try:
            yield
        finally:
            koneksi.execute(
                text("SELECT RELEASE_LOCK(:nama)"), {"nama": KUNCI_FASE_AKHIR}
            )
    except Exception:
        # Koneksi yang masih memegang kunci tidak boleh kembali ke pool: kunci
        # yang menggantung akan memblokir seluruh worker.
        koneksi.invalidate()
        raise
    finally:
        koneksi.close()


def simpan_fase_akhir(sesi: Session, run: Run, jumlah: int, potongan: bool) -> int:
    """Rekap, anomali, capaian target, dan perapian ``urut`` (transaksi penutup).

    Kembalikan jumlah baris anomali. Semua langkah di sini menyapu
    ``titik_hasil``/``wilayah`` satu run secara menyeluruh, jadi dijalankan di
    bawah :func:`kunci_fase_akhir` supaya tidak bertabrakan dengan fase akhir job
    lain.
    """
    run_id = run.id
    with kunci_fase_akhir(sesi.get_bind()):
        # Peringkat urut penuh dihitung sebelum titik tidak perlu perhatian
        # dibuang, supaya celah urut sama dengan mode tanpa potongan.
        if potongan:
            siapkan_urut_penuh(sesi, run_id)

        modul_rekap.simpan_rekap(sesi, run)
        # Anomali titik (menu audit) juga butuh seluruh titik B sebelum dipangkas.
        jumlah_anomali = simpan_anomali(sesi, run)
        # Capaian per assignment_id (target A vs B), juga sebelum pemangkasan.
        modul_rekap.simpan_rekap_target(sesi, run)

        run.jumlah_baris = jumlah
        run.jumlah_tanpa_wilayah = hitung_tanpa_wilayah(sesi, run_id)
        run.status = STATUS_SUKSES
        run.heartbeat_at = sekarang()
        run.finished_at = sekarang()
        # Detail run terbaru tersedia; pemangkasan (baris tidak perlu perhatian
        # + run lama) dikerjakan app.pemeliharaan, bukan di sini,
        # supaya transaksi sukses tetap pendek dan tidak menunggu lock.
        run.detail_tersedia = 1
        if potongan:
            terapkan_urut_penuh(sesi, run_id)
        sesi.commit()
    return jumlah_anomali


def denyut_worker(
    worker_id: str, run_id: int, sesi_pabrik: sessionmaker[Session]
) -> None:
    """Tulis denyut worker di transaksi tersendiri (tidak boleh gagal).

    Baris ``worker_heartbeat`` tidak pernah disentuh transaksi batch job, jadi
    denyut ini tetap segar walau transaksi penutup job memegang kunci baris
    ``runs`` lama. Itu penting karena :func:`tandai_job_terhenti` memakai baris
    inilah untuk tahu job masih dipegang worker yang hidup.
    """
    with sesi_pabrik() as sesi:
        perbarui_heartbeat_worker(sesi, worker_id, status=WORKER_JALAN, run_id=run_id)
        sesi.commit()


def denyut_job(run_id: int, sesi_pabrik: sessionmaker[Session]) -> bool:
    """Perbarui ``runs.heartbeat_at``; ``False`` bila job sudah tidak ``jalan``.

    Hanya informasi, jadi jangan menunggu 50 detik saat baris ``runs`` sedang
    dikunci transaksi batch utama.
    """
    with sesi_pabrik() as sesi:
        if sesi.get_bind().dialect.name in ("mysql", "mariadb"):
            sesi.execute(text("SET SESSION innodb_lock_wait_timeout = 2"))
        hasil = sesi.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == STATUS_JALAN)
            .values(heartbeat_at=sekarang())
        )
        sesi.commit()
        return bool(hasil.rowcount)


def _jaga_heartbeat(
    run_id: int,
    worker_id: str,
    sesi_pabrik: sessionmaker[Session],
    berhenti: threading.Event,
    interval: float,
) -> None:
    """Perbarui denyut worker lalu denyut job tiap ``interval`` detik.

    Keduanya ditulis di transaksi yang **terpisah**: kegagalan denyut job (baris
    ``runs`` terkunci transaksi batch besar/penutup) tidak boleh ikut membekukan
    denyut worker, karena denyut worker itulah bukti job masih dipegang proses
    yang hidup -- tanpa pemisahan itu job sehat bisa disapu worker lain sebagai
    yatim.
    """
    while not berhenti.wait(interval):
        try:
            denyut_worker(worker_id, run_id, sesi_pabrik)
        except Exception:  # noqa: BLE001 - denyut tidak boleh mematikan job
            logger.exception("gagal memperbarui heartbeat worker %s", worker_id)

        try:
            if not denyut_job(run_id, sesi_pabrik):
                return
        except OperationalError as galat:
            # 1205 = lock wait timeout, 1213 = deadlock; wajar saat batch besar
            # masih memegang lock baris runs. Jangan banjiri log tiap 15 detik;
            # denyut worker sudah menandai job ini masih hidup.
            kode = getattr(getattr(galat, "orig", None), "args", (None,))[0]
            if kode in (1205, 1213):
                logger.debug("heartbeat job %s tertunda: %s", run_id, galat)
            else:
                logger.warning("heartbeat job %s gagal: %s", run_id, galat)
        except Exception:  # noqa: BLE001 - heartbeat tidak boleh mematikan job
            logger.exception("gagal memperbarui heartbeat job %s", run_id)


def pasang_batas_tunggu_kunci(sesi: Session, setelan: Settings) -> None:
    """Longgarkan batas tunggu kunci baris untuk sesi job ini (MySQL/MariaDB).

    Batch penyimpanan 10.000 baris hanya bisa menunggu worker lain menuntaskan
    sapuannya; batas bawaan MySQL 50 detik membuat job gagal (1205) padahal
    datanya tidak rusak. Nilai ini hanya menempel pada koneksi proses worker --
    API berjalan di proses terpisah dengan pool-nya sendiri.
    """
    if sesi.get_bind().dialect.name not in ("mysql", "mariadb"):
        return
    sesi.execute(
        text("SET SESSION innodb_lock_wait_timeout = :detik"),
        {"detik": setelan.db_lock_wait_detik},
    )


def proses_satu_job(
    sesi_pabrik: sessionmaker[Session] | None = None,
    setelan: Settings | None = None,
    penghenti: threading.Event | None = None,
    worker_id: str | None = None,
) -> bool:
    """Ambil lalu jalankan satu job; ``False`` kalau tidak ada job antre.

    ``penghenti`` dipakai mode service: setelah batch yang sedang berjalan
    selesai, job dikembalikan ke ``menunggu`` lalu proses boleh keluar.
    """
    sesi_pabrik = sesi_pabrik or get_sessionmaker()
    setelan = setelan or get_settings()
    worker_id = worker_id or worker_id_untuk()

    with sesi_pabrik() as sesi:
        perbarui_heartbeat_worker(sesi, worker_id, status=WORKER_MENANGGUR)
        terhenti = tandai_job_terhenti(sesi, setelan, worker_id)
        if terhenti:
            logger.warning("job terhenti ditandai gagal: %s", terhenti)
        run = klaim_job(sesi)
        if run is None:
            perbarui_heartbeat_worker(sesi, worker_id, status=WORKER_MENANGGUR)
            sesi.commit()
            return False
        run_id, tipe, kdprov, kdkab = run.id, run.tipe, run.kdprov, run.kdkab
        perbarui_heartbeat_worker(
            sesi, worker_id, status=WORKER_JALAN, run_id=run_id
        )
        catat_event(
            sesi,
            worker_id=worker_id,
            run_id=run_id,
            jenis="job_klaim",
            pesan=f"Job {run_id} ({tipe}, {kdprov}/{kdkab}) mulai dikerjakan",
            setelan=setelan,
        )
        sesi.commit()

    logger.info("job %s (%s, %s/%s) mulai dikerjakan", run_id, tipe, kdprov, kdkab)
    potongan = setelan.proses_chunk_titik > 0
    buang: list[int] = []
    berhenti_heartbeat = threading.Event()
    heartbeat = threading.Thread(
        target=_jaga_heartbeat,
        args=(
            run_id,
            worker_id,
            sesi_pabrik,
            berhenti_heartbeat,
            setelan.worker_heartbeat_detik,
        ),
        name=f"pointse-heartbeat-{run_id}",
        daemon=True,
    )
    heartbeat.start()
    try:
        with sesi_pabrik() as sesi:
            pasang_batas_tunggu_kunci(sesi, setelan)
            run = sesi.get(Run, run_id)
            if run is None:  # job dihapus saat sedang jalan
                logger.warning("job %s hilang saat dikerjakan", run_id)
                return True

            # Tentukan ulang sumber A job B sebelum diproses (petanya bisa
            # berubah bila A baru selesai setelah B diunggah).
            ikat_ulang_sumber_a(sesi, run)
            sesi.commit()

            # Bersihkan sisa hasil percobaan sebelumnya (bila job diulang).
            bersihkan_hasil(sesi, run_id)
            sesi.commit()

            if run.tipe == TIPE_V:
                # Validasi SLS 2026 S1: steril dari SE2026, tanpa potongan/
                # wilayah/titik_hasil/rekap (PRD §11).
                hasil_v = proses_validasi_v(sesi, run, setelan)
                simpan_fase_akhir_v(sesi, run, hasil_v)
                jumlah = hasil_v[0]
                jumlah_anomali = 0
            elif potongan:
                jumlah = proses_potongan(sesi, run, setelan, penghenti)
            else:
                titik, peta = baca_masukan(run)
                # Dimensi wilayah di-upsert dari peta (nama wilayah hanya di sini).
                wilayah.upsert(sesi, wilayah.baris_dari_peta(peta))
                sesi.commit()
                cek_berhenti(penghenti, setelan)

                hasil = jalankan_proses(run, titik, peta)
                id_wilayah = wilayah.peta_id(sesi, kode_hasil(hasil))
                sesi.commit()
                cek_berhenti(penghenti, setelan)

                # Semua titik disimpan dulu supaya rekap bisa dihitung lewat query
                # GROUP BY; sisanya dirampingkan di akhir (satu transaksi).
                jumlah = simpan_hasil(
                    sesi, run, hasil, id_wilayah, setelan, penghenti
                )

            # Fase akhir (rekap, anomali, capaian, perapian urut) dijalankan di
            # bawah kunci antar-worker; lihat ``simpan_fase_akhir``. Run V
            # steril dari SE2026: sudah ditutup simpan_fase_akhir_v di atas.
            if run.tipe != TIPE_V:
                jumlah_anomali = simpan_fase_akhir(sesi, run, jumlah, potongan)
        logger.info(
            "job %s sukses: %s baris (anomali: %s)",
            run_id,
            jumlah,
            jumlah_anomali,
        )
        _catat_event_aman(
            sesi_pabrik,
            setelan,
            worker_id=worker_id,
            run_id=run_id,
            jenis="job_sukses",
            pesan=f"Job {run_id} sukses: {jumlah} baris",
        )
    except WorkerDihentikan:
        logger.info("job %s dihentikan setelah batch; dikembalikan ke antrean", run_id)
        _catat_event_aman(
            sesi_pabrik,
            setelan,
            worker_id=worker_id,
            run_id=run_id,
            level="warning",
            jenis="job_dihentikan",
            pesan=f"Job {run_id} dikembalikan ke antrean setelah sinyal berhenti",
        )
        with sesi_pabrik() as sesi:
            bersihkan_hasil(sesi, run_id)
            sesi.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    status=STATUS_MENUNGGU,
                    started_at=None,
                    heartbeat_at=None,
                    finished_at=None,
                    detail_tersedia=0,
                    jumlah_baris=0,
                    jumlah_tanpa_wilayah=0,
                    pesan=PESAN_DIHENTIKAN,
                )
            )
            sesi.commit()
    except AnggaranMemori as galat:
        logger.error("job %s melewati anggaran memori: %s", run_id, galat)
        _catat_event_aman(
            sesi_pabrik,
            setelan,
            worker_id=worker_id,
            run_id=run_id,
            level="error",
            jenis="anggaran_memori",
            pesan=f"Job {run_id} gagal: {PESAN_ANGGARAN_MEMORI}",
        )
        with sesi_pabrik() as sesi:
            bersihkan_hasil(sesi, run_id)
            sesi.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    status=STATUS_GAGAL,
                    detail_tersedia=0,
                    pesan=PESAN_ANGGARAN_MEMORI,
                    finished_at=sekarang(),
                )
            )
            sesi.commit()
    except Exception as galat:  # noqa: BLE001 - pesan apa pun dicatat di runs.pesan
        logger.exception("job %s gagal", run_id)
        with sesi_pabrik() as sesi:
            run = sesi.get(Run, run_id)
            pesan = pesan_galat(galat, run)
            ringkas = pesan.splitlines()[0][:500]
            bersihkan_hasil(sesi, run_id)
            sesi.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    status=STATUS_GAGAL,
                    detail_tersedia=0,
                    pesan=pesan[:2000],
                    finished_at=sekarang(),
                )
            )
            sesi.commit()
        _catat_event_aman(
            sesi_pabrik,
            setelan,
            worker_id=worker_id,
            run_id=run_id,
            level="error",
            jenis="job_gagal",
            pesan=f"Job {run_id} gagal: {ringkas}",
        )
    finally:
        berhenti_heartbeat.set()
        heartbeat.join(timeout=5)
        _set_worker_idle(sesi_pabrik, worker_id)
    return True


def jalankan_sekali(
    sesi_pabrik: sessionmaker[Session] | None = None,
    setelan: Settings | None = None,
    penghenti: threading.Event | None = None,
) -> bool:
    """Mode cron: ambil **paling banyak satu** job, proses, lalu keluar.

    ``fcntl.flock`` dipasang selama job berjalan, sehingga dua pemanggilan cron
    (``python -m app.worker --once``) tidak memproses job bersamaan. Kembalian
    ``False`` kalau tidak ada job atau kunci dipegang proses lain.
    """
    sesi_pabrik = sesi_pabrik or get_sessionmaker()
    setelan = setelan or get_settings()

    kunci = KunciBerkas(jalur_kunci(setelan))
    if not kunci.ambil():
        logger.info("worker lain sedang berjalan; keluar")
        return False
    worker_id = worker_id_untuk("once")
    try:
        with sesi_pabrik() as sesi:
            perbarui_heartbeat_worker(sesi, worker_id, status=WORKER_MENANGGUR)
            catat_event(
                sesi,
                worker_id=worker_id,
                jenis="worker_mulai",
                pesan="Worker mode --once mulai",
                setelan=setelan,
            )
            sesi.commit()
        return proses_satu_job(sesi_pabrik, setelan, penghenti, worker_id)
    finally:
        _catat_event_aman(
            sesi_pabrik,
            setelan,
            worker_id=worker_id,
            jenis="worker_berhenti",
            pesan="Worker mode --once berhenti",
        )
        _set_worker_berhenti(sesi_pabrik, worker_id)
        kunci.lepas()


def _pemeliharaan_bila_jeda(setelan: Settings, terakhir: float) -> float:
    """Rapikan ``titik_hasil`` saat worker menganggur (maks. sekali per interval).

    Kembaliannya waktu (``time.monotonic``) percobaan terakhir, supaya worker yang
    terus-menerus menganggur tidak memanggil pemeliharaan tiap putaran poll.
    """
    if setelan.pemeliharaan_interval_menit <= 0:
        return terakhir
    sekarang_detik = time.monotonic()
    jeda = setelan.pemeliharaan_interval_menit * 60
    if terakhir and sekarang_detik - terakhir < jeda:
        return terakhir
    try:
        from app.pemeliharaan import jalankan_pemeliharaan

        ringkasan = jalankan_pemeliharaan(setelan)
    except Exception:  # noqa: BLE001 - pemeliharaan tidak boleh mematikan worker
        logger.exception("pemeliharaan titik_hasil gagal")
        return sekarang_detik
    if ringkasan is None:
        return sekarang_detik
    if ringkasan.run_dipangkas or ringkasan.run_dirampingkan:
        logger.info(
            "pemeliharaan: %s run dipangkas, %s run dirampingkan, %s baris dihapus",
            len(ringkasan.run_dipangkas),
            len(ringkasan.run_dirampingkan),
            ringkasan.baris_dihapus,
        )
    return sekarang_detik


def jalankan_worker(
    penghenti: threading.Event,
    sesi_pabrik: sessionmaker[Session] | None = None,
    setelan: Settings | None = None,
) -> None:
    """Loop worker: kerjakan job sampai ``penghenti`` diset."""
    setelan = setelan or get_settings()
    sesi_pabrik = sesi_pabrik or get_sessionmaker()
    worker_id = worker_id_untuk()
    try:
        with sesi_pabrik() as sesi:
            perbarui_heartbeat_worker(sesi, worker_id, status=WORKER_MENANGGUR)
            catat_event(
                sesi,
                worker_id=worker_id,
                jenis="worker_mulai",
                pesan=f"Worker {worker_id} mulai",
                setelan=setelan,
            )
            sesi.commit()
        terakhir_pemeliharaan = 0.0
        while not penghenti.is_set():
            try:
                ada_job = proses_satu_job(
                    sesi_pabrik, setelan, penghenti, worker_id
                )
            except Exception:  # noqa: BLE001 - worker jangan mati karena satu galat
                logger.exception("worker gagal mengambil job")
                ada_job = False
            if not ada_job:
                terakhir_pemeliharaan = _pemeliharaan_bila_jeda(
                    setelan, terakhir_pemeliharaan
                )
                penghenti.wait(setelan.worker_poll_detik)
    finally:
        _catat_event_aman(
            sesi_pabrik,
            setelan,
            worker_id=worker_id,
            jenis="worker_berhenti",
            pesan=f"Worker {worker_id} berhenti",
        )
        _set_worker_berhenti(sesi_pabrik, worker_id)
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
    """Titik masuk worker terpisah: ``python -m app.worker --once|--loop``."""
    parser = argparse.ArgumentParser(
        prog="python -m app.worker",
        description="Worker pemroses job Proses A/B.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="ambil paling banyak satu job menunggu, proses, lalu keluar (untuk cron)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="polling terus-menerus (default bila --once tidak diberikan)",
    )
    argumen = parser.parse_args(argv)
    if argumen.once and argumen.loop:
        parser.error("--once dan --loop tidak boleh dipakai bersamaan")

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    setelan = get_settings()
    penghenti = threading.Event()

    def berhenti(_nomor: int, _frame: object) -> None:
        logger.info(
            "sinyal berhenti diterima; menyelesaikan batch lalu keluar"
        )
        penghenti.set()

    signal.signal(signal.SIGINT, berhenti)
    signal.signal(signal.SIGTERM, berhenti)

    if argumen.once:
        diproses = jalankan_sekali(setelan=setelan, penghenti=penghenti)
        logger.info(
            "mode --once selesai: %s",
            "satu job diproses" if diproses else "tidak ada job (atau worker lain berjalan)",
        )
        return

    # Satu service/loop memegang flock selama hidupnya; --once dari cron akan
    # langsung keluar bila service sedang berjalan (dan sebaliknya).
    kunci = KunciBerkas(jalur_kunci(setelan))
    if not kunci.ambil():
        logger.info("worker --loop lain sedang berjalan; keluar")
        return
    try:
        jalankan_worker(penghenti, setelan=setelan)
    finally:
        kunci.lepas()


if __name__ == "__main__":
    main()
