"""Konfirmasi pencermatan titik anomali.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-01

Anomali tidak wajib habis, tetapi tiap temuan harus dijelaskan kabupaten/kota
lewat konfirmasi ("Akan Diperbaiki" / "Sesuai Kondisi Kenyataan"). Konfirmasi
disimpan di tabel baru ``konfirmasi_anomali`` dengan kunci stabil antar run
(``jenis | assignment_id | unique_bang``), jadi penjelasan yang sudah dibuat
tetap berlaku saat run B berikutnya memunculkan temuan yang sama.

Tabel ini hanya **lapisan penjelasan** di atas ``anomali_titik``; rekap progres
tetap memakai klaim kabupaten (``titik_hasil.flag_repair_unggah``) dan tidak
terpengaruh. Migrasi ini additive: tidak mengubah tabel yang sudah ada.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0017"
down_revision = "0016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ID_BESAR = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
ANGKA_KECIL = sa.SmallInteger().with_variant(mysql.TINYINT(), "mysql")


def upgrade() -> None:
    """Buat tabel ``konfirmasi_anomali`` beserta indeksnya."""
    op.create_table(
        "konfirmasi_anomali",
        sa.Column("id", ID_BESAR, primary_key=True, autoincrement=True),
        sa.Column("kdprov", sa.String(4), nullable=False),
        sa.Column("kdkab", sa.String(4), nullable=False),
        sa.Column("kunci", sa.String(191), nullable=False),
        sa.Column("jenis", sa.String(24), nullable=False),
        sa.Column("assignment_id", sa.String(64), nullable=True),
        sa.Column("unique_bang", sa.String(64), nullable=True),
        sa.Column("level_6_full_code", sa.String(16), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("kategori_alasan", sa.String(32), nullable=True),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("perlu_klarifikasi", ANGKA_KECIL, nullable=False),
        sa.Column("klarifikasi_catatan", sa.Text(), nullable=True),
        sa.Column("klarifikasi_oleh", sa.String(128), nullable=True),
        sa.Column("klarifikasi_pada", sa.DateTime(), nullable=True),
        sa.Column("run_b_id", sa.Integer(), nullable=True),
        sa.Column("sub", sa.String(128), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("nama", sa.String(128), nullable=False),
        sa.Column("nip", sa.String(32), nullable=True),
        sa.Column("peran", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_b_id"], ["runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("kdprov", "kdkab", "kunci", name="uq_konfirmasi_anomali_kunci"),
    )
    op.create_index(
        "ix_konfirmasi_anomali_kab_status",
        "konfirmasi_anomali",
        ["kdprov", "kdkab", "status"],
    )
    op.create_index("ix_konfirmasi_anomali_run", "konfirmasi_anomali", ["run_b_id"])


def downgrade() -> None:
    """Hapus tabel ``konfirmasi_anomali``."""
    op.drop_index("ix_konfirmasi_anomali_run", table_name="konfirmasi_anomali")
    op.drop_index("ix_konfirmasi_anomali_kab_status", table_name="konfirmasi_anomali")
    op.drop_table("konfirmasi_anomali")
