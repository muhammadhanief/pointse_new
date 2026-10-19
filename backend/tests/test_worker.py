"""Tes worker Proses A/B: klaim job, batch penyimpanan, penggantian hasil, gagal."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app import worker as modul_worker
from app.config import Settings
from app.models import (
    STATUS_DIGANTIKAN,
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    Run,
    TitikHasil,
)
from app.worker import UKURAN_BATCH, klaim_job, kueri_klaim, mulai_worker, proses_satu_job

BARIS_A = (
    data_kecil.baris_titik_a("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_a("2", "A1", 0.3, 0.3),
    data_kecil.baris_titik_a("3", "A1", 0.5, 2.5),
)

# Masukan Proses B: satu titik apa adanya, satu digeser pindah SubSLS, satu
# digeser tapi atribut flag_repair-nya sudah diubah manual.
BARIS_B = (
    data_kecil.baris_titik_b("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_b("2", "A1", 0.3, 0.3, latitude=0.9, longitude=2.5),
    data_kecil.baris_titik_b("3", "A1", 0.4, 0.4, flag_repair_initial=1, flag_repair=0),
)


def buat_job(
    sesi: Session,
    tmp_path: Path,
    *,
    tipe: str = TIPE_A,
    kdkab: str = "3307",
    nama: str = "job",
    baris: tuple[dict[str, Any], ...] | None = None,
) -> Run:
    """Tulis berkas masukan kecil lalu buat baris ``runs`` berstatus menunggu."""
    dasar = tmp_path / nama
    if tipe == TIPE_A:
        titik = data_kecil.tulis(data_kecil.titik_a(*(baris or BARIS_A)), dasar / "titik.geojson")
    else:
        titik = data_kecil.tulis(data_kecil.titik_b(*(baris or BARIS_B)), dasar / "titik.geojson")
    peta = data_kecil.tulis(data_kecil.peta(), dasar / "peta.geojson")

    run = Run(
        tipe=tipe,
        kdkab=kdkab,
        status=STATUS_MENUNGGU,
        nama_file_input=titik.name,
        nama_file_peta=peta.name,
        berkas_input=str(titik),
        berkas_peta=str(peta),
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)
    return run


def baris_hasil(sesi: Session, run_id: int) -> list[TitikHasil]:
    """Ambil baris hasil satu job, urut sesuai keluaran proses."""
    return list(
        sesi.scalars(
            select(TitikHasil).where(TitikHasil.run_id == run_id).order_by(TitikHasil.id)
        )
    )


def test_ukuran_batch_penyimpanan_sepuluh_ribu() -> None:
    """Hasil disimpan per batch 10.000 baris (PRD §8)."""
    assert UKURAN_BATCH == 10_000


def test_kueri_klaim_mysql_memakai_skip_locked() -> None:
    """Kueri klaim memakai FOR UPDATE SKIP LOCKED dan menyaring status/kdkab."""
    sql = " ".join(str(kueri_klaim().compile(dialect=mysql.dialect())).split())

    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "runs.status" in sql
    assert "NOT (EXISTS" in sql


def test_proses_a_menyimpan_hasil_dan_status_sukses(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Worker Proses A: status sukses, jumlah baris, dan isi hasil benar."""
    job = buat_job(sesi, tmp_path)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True

    sesi.refresh(job)
    assert job.status == STATUS_SUKSES, job.pesan
    assert job.jumlah_baris == 3
    assert job.started_at is not None and job.finished_at is not None

    hasil = baris_hasil(sesi, job.id)
    assert [baris.assignment_id for baris in hasil] == ["1", "2", "3"]

    pertama = hasil[0]
    assert pertama.idsubsls_origin == "A1"
    assert pertama.flag_repair == 0 and pertama.flag_repair_initial == 0
    assert pertama.latitude_origin == 0.2 and pertama.longitude_origin == 0.2
    assert pertama.kk == 1 and pertama.btt == 1 and pertama.bku == 0
    assert pertama.kode_bang_value == "2"
    assert pertama.no_bang == "0001"
    assert pertama.nama_usaha_bang is None
    # kolom khusus Proses B tetap kosong untuk job Proses A
    assert pertama.flag_position is None and pertama.latitude_edited is None

    ketiga = hasil[2]
    assert ketiga.idsubsls_origin == "A2"
    assert ketiga.flag_repair == 1


