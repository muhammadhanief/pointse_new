"""Tes mode hemat memori (``PROSES_CHUNK_TITIK``), heartbeat, dan worker cron.

Mode potongan harus menghasilkan baris yang **identik** dengan mode biasa:
jumlah baris, urutan ``urut`` (termasuk celah setelah pemangkasan), nilai semua
flag, wilayah, dan rekap per desa. Termasuk dedup ``assignment_id`` yang muncul
di potongan berbeda.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app.config import Settings
from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_B,
    WORKER_JALAN,
    Run,
    TitikHasil,
    sekarang,
)
from app.kunci import KunciBerkas, jalur_kunci
from app.worker import (
    PESAN_DIHENTIKAN,
    PESAN_TERHENTI,
    jalankan_sekali,
    perbarui_heartbeat_worker,
    proses_satu_job,
    tandai_job_terhenti,
)
from test_worker import (
    BARIS_B,
    baris_hasil,
    buat_job,
    kode_wilayah,
    rekap_desa,
    rekap_kabupaten,
)

# Enam titik, ``assignment_id`` "9" muncul dua kali di potongan berbeda:
# kemunculan di A2 (flag_repair 1) lalu di A1 (flag_repair 0). Yang menang harus
# yang A1 karena lebih awal pada urutan hasil, walau disisipkan belakangan.
BARIS_POTONGAN = (
    data_kecil.baris_titik_a("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_a("9", "A1", 0.5, 2.5),
    data_kecil.baris_titik_a("2", "A1", 0.3, 0.3),
    data_kecil.baris_titik_a("9", "A1", 0.4, 0.4),
    data_kecil.baris_titik_a("3", "A1", 0.5, 5.5),
    data_kecil.baris_titik_a("4", "A1", 0.6, 0.6),
)


def ringkasan_hasil(sesi: Session, run_id: int) -> list[tuple[object, ...]]:
    """Nilai baris ``titik_hasil`` satu run, urut ``urut`` (wilayah jadi kode)."""
    return [
        (
            baris.urut,
            baris.assignment_id,
            baris.level_6_full_code,
            kode_wilayah(sesi, baris.wilayah_asal_id),
            kode_wilayah(sesi, baris.wilayah_edit_id),
            baris.flag_psls,
            baris.flag_position,
            baris.flag_edit_atr_repair,
            baris.flag_repair_initial,
            baris.flag_repair,
            baris.kk,
            baris.btt,
            baris.bku,
            baris.bttk,
            baris.bbtt,
            baris.usaha,
            baris.latitude_origin,
            baris.longitude_origin,
            baris.latitude_edited,
            baris.longitude_edited,
        )
        for baris in baris_hasil(sesi, run_id)
    ]


def test_mode_potongan_identik_dengan_mode_biasa(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Mode potongan = mode biasa: hasil, urut (celah), dan rekap sama."""
    normal = buat_job(sesi, tmp_path, nama="normal", baris=BARIS_POTONGAN)
    potong = buat_job(sesi, tmp_path, nama="potong", baris=BARIS_POTONGAN)

    assert proses_satu_job(sesi_pabrik, Settings(proses_chunk_titik=0)) is True
    assert proses_satu_job(sesi_pabrik, Settings(proses_chunk_titik=2)) is True
    sesi.expire_all()

    job_normal = sesi.get(Run, normal.id)
    job_potong = sesi.get(Run, potong.id)
    assert job_normal is not None and job_potong is not None
    assert job_normal.status == job_potong.status == STATUS_SUKSES
    assert job_normal.jumlah_baris == job_potong.jumlah_baris == 5
    assert job_normal.jumlah_tanpa_wilayah == job_potong.jumlah_tanpa_wilayah == 1

    # "9" yang menang adalah baris A1 (benar_awal), bukan baris A2 yang tersisip
    # lebih dulu. Titik yang perlu perhatian tinggal "3" (di luar poligon) dan
    # urutnya tetap celah posisi penuh (4), sama seperti mode biasa.
    assert ringkasan_hasil(sesi, normal.id) == ringkasan_hasil(sesi, potong.id)
    hasil = baris_hasil(sesi, potong.id)
    assert [satu.assignment_id for satu in hasil] == ["3"]
    assert hasil[0].urut == 4
    assert hasil[0].flag_repair == 1

    for dasar in (DASAR_TUGAS, DASAR_POSISI):
        assert rekap_desa(sesi, normal.id, dasar) == rekap_desa(sesi, potong.id, dasar)
        assert rekap_kabupaten(sesi, normal.id, dasar) == rekap_kabupaten(
            sesi, potong.id, dasar
        )

    # Rekap posisi: empat titik di A1, satu titik "(tanpa wilayah)".
    posisi = rekap_desa(sesi, potong.id, DASAR_POSISI)
    assert sum(satu.jumlah for satu in posisi.values()) == 5
    assert posisi[None].jumlah == 1
    assert posisi[data_kecil.DESA["A1"]["kddesa"]].jumlah == 4


