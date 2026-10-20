"""Tes endpoint status sistem untuk halaman admin."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import auth
from app.kunci import KunciBerkas, baca_pid_kunci
from app.main import app
from app.models import (
    STATUS_JALAN,
    STATUS_MENUNGGU,
    WORKER_JALAN,
    Run,
    WorkerEvent,
    WorkerHeartbeat,
    sekarang,
)
from app.peran import PERAN_PETUGAS_KABKOT, Peran


def _buat_run(sesi: Session, *, status: str = STATUS_MENUNGGU) -> Run:
    """Buat satu job minimal untuk mengisi hitungan antrean."""
    run = Run(
        tipe="A",
        kdprov="33",
        kdkab="3307",
        status=status,
        nama_file_input="titik.geojson",
        nama_file_peta="peta.geojson",
        berkas_input="/tmp/titik.geojson",
        berkas_peta="/tmp/peta.geojson",
    )
    sesi.add(run)
    sesi.commit()
    return run


def test_status_sistem_mengembalikan_metrik(klien: TestClient, sesi: Session) -> None:
    """Endpoint membalas status worker, antrean, RAM, dan disk."""
    _buat_run(sesi)

    resp = klien.get("/sistem/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["worker"]["aktif"] is False
    assert data["worker"]["batas_memori_mb"] >= 0
    assert data["antrean"]["menunggu"] == 1
    assert data["antrean"]["jalan"] == 0
    assert data["antrean"]["total"] >= 1
    assert len(data["job_aktif"]) == 0
    assert data["sistem"]["memori"]["api_rss_mb"] is None or (
        data["sistem"]["memori"]["api_rss_mb"] >= 0
    )
    assert isinstance(data["peringatan"], list)
    assert any("worker tidak aktif" in pesan for pesan in data["peringatan"])


def test_status_sistem_menampilkan_job_jalan_dan_heartbeat(
    klien: TestClient, sesi: Session
) -> None:
    """Job jalan yang heartbeat-nya kedaluwarsa memunculkan peringatan."""
    run = _buat_run(sesi, status=STATUS_JALAN)
    run.started_at = sekarang() - timedelta(minutes=20)
    run.heartbeat_at = run.started_at
    sesi.commit()

    resp = klien.get("/sistem/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["antrean"]["jalan"] == 1
    assert data["job_aktif"][0]["id"] == run.id
    assert data["job_aktif"][0]["umur_heartbeat_detik"] >= 60 * 19
    assert any("melewati batas" in pesan for pesan in data["peringatan"])


def test_status_sistem_menampilkan_heartbeat_event_dan_backup(
    klien: TestClient, sesi: Session, setelan: object, tmp_path: Path
) -> None:
    """Heartbeat, riwayat kejadian, dan status backup ikut dibalas."""
    waktu = sekarang()
    sesi.add(
        WorkerHeartbeat(
            worker_id="uji:1:worker-1",
            pid=1234,
            hostname="uji",
            status=WORKER_JALAN,
            started_at=waktu,
            heartbeat_at=waktu,
        )
    )
    sesi.add(
        WorkerEvent(
            worker_id="uji:1:worker-1",
            level="info",
            jenis="job_klaim",
            pesan="Job 7 mulai",
            created_at=waktu,
        )
    )
    sesi.commit()

    berkas = tmp_path / "status-backup.json"
    berkas.write_text(
        json.dumps(
            {
                "status": "sukses",
                "waktu_mulai": (waktu - timedelta(minutes=5)).isoformat() + "Z",
                "waktu_selesai": waktu.isoformat() + "Z",
                "berkas": "/home/backup/pointse-uji.sql.gz",
                "ukuran_bytes": 2048,
                "pesan": "Backup selesai",
            }
        ),
        encoding="utf-8",
    )
    setelan.backup_status_file = str(berkas)

    resp = klien.get("/sistem/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["heartbeats"][0]["worker_id"] == "uji:1:worker-1"
    assert data["heartbeats"][0]["aktif"] is True
    assert data["kejadian"][0]["jenis"] == "job_klaim"
    assert data["backup"]["status"] == "sukses"
    assert data["backup"]["berkas"] == "pointse-uji.sql.gz"
    assert data["backup"]["ukuran_bytes"] == 2048


def test_status_sistem_hanya_untuk_admin(klien: TestClient) -> None:
    """Petugas kabupaten/kota tidak boleh melihat status server."""
    petugas = auth.Pengguna(
        sub="petugas",
        username="petugas",
        nama="Petugas",
        org="3307",
        peran=Peran(
            nama=PERAN_PETUGAS_KABKOT,
            kdprov="33",
            kdkab="3307",
        ),
    )
    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: petugas
    try:
        resp = klien.get("/sistem/status")
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 403


def test_kunci_menyimpan_pid_untuk_pemantauan(tmp_path: Path) -> None:
    """Isi berkas kunci memberi petunjuk PID tanpa mengubah sifat eksklusif."""
    jalur = tmp_path / "worker.lock"
    kunci = KunciBerkas(jalur)
    assert kunci.ambil() is True
    assert baca_pid_kunci(jalur) == os.getpid()
    kunci.lepas()
