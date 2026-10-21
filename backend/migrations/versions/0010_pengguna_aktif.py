"""Tabel kehadiran pengguna untuk pemantauan admin provinsi.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-21

Shell dashboard mengirim heartbeat berkala ke ``/kehadiran``. Backend menyimpan
satu baris per subjek SSO; admin provinsi membaca daftar ini lewat ``/pengguna``
dan hanya melihat pengguna di provinsinya.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel pengguna_aktif dan indeks pencarian admin."""
    op.create_table(
        "pengguna_aktif",
        sa.Column("sub", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("nama", sa.String(length=128), nullable=False),
        sa.Column("nip", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("org", sa.String(length=8), nullable=False),
        sa.Column("peran", sa.String(length=32), nullable=False),
        sa.Column("kdprov", sa.String(length=4), nullable=False),
        sa.Column("kdkab", sa.String(length=4), nullable=True),
        sa.Column("foto_url", sa.Text(), nullable=True),
        sa.Column("login_pada", sa.DateTime(), nullable=False),
        sa.Column("terakhir_aktif", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("sub"),
    )
    op.create_index(
        "ix_pengguna_aktif_kdprov_terakhir",
        "pengguna_aktif",
        ["kdprov", "terakhir_aktif"],
    )


def downgrade() -> None:
    """Hapus tabel kehadiran pengguna."""
    op.drop_index(
        "ix_pengguna_aktif_kdprov_terakhir",
        table_name="pengguna_aktif",
    )
    op.drop_table("pengguna_aktif")
