"""Penanda perampingan ``titik_hasil`` per run.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-31

Pemangkasan ``titik_hasil`` dipindah keluar jalur job (``app.pemeliharaan``)
supaya transaksi sukses pendek dan dua worker tidak saling menunggu kunci baris.
Kolom ``runs.titik_ramping`` menandai run yang baris "tidak perlu perhatian"-nya
sudah dibuang, agar pemeliharaan berikutnya tidak memindai ulang ratusan ribu
baris.

Run lama dibiarkan ``0``: putaran pemeliharaan pertama akan merampingkannya
sekali, lalu menandainya ``1``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Tambah ``runs.titik_ramping`` (default 0)."""
    op.add_column(
        "runs",
        sa.Column(
            "titik_ramping",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Hapus ``runs.titik_ramping``."""
    op.drop_column("runs", "titik_ramping")
