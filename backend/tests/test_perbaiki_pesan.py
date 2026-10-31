"""Tes skrip perapian pesan galat lama (``scripts/perbaiki_pesan.py``)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import STATUS_GAGAL, TIPE_B, Run
from scripts.perbaiki_pesan import PENANDA, perbaiki_pesan_lama

MENTAH = (
    "(pymysql.err.OperationalError) (1364, \"Field 'assignment_id' doesn't have "
    "a default value\")\n[SQL: INSERT INTO titik_hasil ...]"
)


def buat_run(sesi: Session, pesan: str | None) -> Run:
    run = Run(
        tipe=TIPE_B,
        kdprov="33",
        kdkab="3307",
        nama_file_input="3307_geotagging_1.geojson",
        nama_file_peta="3307_peta.geojson",
        berkas_input="/tmp/a.geojson",
        berkas_peta="/tmp/b.geojson",
        status=STATUS_GAGAL,
        pesan=pesan,
    )
    sesi.add(run)
    sesi.commit()
    return run


def test_pratinjau_tidak_mengubah_pesan(sesi: Session) -> None:
    """Tanpa ``terapkan`` hanya menghitung, pesan di DB tetap mentah."""
    run = buat_run(sesi, MENTAH)

    hasil = perbaiki_pesan_lama(sesi)

    assert [run_id for run_id, _ in hasil] == [run.id]
    sesi.refresh(run)
    assert run.pesan == MENTAH


def test_terapkan_menambah_penjelasan_dan_menyertakan_mentah(sesi: Session) -> None:
    """Pesan baru menjelaskan kolom hilang, teks mentah tetap ada."""
    run = buat_run(sesi, MENTAH)

    perbaiki_pesan_lama(sesi, terapkan=True)

    sesi.refresh(run)
    assert run.pesan is not None
    assert "Kolom wajib 'assignment_id' tidak terisi" in run.pesan
    assert "berkas Proses B (3307_geotagging_1.geojson)" in run.pesan
    assert PENANDA in run.pesan
    assert MENTAH in run.pesan


def test_aman_dijalankan_berulang(sesi: Session) -> None:
    """Pesan yang sudah berpenjelasan tidak diproses lagi."""
    run = buat_run(sesi, MENTAH)
    perbaiki_pesan_lama(sesi, terapkan=True)
    sesi.refresh(run)
    sesudah = run.pesan

    assert perbaiki_pesan_lama(sesi, terapkan=True) == []

    sesi.refresh(run)
    assert run.pesan == sesudah


def test_pesan_tak_dikenal_dibiarkan(sesi: Session) -> None:
    """Galat di luar pola yang dikenal tidak diubah."""
    run = buat_run(sesi, "berkas rusak")

    assert perbaiki_pesan_lama(sesi, terapkan=True) == []

    sesi.refresh(run)
    assert run.pesan == "berkas rusak"
