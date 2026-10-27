"""Tabel capaian B terhadap target A per ``assignment_id`` (rekap_target).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-27

Latar belakang: ``rekap_subsls`` membandingkan **jumlah titik per kode** antara A
dan B. Kalau operator mengubah ``level_6_full_code`` di berkas B (dilarang, tapi
terjadi di lapangan), kode asal kehilangan titik dan targetnya tidak pernah
terpenuhi walau titiknya sudah dikerjakan.

``rekap_target`` menyimpan hasil pencocokan per ``assignment_id``: titik target
dari A dicari di B, wilayahnya tetap mengikuti kode penugasan A (``dasar=tugas``)
atau posisi hasil join B (``dasar=posisi``). Titik yang bukan target A tetapi
masih ``flag_repair=1`` di B dicatat sebagai ``regresi`` (kerusakan baru) dan
mengurangi capaian.

Tidak ada backfill: job B lama sudah kehilangan titik ``flag_repair=0`` di
``titik_hasil``, sehingga pencocokan per ``assignment_id`` tidak bisa dibangun
ulang. Job lama tetap memakai hitungan lama; job B baru otomatis terisi.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel rekap_target beserta indeks baca per run B/dasar."""
    op.create_table(
        "rekap_target",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_b_id", sa.Integer(), nullable=False),
        sa.Column("run_a_id", sa.Integer(), nullable=True),
        sa.Column("dasar", sa.String(length=8), nullable=False),
        sa.Column("level_6_full_code", sa.String(length=16), nullable=True),
        sa.Column("wilayah_id", sa.Integer(), nullable=True),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("belum", sa.Integer(), nullable=False),
        sa.Column("hilang", sa.Integer(), nullable=False),
        sa.Column("regresi", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["run_b_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_a_id"], ["runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["wilayah_id"], ["wilayah.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rekap_target_run_b_dasar",
        "rekap_target",
        ["run_b_id", "dasar"],
        unique=False,
    )


def downgrade() -> None:
    """Hapus tabel capaian per assignment."""
    op.drop_index("ix_rekap_target_run_b_dasar", table_name="rekap_target")
    op.drop_table("rekap_target")
