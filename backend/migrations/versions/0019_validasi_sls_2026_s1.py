"""Validasi peta SLS 2026 Semester 1 (tipe run V).

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-04

Menu validasi (§11 PRD) memakai tipe run baru ``V`` yang steril dari SE2026:
tidak dibaca rekap/progres, tidak ikut hitung nomor job A/B, dan tidak menjadi
sumber peta Proses B.

- ``runs.semester`` (VARCHAR(7), nullable): periode peta yang divalidasi
  (mis. ``2026_1``); NULL untuk run A/B lama.
- Tabel ``validasi_sls_unmatch``: satu baris per ``idsls`` bermasalah per run,
  untuk daftar unduhan CSV dan audit. Ikut terhapus saat run dihapus (CASCADE).

Migrasi additive: kolom nullable, run lama bernilai NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Tambah ``runs.semester`` dan tabel ``validasi_sls_unmatch``."""
    op.add_column("runs", sa.Column("semester", sa.String(length=7), nullable=True))
    op.create_table(
        "validasi_sls_unmatch",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("arah", sa.String(length=8), nullable=False),
        sa.Column("idsls", sa.String(length=16), nullable=False),
        sa.Column("nmsls", sa.String(length=128), nullable=True),
        sa.Column("alasan", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validasi_sls_unmatch_run_arah",
        "validasi_sls_unmatch",
        ["run_id", "arah"],
        unique=False,
    )


def downgrade() -> None:
    """Kembalikan skema ke keadaan migrasi 0018."""
    op.drop_index("ix_validasi_sls_unmatch_run_arah", table_name="validasi_sls_unmatch")
    op.drop_table("validasi_sls_unmatch")
    op.drop_column("runs", "semester")
