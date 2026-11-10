"""Konfirmasi temuan validasi peta SLS 2026 S1 beserta persetujuan provinsi.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-10

Menyimpan konfirmasi temuan validasi ("Akan Diperbaiki" / "Sesuai Kondisi
Kenyataan") dari kabupaten/kota maupun provinsi, serta keputusan persetujuan
("Disetujui" / "Ditolak") dari Admin Provinsi di tabel
``konfirmasi_validasi_sls`` dengan kunci stabil per kabupaten/kota.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ID_BESAR = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    """Buat tabel ``konfirmasi_validasi_sls`` beserta indeksnya."""
    op.create_table(
        "konfirmasi_validasi_sls",
        sa.Column("id", ID_BESAR, primary_key=True, autoincrement=True),
        sa.Column("kdprov", sa.String(4), nullable=False),
        sa.Column("kdkab", sa.String(4), nullable=False),
        sa.Column("kunci", sa.String(191), nullable=False),
        sa.Column("jenis", sa.String(24), nullable=False),
        sa.Column("idsls_peta", sa.String(20), nullable=True),
        sa.Column("idsubsls_peta", sa.String(20), nullable=True),
        sa.Column("idsls_master", sa.String(20), nullable=True),
        sa.Column("idsubsls_master", sa.String(20), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("run_v_id", sa.Integer(), nullable=True),
        sa.Column("sub", sa.String(128), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("nama", sa.String(128), nullable=False),
        sa.Column("nip", sa.String(32), nullable=True),
        sa.Column("peran", sa.String(32), nullable=False),
        sa.Column("persetujuan_status", sa.String(24), nullable=True),
        sa.Column("persetujuan_catatan", sa.Text(), nullable=True),
        sa.Column("persetujuan_sub", sa.String(128), nullable=True),
        sa.Column("persetujuan_username", sa.String(64), nullable=True),
        sa.Column("persetujuan_oleh", sa.String(128), nullable=True),
        sa.Column("persetujuan_pada", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_v_id"], ["runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "kdprov",
            "kdkab",
            "kunci",
            name="uq_konfirmasi_validasi_sls_kunci",
        ),
    )
    op.create_index(
        "ix_konfirmasi_validasi_sls_kab",
        "konfirmasi_validasi_sls",
        ["kdprov", "kdkab"],
    )
    op.create_index(
        "ix_konfirmasi_validasi_sls_run",
        "konfirmasi_validasi_sls",
        ["run_v_id"],
    )


def downgrade() -> None:
    """Hapus tabel ``konfirmasi_validasi_sls``."""
    op.drop_index("ix_konfirmasi_validasi_sls_run", table_name="konfirmasi_validasi_sls")
    op.drop_index("ix_konfirmasi_validasi_sls_kab", table_name="konfirmasi_validasi_sls")
    op.drop_table("konfirmasi_validasi_sls")
