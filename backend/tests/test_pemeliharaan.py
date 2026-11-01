"""Tes modul ``app.pemeliharaan``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app.config import Settings
from app.models import (
    TIPE_A,
    STATUS_SUKSES,
    Run,
    TitikHasil,
)
from app.pemeliharaan import (
    KunciPemeliharaan,
    jalankan,
    jalankan_pemeliharaan,
    pangkas_run,
    rampingkan_run,
)
from app.worker import proses_satu_job

BARIS_A: tuple[dict[str, Any], ...] = (
    data_kecil.baris_titik_a("1", "A1", 0.1, 0.5),
    data_kecil.baris_titik_a("2", "A1", 0.2, 0.5),
    data_kecil.baris_titik_a("3", "A1", 0.5, 2.5),
)


def buat_job(
    sesi: Session,
    tmp_path: Path,
    *,
    nama: str = "job",
    kdkab: str = "3307",
) -> Run:
    dasar = tmp_path / nama
    titik = data_kecil.tulis(data_kecil.titik_a(*BARIS_A), dasar / "titik.geojson")
    peta = data_kecil.tulis(data_kecil.peta(), dasar / "peta.geojson")
    run = Run(
        tipe=TIPE_A,
        kdprov="33",
        kdkab=kdkab,
        nama_file_input="titik.geojson",
        nama_file_peta="peta.geojson",
        berkas_input=str(titik),
        berkas_peta=str(peta),
    )
    sesi.add(run)
    sesi.commit()
    return run


def jumlah_baris(sesi: Session, run_id: int) -> int:
    return int(
        sesi.scalar(
            select(TitikHasil.urut).where(TitikHasil.run_id == run_id).limit(1)
        )
        is not None
        and sesi.scalar(
            select(TitikHasil).where(TitikHasil.run_id == run_id).subquery().count()
        )
        or 0
    )


def hitung_baris(sesi: Session, run_id: int) -> int:
    from sqlalchemy import func

    return int(
        sesi.scalar(
            select(func.count())
            .select_from(TitikHasil)
            .where(TitikHasil.run_id == run_id)
        )
        or 0
    )


def test_rampingkan_run_menyisakan_hanya_perlu_perhatian(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``rampingkan_run`` membuang titik benar_awal, menyisakan perlu perhatian."""
    job = buat_job(sesi, tmp_path)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    # Sebelum: 3 baris.
    assert hitung_baris(sesi, job.id) == 3

    rampingkan_run(sesi, job.id)
    sesi.expire_all()

    # Sesudah: hanya titik perlu perhatian (1 baris).
    assert hitung_baris(sesi, job.id) == 1
    assert sesi.get(Run, job.id).titik_ramping == 1
    assert sesi.get(Run, job.id).detail_tersedia == 1


def test_pangkas_run_menghapus_semua_baris(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``pangkas_run`` menghapus seluruh baris dan set ``detail_tersedia=0``."""
    job = buat_job(sesi, tmp_path)
    sesi.rollback()
    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    pangkas_run(sesi, job.id)
    sesi.expire_all()

    assert hitung_baris(sesi, job.id) == 0
    assert sesi.get(Run, job.id).detail_tersedia == 0


def test_jalankan_menyimpan_baseline_dan_terakhir(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Pemeliharaan menyimpan baseline + terakhir, menghapus tengah."""
    ids = [buat_job(sesi, tmp_path, nama=f"j{i}").id for i in range(3)]
    sesi.rollback()

    for _ in range(3):
        assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    ringkasan = jalankan(sesi)
    sesi.expire_all()

    pertama, tengah, terakhir = ids
    assert tengah in ringkasan.run_dipangkas
    assert pertama in ringkasan.run_dirampingkan
    assert terakhir in ringkasan.run_dirampingkan

    assert sesi.get(Run, pertama).detail_tersedia == 1
    assert sesi.get(Run, tengah).detail_tersedia == 0
    assert sesi.get(Run, terakhir).detail_tersedia == 1

    assert hitung_baris(sesi, pertama) > 0
    assert hitung_baris(sesi, tengah) == 0
    assert hitung_baris(sesi, terakhir) > 0


def test_jalankan_idempoten(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Putaran kedua tidak mengubah apa pun."""
    for i in range(2):
        buat_job(sesi, tmp_path, nama=f"j{i}")
    sesi.rollback()
    for _ in range(2):
        assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    pertama = jalankan(sesi)
    sesi.expire_all()
    kedua = jalankan(sesi)
    sesi.expire_all()

    assert kedua.run_dipangkas == []
    assert kedua.run_dirampingkan == []
    assert kedua.baris_dihapus == 0


def test_jalankan_kabupaten_berbeda_terpisah(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Run kabupaten/kota berbeda dipangkas terpisah."""
    buat_job(sesi, tmp_path, nama="kab1", kdkab="3301")
    buat_job(sesi, tmp_path, nama="kab2", kdkab="3302")
    sesi.rollback()

    for _ in range(2):
        assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    ringkasan = jalankan(sesi)

    # Kedua run adalah run pertama+terakhir kabupaten masing-masing → dirampingkan.
    assert ringkasan.run_dipangkas == []
    assert len(ringkasan.run_dirampingkan) == 2


def test_jalankan_pemeliharaan_memakai_kunci(
    sesi_pabrik: sessionmaker[Session], setelan: Settings
) -> None:
    """``jalankan_pemeliharaan`` mengembalikan ringkasan dan melepas kuncinya."""
    ringkasan = jalankan_pemeliharaan(setelan, sesi_pabrik=sesi_pabrik)

    assert ringkasan is not None
    assert ringkasan.run_dipangkas == []
    # Kunci sudah dilepas: pemanggilan berikutnya tidak terhalang.
    assert jalankan_pemeliharaan(setelan, sesi_pabrik=sesi_pabrik) is not None


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl hanya tersedia di POSIX")
def test_kunci_menolak_proses_kedua(tmp_path: Path) -> None:
    """Proses kedua tidak boleh memangkas bersamaan (lock file)."""
    pertama = KunciPemeliharaan(tmp_path)
    kedua = KunciPemeliharaan(tmp_path)
    assert pertama.ambil() is True
    try:
        assert kedua.ambil() is False
    finally:
        pertama.lepas()

    # Setelah dilepas, proses berikutnya boleh masuk.
    assert kedua.ambil() is True
    kedua.lepas()


def test_batas_membatasi_jumlah_run_per_putaran(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``batas`` membagi pekerjaan besar ke beberapa putaran."""
    for i in range(3):
        buat_job(sesi, tmp_path, nama=f"j{i}")
    sesi.rollback()
    for _ in range(3):
        assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    pertama = jalankan(sesi, batas=1)
    assert len(pertama.run_dipangkas) + len(pertama.run_dirampingkan) == 1

    kedua = jalankan(sesi, batas=10)
    assert len(kedua.run_dipangkas) + len(kedua.run_dirampingkan) == 2