def test_proses_b_menghitung_flag_penggeseran(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Worker Proses B: flag_position, flag_edit_atr_repair, dan SubSLS hasil edit."""
    job = buat_job(sesi, tmp_path, tipe=TIPE_B)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.refresh(job)
    assert job.status == STATUS_SUKSES, job.pesan

    hasil = {baris.assignment_id: baris for baris in baris_hasil(sesi, job.id)}
    assert set(hasil) == {"1", "2", "3"}

    apa_adanya = hasil["1"]
    assert apa_adanya.flag_position == 0
    assert apa_adanya.flag_edit_atr_repair == 0
    assert apa_adanya.flag_repair_initial == 0
    assert apa_adanya.flag_repair == 0
    assert apa_adanya.idsubsls_edited == "A1"

    digeser = hasil["2"]
    assert digeser.flag_position == 1
    assert digeser.latitude_edited == 0.9
    assert digeser.longitude_edited == 2.5
    assert digeser.idsubsls_edited == "A2"
    assert digeser.flag_repair_initial == 1
    assert digeser.flag_repair == 1
    assert digeser.flag_edit_atr_repair == 0

    diedit_manual = hasil["3"]
    assert diedit_manual.flag_edit_atr_repair == 1
    assert diedit_manual.flag_position == 0
    assert diedit_manual.flag_repair == 0


def test_job_gagal_kalau_berkas_hilang(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Berkas masukan hilang: status gagal, pesan dicatat, hasil dibersihkan."""
    job = buat_job(sesi, tmp_path)
    Path(job.berkas_input).unlink()
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True

    sesi.refresh(job)
    assert job.status == STATUS_GAGAL
    assert job.pesan, "pesan galat harus dicatat di runs.pesan"
    assert job.finished_at is not None
    assert baris_hasil(sesi, job.id) == []


def test_penyimpanan_memakai_batch(
    sesi: Session,
    sesi_pabrik: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Hasil yang lebih banyak dari ukuran batch tetap tersimpan lengkap."""
    baris = tuple(
        data_kecil.baris_titik_a(str(nomor), "A1", 0.1 + nomor / 100, 0.5)
        for nomor in range(1, 6)
    )
    monkeypatch.setattr(modul_worker, "UKURAN_BATCH", 2)
    job = buat_job(sesi, tmp_path, baris=baris)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True

    sesi.refresh(job)
    assert job.jumlah_baris == 5
    assert len(baris_hasil(sesi, job.id)) == 5


def test_job_antre_lama_digantikan_saat_klaim(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Job terbaru untuk (kdkab, tipe) yang dikerjakan; job antre lama dibatalkan."""
    lama = buat_job(sesi, tmp_path, nama="lama")
    id_lama, id_baru = lama.id, buat_job(sesi, tmp_path, nama="baru").id
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    # job terbaru (id lebih besar) yang jalan dan hasilnya tersimpan
    assert sesi.get(Run, id_baru).status == STATUS_SUKSES
    assert len(baris_hasil(sesi, id_baru)) == 3
    # job antre yang lama ditandai digantikan, tanpa hasil
    assert sesi.get(Run, id_lama).status == STATUS_DIGANTIKAN
    assert baris_hasil(sesi, id_lama) == []
    # tidak ada job menunggu lagi
    assert proses_satu_job(sesi_pabrik) is False


def test_hasil_job_lama_digantikan_oleh_job_baru(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Job baru untuk kabupaten/tipe sama menggantikan hasil job lama."""
    lama = buat_job(sesi, tmp_path, nama="lama")
    sesi.rollback()
    assert proses_satu_job(sesi_pabrik) is True

    baru = buat_job(sesi, tmp_path, nama="baru")
    sesi.rollback()
    assert proses_satu_job(sesi_pabrik) is True

    sesi.expire_all()
    assert sesi.get(Run, baru.id).status == STATUS_SUKSES
    assert sesi.get(Run, lama.id).status == STATUS_DIGANTIKAN
    assert baris_hasil(sesi, lama.id) == []
    assert len(baris_hasil(sesi, baru.id)) == 3


def test_klaim_melewati_job_yang_sedang_jalan(sesi: Session, tmp_path: Path) -> None:
    """Job dengan (kdkab, tipe) yang sedang jalan tidak diambil lagi."""
    sedang = buat_job(sesi, tmp_path, nama="sedang", kdkab="3307")
    sedang.status = STATUS_JALAN
    lain_kabupaten = buat_job(sesi, tmp_path, nama="lain", kdkab="3308")
    sesi.commit()

    diambil = klaim_job(sesi)
    assert diambil is not None and diambil.id == lain_kabupaten.id
    assert diambil.status == STATUS_JALAN


def test_klaim_tidak_ada_job(
    sesi: Session, sesi_pabrik: sessionmaker[Session]
) -> None:
    """Tanpa job antre, klaim mengembalikan None dan ``proses_satu_job`` False."""
    assert klaim_job(sesi) is None
    assert proses_satu_job(sesi_pabrik) is False


def test_mulai_worker_membuat_thread_sesuai_max_workers(
    sesi_pabrik: sessionmaker[Session], setelan: Settings, monkeypatch: Any
) -> None:
    """MAX_WORKERS menentukan jumlah thread worker yang dinyalakan."""
    monkeypatch.setattr(modul_worker, "get_sessionmaker", lambda: sesi_pabrik)
    setelan = setelan.model_copy(update={"max_workers": 2, "interval_polling": 0.05})

    benang, penghenti = mulai_worker(setelan)
    try:
        assert len(benang) == 2
        assert all(satu.is_alive() for satu in benang)
    finally:
        penghenti.set()
        for satu in benang:
            satu.join(timeout=5)

    assert not any(satu.is_alive() for satu in benang)
