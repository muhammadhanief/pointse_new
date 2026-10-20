"""Fixture bersama tes backend.

Tes tidak butuh server MySQL: tabel dibuat dari model ORM di SQLite sementara
(:func:`app.db.buat_engine`). Worker tidak dinyalakan otomatis; tes memanggil
:func:`app.worker.proses_satu_job` langsung supaya hasilnya deterministik.
"""

from __future__ import annotations

import os

# Harus diset SEBELUM app.main diimpor (setelan dibaca sekali lalu di-cache).
os.environ["WORKER_ENABLED"] = "false"
os.environ["ENV"] = "development"
# Tes memakai pengguna dev longgar; tes autentikasi mengaktifkannya sendiri.
os.environ["AUTH_MODE"] = "dev"

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.db import Base, buat_engine, get_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def mesin(tmp_path: Path) -> Iterator[Engine]:
    """Engine SQLite sementara, tabel dibuat dari model ORM."""
    mesin = buat_engine(
        f"sqlite+pysqlite:///{tmp_path / 'uji.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    # WAL supaya sesi pemeriksa dan worker bisa jalan berdampingan di tes.
    @event.listens_for(mesin, "connect")
    def _siapkan_koneksi(koneksi: object, _rekaman: object) -> None:
        kursor = koneksi.cursor()  # type: ignore[attr-defined]
        kursor.execute("PRAGMA journal_mode=WAL")
        kursor.execute("PRAGMA busy_timeout=10000")
        kursor.close()

    Base.metadata.create_all(mesin)
    yield mesin
    mesin.dispose()


@pytest.fixture()
def sesi_pabrik(mesin: Engine) -> sessionmaker[Session]:
    """Pabrik sesi untuk basis data uji."""
    return sessionmaker(bind=mesin, expire_on_commit=False)


@pytest.fixture()
def sesi(sesi_pabrik: sessionmaker[Session]) -> Iterator[Session]:
    """Satu sesi untuk memeriksa isi basis data di dalam tes."""
    with sesi_pabrik() as satu:
        yield satu


@pytest.fixture()
def dir_unggahan(tmp_path: Path) -> Path:
    """Folder unggahan khusus tes."""
    tujuan = tmp_path / "unggahan"
    tujuan.mkdir()
    return tujuan


@pytest.fixture()
def dir_master(tmp_path: Path) -> Path:
    """Folder geotag master khusus tes."""
    tujuan = tmp_path / "master"
    tujuan.mkdir()
    return tujuan


@pytest.fixture()
def setelan(dir_unggahan: Path, dir_master: Path) -> Settings:
    """Setelan aplikasi untuk tes (worker mati, unggahan ke folder tes)."""
    return Settings(
        worker_enabled=False,
        auth_mode="dev",
        dir_unggahan=str(dir_unggahan),
        dir_master=str(dir_master),
        worker_lock_file=str(dir_unggahan.parent / "worker-test.lock"),
    )


@pytest.fixture()
def klien(
    sesi_pabrik: sessionmaker[Session], setelan: Settings
) -> Iterator[TestClient]:
    """TestClient dengan basis data dan setelan tes."""

    def sesi_uji() -> Iterator[Session]:
        with sesi_pabrik() as satu:
            yield satu

    app.dependency_overrides[get_session] = sesi_uji
    app.dependency_overrides[get_settings] = lambda: setelan
    with TestClient(app) as klien_uji:
        yield klien_uji
    app.dependency_overrides.clear()
