"""Pengaturan aplikasi + antrean jalankan ulang pemeriksaan batas.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-11

Menambahkan dua tabel:

- ``pengaturan``: pasangan kunci-nilai untuk pengaturan yang dapat diubah admin.
  Nilai pertama adalah ``rekonsiliasi_batas_luas_min_m2`` (ambang luas minimum
  temuan Gap/Overlap dalam m2; ``0`` = tanpa filter, identik dengan Topology
  Checker QGIS).
- ``rekonsiliasi_batas_jalankan``: satu baris per permintaan "periksa ulang
  semua pasangan batas" beserta progresnya, dikerjakan worker.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel ``pengaturan`` dan ``rekonsiliasi_batas_jalankan``."""
    op.create_table(
        "pengaturan",
        sa.Column("kunci", sa.String(64), primary_key=True),
        sa.Column("nilai", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=True),
    )

    op.create_table(
        "rekonsiliasi_batas_jalankan",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="menunggu"
        ),
        sa.Column("luas_min_m2", sa.Double(), nullable=False, server_default="0"),
        sa.Column("total_pasang", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "sudah_diproses", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("jumlah_bersih", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "jumlah_belum_clean", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("jumlah_gagal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pesan", sa.Text(), nullable=True),
        sa.Column("diminta_oleh", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_rekonsiliasi_batas_jalankan_status",
        "rekonsiliasi_batas_jalankan",
        ["status"],
    )


def downgrade() -> None:
    """Hapus tabel ``rekonsiliasi_batas_jalankan`` dan ``pengaturan``."""
    op.drop_index(
        "ix_rekonsiliasi_batas_jalankan_status",
        table_name="rekonsiliasi_batas_jalankan",
    )
    op.drop_table("rekonsiliasi_batas_jalankan")
    op.drop_table("pengaturan")