def test_mode_potongan_proses_b(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Mode potongan juga berlaku untuk Proses B (termasuk rekap)."""
    normal = buat_job(
        sesi, tmp_path, tipe=TIPE_B, nama="normal_b", baris=BARIS_B
    )
    potong = buat_job(
        sesi, tmp_path, tipe=TIPE_B, nama="potong_b", baris=BARIS_B
    )

    assert proses_satu_job(sesi_pabrik, Settings(proses_chunk_titik=0)) is True
    assert proses_satu_job(sesi_pabrik, Settings(proses_chunk_titik=2)) is True
    sesi.expire_all()

    job_normal = sesi.get(Run, normal.id)
    job_potong = sesi.get(Run, potong.id)
    assert job_normal is not None and job_potong is not None
    assert job_normal.status == job_potong.status == STATUS_SUKSES
    assert job_normal.jumlah_baris == job_potong.jumlah_baris == len(BARIS_B)
    assert ringkasan_hasil(sesi, normal.id) == ringkasan_hasil(sesi, potong.id)
    for dasar in (DASAR_TUGAS, DASAR_POSISI):
        assert rekap_desa(sesi, normal.id, dasar) == rekap_desa(sesi, potong.id, dasar)


def test_heartbeat_diperbarui_saat_job_sukses(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Job yang selesai punya ``started_at``/``heartbeat_at``/``finished_at``."""
    job = buat_job(sesi, tmp_path, nama="heartbeat")
    assert proses_satu_job(sesi_pabrik, Settings(proses_chunk_titik=2)) is True
    sesi.expire_all()

    run = sesi.get(Run, job.id)
    assert run is not None
    assert run.started_at is not None
    assert run.heartbeat_at is not None
    assert run.finished_at is not None
    assert run.heartbeat_at >= run.started_at


def test_job_jalan_yang_sehat_tidak_disentuh(
    sesi: Session, tmp_path: Path
) -> None:
    """Heartbeat baru + dipegang worker hidup: job bukan job menggantung."""
    job = buat_job(sesi, tmp_path, nama="sehat")
    job.status = STATUS_JALAN
    job.started_at = sekarang()
    job.heartbeat_at = sekarang()
    perbarui_heartbeat_worker(sesi, "w-sehat", status=WORKER_JALAN, run_id=job.id)
    sesi.commit()

    assert tandai_job_terhenti(sesi, Settings(job_timeout_menit=10)) == []
    assert sesi.get(Run, job.id).status == STATUS_JALAN  # type: ignore[union-attr]


def test_job_menggantung_ditandai_gagal_dan_hasilnya_dibersihkan(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Job ``jalan`` yang heartbeat-nya kedaluwarsa tidak menghalangi job baru."""
    lama = buat_job(sesi, tmp_path, nama="lama")
    lama.status = STATUS_JALAN
    lama.started_at = sekarang() - timedelta(minutes=20)
    lama.heartbeat_at = sekarang() - timedelta(minutes=20)
    lama.detail_tersedia = 1
    sesi.add(TitikHasil(run_id=lama.id, urut=0, assignment_id="sisa"))
    sesi.commit()

    baru = buat_job(sesi, tmp_path, nama="baru")
    # Job baru untuk kabupaten/tipe yang sama harus tetap bisa diproses.
    assert proses_satu_job(sesi_pabrik, Settings(job_timeout_menit=10)) is True
    sesi.expire_all()

    run_lama = sesi.get(Run, lama.id)
    run_baru = sesi.get(Run, baru.id)
    assert run_lama is not None and run_baru is not None
    assert run_lama.status == STATUS_GAGAL
    assert run_lama.pesan == PESAN_TERHENTI
    assert run_lama.detail_tersedia == 0
    assert run_baru.status == STATUS_SUKSES
    assert (
        sesi.scalar(
            select(func.count())
            .select_from(TitikHasil)
            .where(TitikHasil.run_id == lama.id)
        )
        == 0
    )


def test_jalankan_sekali_memproses_satu_job_per_panggilan(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``--once`` mengambil satu job per pemanggilan lalu keluar."""
    satu = buat_job(sesi, tmp_path, nama="sekali1")
    dua = buat_job(sesi, tmp_path, nama="sekali2")
    setelan = Settings(
        proses_chunk_titik=0,
        worker_lock_file=str(tmp_path / "worker.lock"),
    )

    assert jalankan_sekali(sesi_pabrik, setelan) is True
    sesi.expire_all()
    assert sesi.get(Run, satu.id).status == STATUS_SUKSES  # type: ignore[union-attr]
    assert sesi.get(Run, dua.id).status == STATUS_MENUNGGU  # type: ignore[union-attr]

    assert jalankan_sekali(sesi_pabrik, setelan) is True
    sesi.expire_all()
    assert sesi.get(Run, dua.id).status == STATUS_SUKSES  # type: ignore[union-attr]

    assert jalankan_sekali(sesi_pabrik, setelan) is False


def test_kunci_berkas_eksklusif_dan_mudah_dilepas(tmp_path: Path) -> None:
    """Dua worker tidak boleh memegang berkas kunci yang sama."""
    setelan = Settings(worker_lock_file=str(tmp_path / "worker.lock"))
    assert jalur_kunci(setelan) == tmp_path / "worker.lock"

    pertama = KunciBerkas(jalur_kunci(setelan))
    kedua = KunciBerkas(jalur_kunci(setelan))
    assert pertama.ambil() is True
    assert kedua.ambil() is False
    pertama.lepas()
    assert kedua.ambil() is True
    kedua.lepas()


def test_sigterm_mengembalikan_job_ke_antrean(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """SIGTERM saat job jalan tidak menandai gagal; job bisa diulang."""
    run = buat_job(sesi, tmp_path, nama="dihentikan")
    setelan = Settings(proses_chunk_titik=2)
    penghenti = threading.Event()
    penghenti.set()

    assert proses_satu_job(sesi_pabrik, setelan, penghenti) is True
    sesi.expire_all()
    ulang = sesi.get(Run, run.id)
    assert ulang is not None
    assert ulang.status == STATUS_MENUNGGU
    assert ulang.pesan == PESAN_DIHENTIKAN
    assert ulang.started_at is None
    assert ulang.heartbeat_at is None
    assert ulang.jumlah_baris == 0
    assert (
        sesi.scalar(
            select(func.count())
            .select_from(TitikHasil)
            .where(TitikHasil.run_id == run.id)
        )
        == 0
    )
