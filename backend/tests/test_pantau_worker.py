"""Tes pembantu skrip pantau worker (tanpa MySQL dan tanpa proses nyata)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    Run,
    sekarang,
)
from scripts import pantau_worker


def test_urai_baris_ps_hanya_worker() -> None:
    """Hanya proses ``app.worker`` yang diambil; grep/pemantau diabaikan."""
    keluaran = "\n".join(
        [
            "101 00:05:12 98.0 12.3 812345 python -m app.worker --once",
            "102 00:00:01  0.0  0.1   1234 grep app.worker",
            "103 00:00:01  0.0  0.1   1234 python scripts/pantau_worker.py",
            "",
        ]
    )
    proses = pantau_worker.urai_baris_ps(keluaran)
    assert [satu.pid for satu in proses] == [101]
    assert proses[0].rss_mb is not None
    assert round(proses[0].rss_mb) == 793


def test_urai_baris_ps_tahan_baris_rusak() -> None:
    """Baris pendek/angka rusak tidak membuat pemantau gagal."""
    assert pantau_worker.urai_baris_ps("bukan keluaran ps\n101 1 2\n") == []


def test_format_durasi() -> None:
    """Durasi ditampilkan ringkas dan tidak negatif."""
    assert pantau_worker.format_durasi(None) == "-"
    assert pantau_worker.format_durasi(timedelta(seconds=12)) == "12s"
    assert pantau_worker.format_durasi(timedelta(minutes=4, seconds=12)) == "4m 12s"
    assert pantau_worker.format_durasi(timedelta(hours=1, minutes=2)) == "1j 02m"
    assert pantau_worker.format_durasi(timedelta(seconds=-5)) == "0s"


def test_format_angka() -> None:
    """Angka memakai titik ribuan; nilai kosong jadi tanda hubung."""
    assert pantau_worker.format_angka(None) == "-"
    assert pantau_worker.format_angka(0) == "0"
    assert pantau_worker.format_angka(397_364) == "397.364"


def test_baca_ekor(tmp_path: Path) -> None:
    """Hanya baris terakhir yang dibaca, termasuk berkas besar."""
    berkas = tmp_path / "worker.log"
    berkas.write_text("\n".join(f"baris-{nomor}" for nomor in range(100)), encoding="utf-8")
    assert pantau_worker.baca_ekor(berkas, 3) == ["baris-97", "baris-98", "baris-99"]
    assert pantau_worker.baca_ekor(tmp_path / "tidak-ada.log", 3) == []
    assert pantau_worker.baca_ekor(berkas, 0) == []


def test_ambil_status_dan_umur(sesi: Session) -> None:
    """Job aktif/antre dan hitungan status dibaca dari basis data uji."""
    for nomor, status in enumerate(
        [STATUS_JALAN, STATUS_MENUNGGU, STATUS_SUKSES, STATUS_GAGAL], start=1
    ):
        sesi.add(
            Run(
                tipe=TIPE_A if nomor % 2 else TIPE_B,
                kdprov="33",
                kdkab="3307",
                status=status,
                nama_file_input=f"input-{nomor}.gpkg",
                nama_file_peta=f"peta-{nomor}.geojson",
                berkas_input=f"/tmp/input-{nomor}.gpkg",
                berkas_peta=f"/tmp/peta-{nomor}.geojson",
            )
        )
    sesi.commit()

    aktif, hitungan, selesai = pantau_worker.ambil_status(sesi)
    assert [run.status for run in aktif] == [STATUS_JALAN, STATUS_MENUNGGU]
    assert hitungan[STATUS_JALAN] == 1
    assert hitungan[STATUS_MENUNGGU] == 1
    assert hitungan[STATUS_SUKSES] == 1
    assert hitungan[STATUS_GAGAL] == 1
    assert [run.status for run in selesai] == [STATUS_GAGAL, STATUS_SUKSES]

    sesi.get(Run, 1).heartbeat_at = sekarang() - timedelta(seconds=5)
    sesi.commit()
    umur = pantau_worker.umur_heartbeat(sesi.get(Run, 1))
    assert umur is not None and umur.total_seconds() >= 4


def test_kunci_worker_tidak_ada_di_sqlite(sesi: Session) -> None:
    """SQLite tidak punya ``IS_USED_LOCK``; pemantau mengembalikan None."""
    assert pantau_worker.kunci_worker(sesi) is None
