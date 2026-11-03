"""Master SLS 2026 S1 pindah ke database.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-04

Menyimpan pasangan (idsls, idsubsls) master per kabupaten di tabel
``master_sls_2026_s1`` supaya validasi dan ringkasan tidak lagi memindai
puluhan berkas Excel setiap kali (pindai penuh 36 kab terbukti >200 detik).
Berkas Excel tetap jadi media transport; isinya dimasukkan lewat perintah
impor ``python -m app.master_impor``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel ``master_sls_2026_s1``."""
    op.create_table(
        "master_sls_2026_s1",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kdprov", sa.String(length=2), nullable=False),
        sa.Column("kdkab", sa.String(length=4), nullable=False),
        sa.Column("idsls", sa.String(length=16), nullable=False),
        sa.Column("idsubsls", sa.String(length=16), nullable=False),
        sa.Column("nmsls", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("kdkab", "idsubsls", name="uq_master_sls_2026_s1_kab_subsls"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_master_sls_2026_s1_kab", "master_sls_2026_s1", ["kdkab"]
    )


def downgrade() -> None:
    """Hapus tabel ``master_sls_2026_s1``."""
    op.drop_index("ix_master_sls_2026_s1_kab", table_name="master_sls_2026_s1")
    op.drop_table("master_sls_2026_s1")
