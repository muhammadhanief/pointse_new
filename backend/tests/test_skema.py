"""Tes skema basis data: model ORM, migrasi Alembic, dan kesesuaian kolom hasil."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import buat_engine
from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    KOLOM_HITUNGAN,
    GeotagMaster,
    RekapDesa,
    RekapKabupaten,
    Run,
    TitikHasil,
    Wilayah,
)
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
    """Kunci tabel hasil & rekap: ``titik_hasil`` (run_id, urut), ``rekap_desa`` ``id``.

    ``rekap_desa`` menyimpan baris kategori "(tanpa wilayah)" dengan kode NULL, jadi
    kunci utamanya memakai ``id`` (MySQL tidak mengizinkan kolom kunci utama NULL);
    kombinasi ``(run_id, dasar, kdprov, kdkab, kdkec, kddesa)`` dijaga UNIQUE.
    ``rekap_kabupaten`` selalu berkode (satu baris per run+dasar), jadi kuncinya
    gabungan tanpa tabel bantuan.
    """
    assert [kolom.name for kolom in TitikHasil.__table__.primary_key] == ["run_id", "urut"]
    assert [kolom.name for kolom in RekapDesa.__table__.primary_key] == ["id"]
    assert RekapDesa.__table__.columns["kdprov"].nullable
    assert RekapDesa.__table__.columns["kddesa"].nullable
    assert not RekapDesa.__table__.columns["dasar"].nullable

    assert [kolom.name for kolom in RekapKabupaten.__table__.primary_key] == [
        "run_id",
        "dasar",
        "kdprov",
        "kdkab",
    ]
    for nama in ("kdprov", "kdkab", "dasar"):
        assert not RekapKabupaten.__table__.columns[nama].nullable

    def batasan_unik(tabel: object, nama: str) -> set[tuple[str, ...]]:
        return {
            tuple(kolom.name for kolom in batasan.columns)
            for batasan in tabel.__table__.constraints  # type: ignore[attr-defined]
            if batasan.name == nama
        }

    assert batasan_unik(Wilayah, "uq_wilayah_idsubsls") == {("idsubsls",)}
    assert batasan_unik(RekapDesa, "uq_rekap_desa_run_dasar_desa") == {
        ("run_id", "dasar", "kdprov", "kdkab", "kdkec", "kddesa")
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
    """Default env: satu worker, worker menyala, folder unggahan/master terpisah."""
    assert Settings.model_fields["max_workers"].default == 1
    assert Settings.model_fields["worker_enabled"].default is True
    assert Settings.model_fields["dir_unggahan"].default == "data/unggahan"
    assert Settings.model_fields["dir_master"].default == "data/master"


def test_assignment_id_unik_per_job(sesi: Session) -> None:
    """Satu ``assignment_id`` hanya boleh muncul sekali per job."""
    run = Run(
        tipe="A",
        kdprov="33",
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
    # migrasi 0003/0004: hitungan rekap dipisah, wilayah_id boleh NULL
    assert "ditindak_posisi_benar INTEGER NOT NULL" in sql
    assert "ditindak_posisi_salah INTEGER NOT NULL" in sql
    assert "benar_awal INTEGER NOT NULL" in sql
    assert "digeser INTEGER NOT NULL" in sql
    assert "tanpa_wilayah INTEGER NOT NULL" in sql
    assert "CONSTRAINT uq_rekap_subsls_run_dasar_wilayah UNIQUE (run_id, dasar, wilayah_id)" in sql
    assert "PRIMARY KEY (id)" in sql
    # migrasi 0005: kdprov + tanggal data di runs, rekap desa/kabupaten, rekap_subsls dihapus
    assert "ALTER TABLE runs ADD COLUMN kdprov VARCHAR(4)" in sql
    assert "ALTER TABLE runs ADD COLUMN tanggal_data DATE" in sql
    assert "ALTER TABLE runs ADD COLUMN detail_tersedia TINYINT" in sql
    assert (
        "CREATE INDEX ix_runs_kdprov_kdkab_tipe_tanggal ON runs (kdprov, kdkab, tipe, tanggal_data)"
        in sql
    )
    assert "CREATE TABLE rekap_desa" in sql
    assert "CREATE TABLE rekap_kabupaten" in sql
    assert (
        "CONSTRAINT uq_rekap_desa_run_dasar_desa UNIQUE "
        "(run_id, dasar, kdprov, kdkab, kdkec, kddesa)" in sql
    )
    assert "PRIMARY KEY (run_id, dasar, kdprov, kdkab)" in sql
    assert (
        "CREATE INDEX ix_rekap_kabupaten_kab_dasar_run ON rekap_kabupaten "
        "(kdprov, kdkab, dasar, run_id)" in sql
    )
    # isi data dilewati di mode offline; tabel rekap_subsls lama dihapus
    assert "DROP TABLE rekap_subsls" in sql
    # migrasi 0006: heartbeat job + urut BIGINT untuk kunci sementara mode potongan
    assert "ALTER TABLE runs ADD COLUMN heartbeat_at DATETIME" in sql
    assert "ALTER TABLE titik_hasil MODIFY urut BIGINT NOT NULL" in sql
    # migrasi 0007: geotag master permanen + sumber run A untuk Proses B
    assert "CREATE TABLE geotag_master" in sql
    assert "ALTER TABLE runs ADD COLUMN geotag_master_id INTEGER" in sql
    assert "ALTER TABLE runs ADD COLUMN sumber_run_a_id INTEGER" in sql
    assert (
        "CREATE INDEX ix_geotag_master_kdprov_kdkab ON geotag_master (kdprov, kdkab)"
        in sql
    )
    assert "FOREIGN KEY(geotag_master_id) REFERENCES geotag_master (id)" in sql
    assert "FOREIGN KEY(sumber_run_a_id) REFERENCES runs (id)" in sql


def test_migrasi_0005_mengisi_rekap_dari_data_lama(tmp_path: Path) -> None:
    """Migrasi 0005 mengisi rekap desa/kabupaten run lama tanpa memproses ulang.

    Data lama dibangun persis seperti skema 0004 (termasuk snapshot
    ``rekap_subsls``), lalu di-upgrade: angka rekapnya harus sama dengan snapshot
    lama, ``titik_hasil`` dirampingkan, ``rekap_subsls`` dihapus, dan
    ``runs.kdprov``/``tanggal_data`` diisi dari data yang ada.
    """
    url = f"sqlite+pysqlite:///{tmp_path / 'migrasi_lama.sqlite3'}"
    konfigurasi = Config(str(AKAR_BACKEND / "alembic.ini"))
    konfigurasi.set_main_option("script_location", str(AKAR_BACKEND / "migrations"))
    konfigurasi.set_main_option("sqlalchemy.url", url)
    command.upgrade(konfigurasi, "0004")

    mesin = buat_engine(url)
    try:
        # Lima titik: dua benar_awal, satu belum (posisi beda), satu tanpa wilayah,
        # satu ditindak manual (posisi benar menurut hasil edit).
        with mesin.begin() as koneksi:
            koneksi.execute(
                text(
                    "INSERT INTO wilayah (id, idsubsls, idsls, nmsls, kdprov, nmprov, "
                    "kdkab, nmkab, kdkec, nmkec, kddesa, nmdesa) VALUES "
                    "(1, 'A1', 'S1', 'SLS 001', '33', 'JAWA TENGAH', '07', 'WONOSOBO', "
                    "'010', 'MOJOTENGAH', '001', 'KALIBEBER'), "
                    "(2, 'A2', 'S1', 'SLS 001', '33', 'JAWA TENGAH', '07', 'WONOSOBO', "
                    "'010', 'MOJOTENGAH', '002', 'MOJOTENGAH')"
                )
            )
            koneksi.execute(
                text(
                    "INSERT INTO runs (id, tipe, kdkab, status, nama_file_input, "
                    "nama_file_peta, berkas_input, berkas_peta, jumlah_baris, created_at, "
                    "finished_at) VALUES (4, 'A', '07', 'sukses', 'titik.geojson', "
                    "'peta.geojson', 'data/unggahan/4/titik.geojson', "
                    "'data/unggahan/4/peta.geojson', 5, '2026-03-04 05:06:07', "
                    "'2026-03-04 05:07:08')"
                )
            )
            koneksi.execute(
                text(
                    "INSERT INTO titik_hasil (run_id, urut, assignment_id, "
                    "level_6_full_code, wilayah_asal_id, wilayah_edit_id, flag_repair, "
                    "flag_edit_atr_repair, flag_repair_initial) VALUES "
                    "(4, 0, '1', 'A1', 1, NULL, 0, NULL, NULL), "
                    "(4, 1, '2', 'A1', 1, NULL, 0, NULL, NULL), "
                    "(4, 2, '3', 'A1', 2, NULL, 1, NULL, NULL), "
                    "(4, 3, '4', 'A1', NULL, NULL, 1, NULL, NULL), "
                    "(4, 4, '5', 'A1', 1, 2, 0, 1, 0)"
                )
            )
            koneksi.execute(
                text(
                    "INSERT INTO rekap_subsls (run_id, wilayah_id, dasar, jumlah, belum, "
                    "ditindak_posisi_benar, ditindak_posisi_salah, benar_awal, digeser, "
                    "tanpa_wilayah) VALUES "
                    "(4, 1, 'tugas', 5, 2, 1, 0, 2, 0, 1), "
                    "(4, 1, 'posisi', 2, 0, 0, 0, 2, 0, 0), "
                    "(4, 2, 'posisi', 2, 1, 1, 0, 0, 0, 0), "
                    "(4, NULL, 'posisi', 1, 1, 0, 0, 0, 0, 1)"
                )
            )

        command.upgrade(konfigurasi, "head")

        with Session(mesin) as sesi:
            run = sesi.get(Run, 4)
            assert run is not None
            # kdprov diisi dari tabel wilayah; tanggal_data dari created_at
            assert run.kdprov == "33"
            assert run.tanggal_data == date(2026, 3, 4)
            # hanya baseline = sukses terakhir (satu-satunya run) yang disimpan
            assert run.detail_tersedia == 1

            def rekap(dasar: str) -> dict[tuple[str, ...], tuple[int, ...]]:
                return {
                    (
                        "" if satu.kdprov is None else satu.kdprov,
                        "" if satu.kdkab is None else satu.kdkab,
                        "" if satu.kdkec is None else satu.kdkec,
                        "" if satu.kddesa is None else satu.kddesa,
                    ): (
                        satu.jumlah,
                        satu.belum,
                        satu.benar_awal,
                        satu.ditindak_posisi_benar,
                        satu.ditindak_posisi_salah,
                        satu.digeser,
                        satu.tanpa_wilayah,
                    )
                    for satu in sesi.scalars(
                        select(RekapDesa).where(RekapDesa.run_id == 4, RekapDesa.dasar == dasar)
                    )
                }

            # sama dengan snapshot rekap_subsls lama, hanya dijumlahkan per desa
            assert rekap(DASAR_TUGAS) == {
                ("33", "07", "010", "001"): (5, 2, 2, 1, 0, 0, 1)
            }
            assert rekap(DASAR_POSISI) == {
                ("33", "07", "010", "001"): (2, 0, 2, 0, 0, 0, 0),
                ("33", "07", "010", "002"): (2, 1, 0, 1, 0, 0, 0),
                ("", "", "", ""): (1, 1, 0, 0, 0, 0, 1),
            }

            # rekap_kabupaten = jumlah rekap_desa tiap dasar
            for dasar in (DASAR_TUGAS, DASAR_POSISI):
                kabupaten = sesi.execute(
                    select(*[getattr(RekapKabupaten, nama) for nama in KOLOM_HITUNGAN]).where(
                        RekapKabupaten.run_id == 4, RekapKabupaten.dasar == dasar
                    )
                ).one()
                desa = rekap(dasar)
                for kolom, nilai in zip(KOLOM_HITUNGAN, kabupaten):
                    assert nilai == sum(satu[KOLOM_HITUNGAN.index(kolom)] for satu in desa.values())
            assert sesi.scalar(
                select(RekapKabupaten.kdprov).where(RekapKabupaten.run_id == 4).limit(1)
            ) == "33"

            # titik_hasil: hanya yang perlu perhatian (benar_awal dipangkas)
            tersisa = [
                satu.assignment_id
                for satu in sesi.scalars(
                    select(TitikHasil)
                    .where(TitikHasil.run_id == 4)
                    .order_by(TitikHasil.urut)
                )
            ]
            assert tersisa == ["3", "4", "5"]

        sisa_tabel = set(inspect(mesin).get_table_names())
        assert "rekap_subsls" not in sisa_tabel
        assert {"rekap_desa", "rekap_kabupaten"} <= sisa_tabel
    finally:
        mesin.dispose()


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
        assert {
            "runs",
            "wilayah",
            "titik_hasil",
            "rekap_desa",
            "rekap_kabupaten",
            "geotag_master",
        } <= set(pemeriksa.get_table_names())
        assert "rekap_subsls" not in set(pemeriksa.get_table_names())

        for tabel, model in (
            ("titik_hasil", TitikHasil),
            ("runs", Run),
            ("wilayah", Wilayah),
            ("rekap_desa", RekapDesa),
            ("rekap_kabupaten", RekapKabupaten),
            ("geotag_master", GeotagMaster),
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

        # indeks tren & kunci unik rekap hasil migrasi
        assert "ix_runs_kdprov_kdkab_tipe_tanggal" in {
            indeks["name"] for indeks in pemeriksa.get_indexes("runs")
        }
        assert "uq_rekap_desa_run_dasar_desa" in {
            unik["name"] for unik in pemeriksa.get_unique_constraints("rekap_desa")
        }
        assert "ix_rekap_kabupaten_kab_dasar_run" in {
            indeks["name"] for indeks in pemeriksa.get_indexes("rekap_kabupaten")
        }
    finally:
        mesin.dispose()

    # Downgrade juga jalan (mengembalikan skema ke kosong).
    command.downgrade(konfigurasi, "base")
    mesin = buat_engine(url)
    try:
        sisa = set(inspect(mesin).get_table_names())
        assert "titik_hasil" not in sisa and "wilayah" not in sisa
        assert "rekap_subsls" not in sisa and "rekap_desa" not in sisa
        assert "rekap_kabupaten" not in sisa
    finally:
        mesin.dispose()
