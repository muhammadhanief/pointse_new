"""Tes skrip backfill snapshot level 6 (``scripts/backfill_rekap_subsls.py``)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app import layanan
from app.config import Settings
from app.models import (
    DASAR_TUGAS,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    RekapSubsls,
    Run,
)
from app.worker import proses_satu_job
from scripts import backfill_rekap_subsls as backfill

# Kode Purbalingga supaya uji ini mencerminkan kasus produksi 3303.
KDPROV = "33"
KDKAB = "3303"
TANGGAL = date(2025, 6, 1)

# Peta dua SubSLS di dua kecamatan berbeda, dengan kode kabupaten Purbalingga.
PETA = {
    "A1": {"kdkab": KDKAB, "nmkab": "PURBALINGGA"},
    "A2": {"kdkab": KDKAB, "nmkab": "PURBALINGGA", "kdkec": "330702", "nmkec": "KALIGONDANG"},
}

# A: satu titik benar (flag 0) di A1, satu titik salah SubSLS di A1 (target
# kecamatan 330701), satu titik salah SubSLS di A2 (target kecamatan 330702).
BARIS_A = (
    data_kecil.baris_titik_a("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_a("2", "A2", 0.3, 0.3),
    data_kecil.baris_titik_a("3", "A1", 0.2, 2.2),
)

# B hanya mengunggah wilayah A1 dan semua titiknya sudah benar (flag 0):
# selesai 1 dari target 2 -> status parsial (kecamatan 330702 belum terunggah).
BARIS_B = (
    data_kecil.baris_titik_b("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_b("2", "A1", 0.3, 0.3),
)


def setelan_uji(tmp_path: Path) -> Settings:
    """Setelan worker ringan untuk tes (tanpa anggaran memori)."""
    return Settings(
        dir_unggahan=str(tmp_path / "unggahan"),
        dir_master=str(tmp_path / "master"),
        worker_mem_budget_mb=0,
        worker_lock_file=str(tmp_path / "worker.lock"),
        worker_event_maks=100,
        worker_event_retensi_hari=1,
    )


def buat_run(
    sesi: Session,
    tmp_path: Path,
    *,
    tipe: str,
    baris: tuple[dict[str, Any], ...],
    nama: str,
) -> Run:
    """Tulis berkas masukan kecil lalu simpan run berstatus ``menunggu``."""
    dasar = tmp_path / nama
    if tipe == TIPE_A:
        titik = data_kecil.tulis(
            data_kecil.titik_a(*baris), dasar / "titik.geojson"
        )
    else:
        titik = data_kecil.tulis(
            data_kecil.titik_b(*baris), dasar / "titik.geojson"
        )
    peta = data_kecil.tulis(data_kecil.peta(PETA), dasar / "peta.geojson")
    run = Run(
        tipe=tipe,
        kdprov=KDPROV,
        kdkab=KDKAB,
        status=STATUS_MENUNGGU,
        tanggal_data=TANGGAL,
        nama_file_input=titik.name,
        nama_file_peta=peta.name,
        berkas_input=str(titik),
        berkas_peta=str(peta),
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)
    return run


def snapshot(sesi: Session, run_id: int) -> dict[tuple[str, str, int | None], tuple[int, ...]]:
    """Snapshot isi ``rekap_subsls`` satu run, kunci per dasar/kode/wilayah."""
    hasil: dict[tuple[str, str, int | None], tuple[int, ...]] = {}
    for baris in sesi.scalars(
        select(RekapSubsls).where(RekapSubsls.run_id == run_id)
    ):
        hasil[(baris.dasar, str(baris.level_6_full_code), baris.wilayah_id)] = (
            baris.jumlah,
            baris.belum,
            baris.ditindak_posisi_benar,
            baris.ditindak_posisi_salah,
        )
    return hasil


@pytest.fixture()
def siapkan(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> dict[str, Any]:
    """Proses A lalu B sekali, catat snapshot aslinya, lalu hapus snapshot itu."""
    setelan = setelan_uji(tmp_path)
    run_a = buat_run(sesi, tmp_path, tipe=TIPE_A, baris=BARIS_A, nama="a")
    assert proses_satu_job(sesi_pabrik, setelan)
    sesi.expire_all()
    run_b = buat_run(sesi, tmp_path, tipe=TIPE_B, baris=BARIS_B, nama="b")
    assert proses_satu_job(sesi_pabrik, setelan)
    sesi.expire_all()
    assert run_a.status == STATUS_SUKSES and run_b.status == STATUS_SUKSES

    asli_a = snapshot(sesi, run_a.id)
    asli_b = snapshot(sesi, run_b.id)
    assert asli_a and asli_b

    # Run lama: snapshot level 6 belum pernah dibuat.
    sesi.execute(delete(RekapSubsls))
    sesi.commit()
    return {
        "setelan": setelan,
        "run_a": run_a,
        "run_b": run_b,
        "asli_a": asli_a,
        "asli_b": asli_b,
    }


def test_dry_run_tidak_mengubah_data(
    sesi: Session, siapkan: dict[str, Any]
) -> None:
    """Mode laporan hanya membaca; snapshot tetap kosong."""
    rencana = backfill.susun_rencana(sesi, kabupaten=[KDKAB])
    assert len(rencana) == 1
    satu = rencana[0]
    assert satu.diproses
    assert satu.kdkab == KDKAB
    assert satu.run_a.id == siapkan["run_a"].id
    assert satu.run_b.id == siapkan["run_b"].id
    assert satu.snapshot_a == 0 and satu.snapshot_b == 0
    assert not satu.hilang_a and not satu.hilang_b
    assert backfill.jumlah_snapshot(sesi, satu.run_a.id) == 0


def test_backfill_memulihkan_snapshot_dan_menjaga_run(
    sesi: Session,
    sesi_pabrik: sessionmaker[Session],
    siapkan: dict[str, Any],
) -> None:
    """Backfill Purbalingga: snapshot kembali sama, id/tanggal run tidak berubah."""
    run_a: Run = siapkan["run_a"]
    run_b: Run = siapkan["run_b"]
    id_a, id_b = run_a.id, run_b.id

    log: list[str] = []
    kode = backfill.jalankan(
        siapkan["setelan"],
        kabupaten=[KDKAB],
        sesi_pabrik=sesi_pabrik,
        log=log,
    )
    assert kode == 0, "\n".join(log)

    sesi.expire_all()
    ulang_a = sesi.get(Run, id_a)
    ulang_b = sesi.get(Run, id_b)
    assert ulang_a is not None and ulang_b is not None
    assert ulang_a.status == STATUS_SUKSES
    assert ulang_b.status == STATUS_SUKSES
    assert (ulang_a.id, ulang_a.tanggal_data) == (id_a, TANGGAL)
    assert (ulang_b.id, ulang_b.tanggal_data) == (id_b, TANGGAL)

    assert snapshot(sesi, id_a) == siapkan["asli_a"]
    assert snapshot(sesi, id_b) == siapkan["asli_b"]

    for run in (ulang_a, ulang_b):
        verifikasi = backfill.verifikasi_run(sesi, run)
        assert all(satu.cocok for satu in verifikasi), verifikasi
        assert all(satu.baris > 0 for satu in verifikasi)

    # Angka tabulasi harus konsisten dengan target 2 dan selesai 1 (B parsial).
    tabulasi = layanan.tabulasi_progres(
        sesi, kdprov=KDPROV, kdkab=KDKAB, tingkat="kabupaten", dasar=DASAR_TUGAS
    )
    baris = [satu for satu in tabulasi["baris"] if str(satu["kode"]) == KDKAB]
    assert len(baris) == 1
    assert baris[0]["target"] == 2
    assert baris[0]["selesai"] == 1
    assert baris[0]["sisa"] == 1
    assert baris[0]["status"] == "parsial"
    assert (baris[0]["cakupan_ada"], baris[0]["cakupan_total"]) == (1, 2)


def _tambah_snapshot(sesi: Session, run_id: int) -> None:
    """Satu baris snapshot tiruan untuk menandai run sudah punya level 6."""
    sesi.add(
        RekapSubsls(
            run_id=run_id,
            dasar=DASAR_TUGAS,
            level_6_full_code="A1",
            wilayah_id=None,
            jumlah=1,
            belum=0,
            benar_awal=1,
            ditindak_posisi_benar=0,
            ditindak_posisi_salah=0,
            digeser=0,
            tanpa_wilayah=0,
        )
    )
    sesi.commit()


def test_backfill_melewati_snapshot_lengkap(
    sesi: Session, siapkan: dict[str, Any]
) -> None:
    """Tanpa ``--paksa``, kabupaten yang snapshot A dan B sudah ada dilewati."""
    _tambah_snapshot(sesi, siapkan["run_a"].id)
    # Snapshot A saja belum cukup: B juga harus punya level 6.
    sebagian = backfill.susun_rencana(sesi, kabupaten=[KDKAB])
    assert sebagian[0].diproses

    _tambah_snapshot(sesi, siapkan["run_b"].id)
    rencana = backfill.susun_rencana(sesi, kabupaten=[KDKAB])
    assert rencana[0].lewat is not None
    assert not rencana[0].diproses
    paksa = backfill.susun_rencana(sesi, kabupaten=[KDKAB], paksa=True)
    assert paksa[0].diproses


def test_berkas_hilang_dilewati(
    sesi: Session, siapkan: dict[str, Any]
) -> None:
    """Run yang berkas mentahnya sudah dipangkas tidak diproses ulang."""
    Path(siapkan["run_b"].berkas_input).unlink()
    rencana = backfill.susun_rencana(sesi, kabupaten=[KDKAB])
    assert rencana[0].hilang_b
    assert rencana[0].lewat is not None
    assert not rencana[0].diproses


def test_pilih_run_mengikuti_aturan_tabulasi(sesi: Session) -> None:
    """A = sukses terbaru; B = sukses terbaru setelah A dengan sumber A sama."""
    def tambah(tipe: str, kode: str = KDKAB, sumber: int | None = None) -> Run:
        run = Run(
            tipe=tipe,
            kdprov=KDPROV,
            kdkab=kode,
            status=STATUS_SUKSES,
            tanggal_data=TANGGAL,
            nama_file_input="x.geojson",
            nama_file_peta="p.geojson",
            berkas_input="x.geojson",
            berkas_peta="p.geojson",
            sumber_run_a_id=sumber,
        )
        sesi.add(run)
        sesi.commit()
        sesi.refresh(run)
        return run

    a_lama = tambah(TIPE_A)
    b_sebelum = tambah(TIPE_B)
    a_baru = tambah(TIPE_A, kode="03")
    b_sesudah = tambah(TIPE_B, kode="03", sumber=a_baru.id)
    b_lain = tambah(TIPE_B, kode="03", sumber=a_lama.id)
    assert b_lain.id > b_sesudah.id

    run_a, run_b = backfill.pilih_run(sesi, KDPROV, KDKAB)
    assert run_a is not None and run_a.id == a_baru.id
    assert run_b is not None and run_b.id == b_sesudah.id
    assert b_sebelum.id < a_baru.id
