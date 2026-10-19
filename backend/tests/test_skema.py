"""Tes skema basis data: model ORM, migrasi Alembic, dan kesesuaian kolom hasil."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import buat_engine
from app.models import RekapSubsls, Run, TitikHasil, Wilayah
from app.proses_a import KOLOM_HASIL
from app.proses_b import KOLOM_HASIL_B

AKAR_BACKEND = Path(__file__).resolve().parents[1]

# Kolom ``titik_hasil`` yang disimpan (dipakai dashboard + peta/ekspor).
KOLOM_TITIK_HASIL: tuple[str, ...] = (
    "run_id",
    "urut",
    "assignment_id",
    "level_6_full_code",
    "wilayah_asal_id",
    "wilayah_edit_id",
    "flag_psls",
    "flag_position",
    "flag_edit_atr_repair",
    "flag_repair_initial",
    "flag_repair",
    "kk",
    "btt",
    "bku",
    "bttk",
    "bbtt",
    "usaha",
    "latitude_origin",
    "longitude_origin",
    "latitude_edited",
    "longitude_edited",
)

# Kolom keluaran Proses A/B yang sengaja tidak disimpan (atribut bangunan dan
# nama/kode wilayah yang sudah dinormalkan ke tabel ``wilayah``).
KOLOM_DIBUANG = (
    "unique_bang",
    "idsubsls_origin",
    "idsubsls_edited",
    "no_bang",
    "kode_bang_value",
    "ada_keluarga_value",
    "ada_bang_usaha_value",
    "jumlah_usaha_ditemukan",
    "kdprov",
    "nmprov",
    "kdkab",
    "nmkab",
    "kdkec",
    "nmkec",
    "kddesa",
    "nmdesa",
    "nmsls",
    "nama_usaha_bang",
)


def test_kolom_titik_hasil_ramping() -> None:
    """``titik_hasil`` hanya memuat kolom yang disepakati (urutan sama)."""
    assert tuple(TitikHasil.__table__.columns.keys()) == KOLOM_TITIK_HASIL
    for nama in KOLOM_DIBUANG:
        assert nama not in TitikHasil.__table__.columns


def test_semua_kolom_keluaran_proses_diputuskan() -> None:
    """Tiap kolom keluaran Proses A/B disimpan atau masuk daftar dibuang."""
    keluaran = set(KOLOM_HASIL) | set(KOLOM_HASIL_B)
    tersimpan = set(TitikHasil.__table__.columns.keys())
    assert keluaran - tersimpan == set(KOLOM_DIBUANG)
    assert tersimpan <= keluaran | {"run_id", "urut", "wilayah_asal_id", "wilayah_edit_id"}


def test_kunci_tabel_titik_hasil_wilayah_dan_rekap() -> None:
    """Kunci utama titik_hasil = (run_id, urut); rekap_subsls berkunci ``id``.

    ``rekap_subsls.wilayah_id`` boleh NULL (baris kategori "(tanpa wilayah)"), jadi
    kunci utamanya tidak bisa memuat kolom itu (MySQL tidak mengizinkan kolom kunci
    utama bernilai NULL) — kombinasi ``(run_id, dasar, wilayah_id)`` dijaga UNIQUE.
    """
    assert [kolom.name for kolom in TitikHasil.__table__.primary_key] == ["run_id", "urut"]
    assert [kolom.name for kolom in RekapSubsls.__table__.primary_key] == ["id"]
    assert RekapSubsls.__table__.columns["wilayah_id"].nullable
    assert not RekapSubsls.__table__.columns["dasar"].nullable

    def batasan_unik(tabel: object, nama: str) -> set[tuple[str, ...]]:
        return {
            tuple(kolom.name for kolom in batasan.columns)
            for batasan in tabel.__table__.constraints  # type: ignore[attr-defined]
            if batasan.name == nama
        }

    assert batasan_unik(Wilayah, "uq_wilayah_idsubsls") == {("idsubsls",)}
    assert batasan_unik(RekapSubsls, "uq_rekap_subsls_run_dasar_wilayah") == {
        ("run_id", "dasar", "wilayah_id")
    }


def test_kolom_koordinat_pakai_double() -> None:
    """Koordinat disimpan DOUBLE supaya presisi 7-8 angka tidak hilang."""
    for nama in ("latitude_origin", "longitude_origin", "latitude_edited", "longitude_edited"):
        assert TitikHasil.__table__.columns[nama].type.__class__.__name__ == "Double"


def test_flag_pakai_tinyint_di_mysql() -> None:
    """Kolom flag/indikator disimpan TINYINT di MySQL (angka kecil)."""
    for nama in ("flag_repair", "flag_psls", "flag_position", "kk", "bttk"):
        tipe = str(TitikHasil.__table__.columns[nama].type.compile(dialect=mysql.dialect()))
        assert tipe == "TINYINT", f"{nama} dikompilasi jadi {tipe}"


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
            TitikHasil(run_id=run.id, urut=0, assignment_id="1"),
            TitikHasil(run_id=run.id, urut=1, assignment_id="1"),
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

    assert "CREATE TABLE wilayah" in sql
    assert "CREATE TABLE rekap_subsls" in sql
    assert "CREATE TABLE titik_hasil" in sql
    assert "ALTER TABLE runs ADD COLUMN jumlah_tanpa_wilayah INTEGER" in sql
    assert "assignment_id VARCHAR(64) NOT NULL" in sql
    assert "level_6_full_code VARCHAR(16)" in sql
    assert "flag_repair TINYINT" in sql
    assert "usaha SMALLINT" in sql
    assert "latitude_origin DOUBLE" in sql
    assert "CONSTRAINT uq_wilayah_idsubsls UNIQUE (idsubsls)" in sql
    assert "CONSTRAINT uq_titik_hasil_run_assignment UNIQUE (run_id, assignment_id)" in sql
    assert "PRIMARY KEY (run_id, urut)" in sql
    assert "FOREIGN KEY(wilayah_asal_id) REFERENCES wilayah (id)" in sql
    assert "FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE" in sql
    assert "CREATE INDEX ix_titik_hasil_run_flag_repair ON titik_hasil (run_id, flag_repair)" in sql
    # migrasi 0003: hitungan rekap dipisah dan wilayah_id boleh NULL
    assert "sudah_posisi INTEGER NOT NULL" in sql
    assert "sudah_manual INTEGER NOT NULL" in sql
    assert "tanpa_wilayah INTEGER NOT NULL" in sql
    assert "CONSTRAINT uq_rekap_subsls_run_dasar_wilayah UNIQUE (run_id, dasar, wilayah_id)" in sql
    assert "PRIMARY KEY (id)" in sql


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
        assert {"runs", "wilayah", "titik_hasil", "rekap_subsls"} <= set(
            pemeriksa.get_table_names()
        )

        for tabel, model in (
            ("titik_hasil", TitikHasil),
            ("runs", Run),
            ("wilayah", Wilayah),
            ("rekap_subsls", RekapSubsls),
        ):
            assert {kolom["name"] for kolom in pemeriksa.get_columns(tabel)} == set(
                model.__table__.columns.keys()
            )
            assert pemeriksa.get_pk_constraint(tabel)["constrained_columns"] == [
                kolom.name for kolom in model.__table__.primary_key
            ]

        indeks = {indeks["name"] for indeks in pemeriksa.get_indexes("titik_hasil")}
        assert {
            "ix_titik_hasil_wilayah_asal",
            "ix_titik_hasil_wilayah_edit",
            "ix_titik_hasil_run_flag_repair",
        } <= indeks
        assert "uq_titik_hasil_run_assignment" in {
            unik["name"] for unik in pemeriksa.get_unique_constraints("titik_hasil")
        }
        assert "uq_wilayah_idsubsls" in {
            unik["name"] for unik in pemeriksa.get_unique_constraints("wilayah")
        }
    finally:
        mesin.dispose()

    # Downgrade juga jalan (mengembalikan skema ke kosong).
    command.downgrade(konfigurasi, "base")
    mesin = buat_engine(url)
    try:
        sisa = set(inspect(mesin).get_table_names())
        assert "titik_hasil" not in sisa and "wilayah" not in sisa
        assert "rekap_subsls" not in sisa
    finally:
        mesin.dispose()
