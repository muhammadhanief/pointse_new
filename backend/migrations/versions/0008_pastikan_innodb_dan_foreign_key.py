"""Pastikan tabel MySQL memakai InnoDB dan foreign key lengkap.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20

Beberapa instalasi MySQL/MariaDB cPanel masih memakai MyISAM sebagai default.
MyISAM menerima ``CREATE TABLE`` dengan foreign key tetapi constraint-nya
diabaikan. Migrasi ini mengubah tabel ke InnoDB dan menambahkan foreign key
yang belum ada. Aman dijalankan pada database yang foreign key-nya sudah ada.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TABEL = (
    "runs",
    "wilayah",
    "geotag_master",
    "titik_hasil",
    "rekap_desa",
    "rekap_kabupaten",
)


def _foreign_key_ada(tabel: str, kolom: tuple[str, ...]) -> bool:
    # Mode offline (``alembic upgrade --sql``) tidak punya koneksi untuk
    # diinspeksi; biarkan FK ditulis dan andalkan database yang menolaknya
    # bila sudah ada. Mode online tetap memeriksa agar aman diulang.
    if op.get_context().as_sql:
        return False
    inspektur = sa.inspect(op.get_bind())
    for fk in inspektur.get_foreign_keys(tabel):
        if tuple(fk["constrained_columns"]) == kolom:
            return True
    return False


def _tambah_fk(
    nama: str,
    tabel: str,
    kolom: list[str],
    tabel_tujuan: str,
    kolom_tujuan: list[str],
    ondelete: str | None = None,
) -> None:
    if _foreign_key_ada(tabel, tuple(kolom)):
        return
    op.create_foreign_key(
        nama,
        tabel,
        tabel_tujuan,
        kolom,
        kolom_tujuan,
        ondelete=ondelete,
    )


def upgrade() -> None:
    """Ubah tabel ke InnoDB lalu lengkapi foreign key yang belum ada."""
    dialek = op.get_context().dialect.name
    if dialek not in ("mysql", "mariadb"):
        return

    for tabel in TABEL:
        op.execute(sa.text(f"ALTER TABLE {tabel} ENGINE=InnoDB"))

    _tambah_fk(
        "fk_runs_geotag_master_id",
        "runs",
        ["geotag_master_id"],
        "geotag_master",
        ["id"],
        "SET NULL",
    )
    _tambah_fk(
        "fk_runs_sumber_run_a_id",
        "runs",
        ["sumber_run_a_id"],
        "runs",
        ["id"],
        "SET NULL",
    )
    _tambah_fk(
        "fk_titik_hasil_run_id",
        "titik_hasil",
        ["run_id"],
        "runs",
        ["id"],
        "CASCADE",
    )
    _tambah_fk(
        "fk_titik_hasil_wilayah_asal_id",
        "titik_hasil",
        ["wilayah_asal_id"],
        "wilayah",
        ["id"],
    )
    _tambah_fk(
        "fk_titik_hasil_wilayah_edit_id",
        "titik_hasil",
        ["wilayah_edit_id"],
        "wilayah",
        ["id"],
    )
    _tambah_fk(
        "fk_rekap_desa_run_id",
        "rekap_desa",
        ["run_id"],
        "runs",
        ["id"],
        "CASCADE",
    )
    _tambah_fk(
        "fk_rekap_kabupaten_run_id",
        "rekap_kabupaten",
        ["run_id"],
        "runs",
        ["id"],
        "CASCADE",
    )


def downgrade() -> None:
    """Tidak mengembalikan InnoDB/FK karena migrasi ini bersifat perbaikan."""
