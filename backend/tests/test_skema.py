"""Tes skema basis data: model ORM, migrasi Alembic, dan kesesuaian kolom hasil."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import buat_engine
from app.models import Run, TitikHasil
from app.proses_a import KOLOM_HASIL
from app.proses_b import KOLOM_HASIL_B

AKAR_BACKEND = Path(__file__).resolve().parents[1]

# Kolom yang hanya muncul di keluaran Proses B.
KOLOM_KHUSUS_B = {
    "flag_position",
    "flag_edit_atr_repair",
    "idsubsls_edited",
    "latitude_edited",
    "longitude_edited",
}


def test_kolom_titik_hasil_sesuai_keluaran_proses() -> None:
    """Kolom ``titik_hasil`` = gabungan kolom keluaran Proses A dan Proses B."""
    kolom_db = set(TitikHasil.__table__.columns.keys()) - {"id", "run_id"}
    assert kolom_db == set(KOLOM_HASIL_B)
    assert set(KOLOM_HASIL) <= kolom_db
    assert set(KOLOM_HASIL_B) - set(KOLOM_HASIL) == KOLOM_KHUSUS_B


def test_kolom_koordinat_pakai_double() -> None:
    """Koordinat disimpan DOUBLE supaya presisi 7-8 angka tidak hilang."""
    for nama in ("latitude_origin", "longitude_origin", "latitude_edited", "longitude_edited"):
        assert TitikHasil.__table__.columns[nama].type.__class__.__name__ == "Double"


def test_setelan_default() -> None:
    """Default env: satu worker, worker menyala, folder unggahan data/unggahan."""
    assert Settings.model_fields["max_workers"].default == 1
    assert Settings.model_fields["worker_enabled"].default is True
    assert Settings.model_fields["dir_unggahan"].default == "data/unggahan"


def test_assignment_id_unik_per_job(sesi: Session) -> None:
    """Satu ``assignment_id`` hanya boleh muncul sekali per job."""
    run = Run(
        tipe="A",
        kdkab="3307",
        status="menunggu",
        nama_file_input="titik.geojson",
        nama_file_peta="peta.geojson",
        berkas_input="titik.geojson",
        berkas_peta="peta.geojson",
    )
    sesi.add(run)
    sesi.commit()

    sesi.add_all(
        [
            TitikHasil(run_id=run.id, assignment_id="1"),
            TitikHasil(run_id=run.id, assignment_id="1"),
        ]
    )
    with pytest.raises(IntegrityError):
        sesi.commit()
    sesi.rollback()


def test_sql_migrasi_untuk_mysql(capsys: pytest.CaptureFixture[str]) -> None:
    """Migrasi bisa dirender sebagai SQL MySQL (diperiksa tanpa server MySQL)."""
    konfigurasi = Config(str(AKAR_BACKEND / "alembic.ini"))
    konfigurasi.set_main_option("script_location", str(AKAR_BACKEND / "migrations"))
    konfigurasi.set_main_option(
        "sqlalchemy.url", "mysql+pymysql://pengguna:sandi@localhost/pointse"
    )

    command.upgrade(konfigurasi, "head", sql=True)
    sql = " ".join(capsys.readouterr().out.split())

    assert "CREATE TABLE runs" in sql
    assert "CREATE TABLE titik_hasil" in sql
    assert "id BIGINT NOT NULL AUTO_INCREMENT" in sql
    assert "flag_repair SMALLINT" in sql
    assert "latitude_origin DOUBLE" in sql
    assert "assignment_id VARCHAR(64) NOT NULL" in sql
    assert "CONSTRAINT uq_titik_hasil_run_assignment UNIQUE (run_id, assignment_id)" in sql
    assert "FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE" in sql
    assert "CREATE INDEX ix_titik_hasil_kdkab ON titik_hasil (kdkab)" in sql


def test_migrasi_alembic_sesuai_model(tmp_path: Path) -> None:
    """``alembic upgrade head`` menghasilkan skema yang sama dengan model ORM."""
    url = f"sqlite+pysqlite:///{tmp_path / 'migrasi.sqlite3'}"
    konfigurasi = Config(str(AKAR_BACKEND / "alembic.ini"))
    konfigurasi.set_main_option("script_location", str(AKAR_BACKEND / "migrations"))
    konfigurasi.set_main_option("sqlalchemy.url", url)

    command.upgrade(konfigurasi, "head")
    # Gagal kalau model ORM dan hasil migrasi berbeda (pakai autogenerate Alembic).
    command.check(konfigurasi)

    mesin = buat_engine(url)
    try:
        pemeriksa = inspect(mesin)
        assert {"runs", "titik_hasil"} <= set(pemeriksa.get_table_names())

        assert {kolom["name"] for kolom in pemeriksa.get_columns("titik_hasil")} == set(
            TitikHasil.__table__.columns.keys()
        )
        assert {kolom["name"] for kolom in pemeriksa.get_columns("runs")} == set(
            Run.__table__.columns.keys()
        )

        indeks = {indeks["name"] for indeks in pemeriksa.get_indexes("titik_hasil")}
        assert {
            "ix_titik_hasil_assignment_id",
            "ix_titik_hasil_idsubsls_origin",
            "ix_titik_hasil_kdkab",
            "ix_titik_hasil_run_flag_repair",
            "ix_titik_hasil_run_id",
        } <= indeks
        assert "uq_titik_hasil_run_assignment" in {
            unik["name"] for unik in pemeriksa.get_unique_constraints("titik_hasil")
        }
    finally:
        mesin.dispose()

    # Downgrade juga jalan (mengembalikan skema ke kosong).
    command.downgrade(konfigurasi, "base")
    mesin = buat_engine(url)
    try:
        assert "titik_hasil" not in inspect(mesin).get_table_names()
    finally:
        mesin.dispose()
