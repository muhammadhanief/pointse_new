"""Validasi SLS: temuan sisi-berdampingan + unduhan Excel per jenis.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-04

Laporan unmatch diubah dari satu kode per baris (arah/level) menjadi satu
pasangan per baris dengan sisi peta vs sisi master berdampingan, plus kolom
``jenis`` yang menjadi nama sheet unduhan Excel (``tidak_di_peta`` /
``tidak_di_master`` / ``ganda`` / ``kolom_salah``) dan ``catatan``.
Kolom lama (``arah``, ``level``, ``idsls``, ``alasan``) dihapus; baris yang
ada hanya data uji sehingga tidak ada migrasi data produksi.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Ganti kolom arah/level/idsls/alasan dengan pasangan sisi + jenis."""
    with op.batch_alter_table("validasi_sls_unmatch") as batch:
        batch.drop_index("ix_validasi_sls_unmatch_run_arah")
        batch.drop_column("arah")
        batch.drop_column("level")
        batch.drop_column("idsls")
        batch.drop_column("alasan")
        batch.add_column(sa.Column("jenis", sa.String(length=16), nullable=False, server_default="tidak_di_peta"))
        batch.add_column(sa.Column("idsls_peta", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("idsubsls_peta", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("idsls_master", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("idsubsls_master", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("catatan", sa.String(length=255), nullable=True))
        batch.create_index("ix_validasi_sls_unmatch_run_jenis", ["run_id", "jenis"])


def downgrade() -> None:
    """Kembalikan kolom lama (data temuan tidak dipertahankan)."""
    with op.batch_alter_table("validasi_sls_unmatch") as batch:
        batch.drop_index("ix_validasi_sls_unmatch_run_jenis")
        batch.drop_column("catatan")
        batch.drop_column("idsls_master")
        batch.drop_column("idsubsls_master")
        batch.drop_column("idsls_peta")
        batch.drop_column("idsubsls_peta")
        batch.drop_column("jenis")
        batch.add_column(sa.Column("arah", sa.String(length=8), nullable=False, server_default="peta"))
        batch.add_column(sa.Column("level", sa.String(length=8), nullable=False, server_default="sls"))
        batch.add_column(sa.Column("idsls", sa.String(length=20), nullable=False, server_default=""))
        batch.add_column(sa.Column("alasan", sa.String(length=32), nullable=True))
        batch.create_index("ix_validasi_sls_unmatch_run_arah", ["run_id", "arah"])
