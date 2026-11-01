"""Jumlah anomali permanen per run Proses B.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-01

Menu anomali kini menyimpan detail ``anomali_titik`` **semua** run B (bukan
hanya run terakhir), supaya tren pencermatan per kabupaten/kota per waktu bisa
dibaca. Kolom ``runs.jumlah_anomali`` menyimpan totalnya per run, termasuk ``0``
saat sudah bersih -- run bersih tidak punya baris ``anomali_titik``, jadi tanpa
kolom ini kondisi "clean" tidak terlihat di tren.

Run lama dibiarkan NULL (belum pernah dihitung); worker akan mengisinya saat job
B berikutnya dijalankan.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Tambah ``runs.jumlah_anomali`` (nullable, run lama NULL)."""
    op.add_column("runs", sa.Column("jumlah_anomali", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Hapus ``runs.jumlah_anomali``."""
    op.drop_column("runs", "jumlah_anomali")
