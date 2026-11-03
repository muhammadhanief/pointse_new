"""Validasi SLS: bedakan temuan level SLS vs SubSLS.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-04

Kode yang sama bisa dinilai di dua level (mis. kode 16 digit tertulis di
kolom ``idsls`` peta sekaligus di kolom ``idsubsls``); tanpa penanda level,
daftar unduhan CSV menampilkan dua baris yang tampak identik. Kolom baru
``validasi_sls_unmatch.level`` (``sls``/``subsls``) menandai granularitas
tiap baris dan ikut diunduh sebagai kolom CSV kedua.

Backfill: baris lama 14 digit = ``sls``, selainnya = ``subsls``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Tambah ``validasi_sls_unmatch.level`` + backfill dari panjang kode."""
    op.add_column(
        "validasi_sls_unmatch",
        sa.Column("level", sa.String(length=8), nullable=False, server_default="sls"),
    )
    op.execute(
        sa.text(
            "UPDATE validasi_sls_unmatch SET level = 'subsls' "
            "WHERE LENGTH(idsls) <> 14"
        )
    )


def downgrade() -> None:
    """Hapus kolom ``level``."""
    op.drop_column("validasi_sls_unmatch", "level")
