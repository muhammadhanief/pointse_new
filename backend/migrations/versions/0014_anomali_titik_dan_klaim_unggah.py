"""Anomali titik dan rekap berbasis klaim unggahan.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-28

Latar belakang: rekap selama ini memakai ``flag_repair`` hasil hitung ulang
model, sehingga kabupaten yang berkasnya sudah "0 semua" tetap tampil belum
selesai tanpa penjelasan. Dua hal dipisah:

- **rekap** memakai klaim kabupaten: nilai ``flag_repair`` apa adanya dari
  berkas yang diunggah (``titik_hasil.flag_repair_unggah``, kolom baru), dengan
  titik yang hilang/berubah id tetap dihitung belum;
- **anomali** menyimpan rincian titik bermasalah menurut sistem di tabel
  ``anomali_titik`` (menu baru), supaya selisihnya bisa ditelusuri.

``titik_hasil.unique_bang`` ikut disimpan supaya ``assignment_id`` yang berubah
antar unggahan bisa dikenali (dicocokkan lewat identitas bangunan), dan
``runs.anomali_versi`` menandai job B yang anomalinya sudah dihitung.

Backfill ``rekap_target.selesai`` memakai rumus lama (``target - belum -
regresi``) supaya angka historis tidak berubah sebelum job B diproses ulang.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Tambah kolom klaim/identitas, tabel anomali, dan penanda versi."""
    op.add_column(
        "titik_hasil",
        sa.Column("unique_bang", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "titik_hasil",
        sa.Column("flag_repair_unggah", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column(
            "anomali_versi", sa.SmallInteger(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "rekap_target",
        sa.Column("selesai", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        "UPDATE rekap_target SET selesai = "
        "CASE WHEN target - belum - regresi < 0 THEN 0 "
        "ELSE target - belum - regresi END"
    )

    op.create_table(
        "anomali_titik",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_b_id", sa.Integer(), nullable=False),
        sa.Column("run_a_id", sa.Integer(), nullable=True),
        sa.Column("jenis", sa.String(length=24), nullable=False),
        sa.Column("assignment_id", sa.String(length=64), nullable=True),
        sa.Column("assignment_id_baru", sa.String(length=64), nullable=True),
        sa.Column("unique_bang", sa.String(length=64), nullable=True),
        sa.Column("level_6_full_code", sa.String(length=16), nullable=True),
        sa.Column("level_6_full_code_b", sa.String(length=16), nullable=True),
        sa.Column("wilayah_id", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Double(), nullable=True),
        sa.Column("longitude", sa.Double(), nullable=True),
        sa.Column("flag_unggah", sa.SmallInteger(), nullable=True),
        sa.Column("flag_model", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(["run_b_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_a_id"], ["runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["wilayah_id"], ["wilayah.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_anomali_titik_run_jenis",
        "anomali_titik",
        ["run_b_id", "jenis"],
        unique=False,
    )
    op.create_index(
        "ix_anomali_titik_run_kode",
        "anomali_titik",
        ["run_b_id", "level_6_full_code"],
        unique=False,
    )


def downgrade() -> None:
    """Kembalikan skema ke keadaan migrasi 0013."""
    op.drop_index("ix_anomali_titik_run_kode", table_name="anomali_titik")
    op.drop_index("ix_anomali_titik_run_jenis", table_name="anomali_titik")
    op.drop_table("anomali_titik")
    op.drop_column("rekap_target", "selesai")
    op.drop_column("runs", "anomali_versi")
    op.drop_column("titik_hasil", "flag_repair_unggah")
    op.drop_column("titik_hasil", "unique_bang")
