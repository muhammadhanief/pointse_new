"""Jejak audit aktivitas pengguna.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-21

Menyimpan pelaku (identitas SSO) beserta aksi, objek, dan waktu. Dipakai halaman
Log Aktivitas admin provinsi dan tidak menggantikan otorisasi.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ID_BESAR = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    """Buat tabel aktivitas dan indeks pencarian."""
    op.create_table(
        "aktivitas",
        sa.Column("id", ID_BESAR, autoincrement=True, nullable=False),
        sa.Column("sub", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("nama", sa.String(length=128), nullable=False),
        sa.Column("nip", sa.String(length=32), nullable=True),
        sa.Column("peran", sa.String(length=32), nullable=False),
        sa.Column("kdprov", sa.String(length=4), nullable=False),
        sa.Column("kdkab", sa.String(length=4), nullable=True),
        sa.Column("foto_url", sa.Text(), nullable=True),
        sa.Column("aksi", sa.String(length=32), nullable=False),
        sa.Column("objek", sa.String(length=32), nullable=False),
        sa.Column("objek_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_aktivitas_kdprov_created",
        "aktivitas",
        ["kdprov", "created_at"],
    )
    op.create_index("ix_aktivitas_created", "aktivitas", ["created_at"])


def downgrade() -> None:
    """Hapus tabel aktivitas."""
    op.drop_index("ix_aktivitas_created", table_name="aktivitas")
    op.drop_index("ix_aktivitas_kdprov_created", table_name="aktivitas")
    op.drop_table("aktivitas")
