"""Tabel rekonsiliasi batas berpasangan antar-kabupaten/kota (Gap & Overlap).

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-11

Menambahkan dua tabel tanpa geometri di DB (poligon disimpan di disk sebagai
GeoJSON per pasangan):
- ``rekonsiliasi_batas_pasang``: status dan ringkasan per pasangan tetangga
  ``(kdkab_a, kdkab_b)`` dengan ``kdkab_a < kdkab_b``.
- ``rekonsiliasi_batas_temuan``: rincian tiap temuan Gap dan Overlap beserta
  pasangan kode/nama SLS, luas (m2), dan titik representatif (lat, lon).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ID_BESAR = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    """Buat tabel ``rekonsiliasi_batas_pasang`` dan ``rekonsiliasi_batas_temuan``."""
    op.create_table(
        "rekonsiliasi_batas_pasang",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kdprov", sa.String(4), nullable=False),
        sa.Column("kdkab_a", sa.String(4), nullable=False),
        sa.Column("kdkab_b", sa.String(4), nullable=False),
        sa.Column(
            "run_a_id",
            sa.Integer(),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "run_b_id",
            sa.Integer(),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("jumlah_overlap", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jumlah_gap", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "total_luas_overlap_m2", sa.Double(), nullable=False, server_default="0"
        ),
        sa.Column("total_luas_gap_m2", sa.Double(), nullable=False, server_default="0"),
        sa.Column("berkas_geojson", sa.String(512), nullable=True),
        sa.Column("pesan", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "kdkab_a", "kdkab_b", name="uq_rekonsiliasi_batas_pasang_kab"
        ),
    )
    op.create_index(
        "ix_rekonsiliasi_batas_pasang_prov_status",
        "rekonsiliasi_batas_pasang",
        ["kdprov", "status"],
    )
    op.create_index(
        "ix_rekonsiliasi_batas_pasang_kab_a",
        "rekonsiliasi_batas_pasang",
        ["kdkab_a"],
    )
    op.create_index(
        "ix_rekonsiliasi_batas_pasang_kab_b",
        "rekonsiliasi_batas_pasang",
        ["kdkab_b"],
    )

    op.create_table(
        "rekonsiliasi_batas_temuan",
        sa.Column("id", ID_BESAR, primary_key=True, autoincrement=True),
        sa.Column(
            "pasang_id",
            sa.Integer(),
            sa.ForeignKey("rekonsiliasi_batas_pasang.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kdkab_a", sa.String(4), nullable=False),
        sa.Column("kdkab_b", sa.String(4), nullable=False),
        sa.Column("jenis", sa.String(16), nullable=False),
        sa.Column("tingkat", sa.String(16), nullable=False),
        sa.Column("idsls_a", sa.String(20), nullable=True),
        sa.Column("idsubsls_a", sa.String(20), nullable=True),
        sa.Column("nmsls_a", sa.String(128), nullable=True),
        sa.Column("idsls_b", sa.String(20), nullable=True),
        sa.Column("idsubsls_b", sa.String(20), nullable=True),
        sa.Column("nmsls_b", sa.String(128), nullable=True),
        sa.Column("luas_m2", sa.Double(), nullable=False, server_default="0"),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("catatan", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_rekonsiliasi_batas_temuan_pasang_jenis",
        "rekonsiliasi_batas_temuan",
        ["pasang_id", "jenis"],
    )


def downgrade() -> None:
    """Hapus tabel ``rekonsiliasi_batas_temuan`` dan ``rekonsiliasi_batas_pasang``."""
    op.drop_index(
        "ix_rekonsiliasi_batas_temuan_pasang_jenis",
        table_name="rekonsiliasi_batas_temuan",
    )
    op.drop_table("rekonsiliasi_batas_temuan")
    op.drop_index(
        "ix_rekonsiliasi_batas_pasang_kab_b",
        table_name="rekonsiliasi_batas_pasang",
    )
    op.drop_index(
        "ix_rekonsiliasi_batas_pasang_kab_a",
        table_name="rekonsiliasi_batas_pasang",
    )
    op.drop_index(
        "ix_rekonsiliasi_batas_pasang_prov_status",
        table_name="rekonsiliasi_batas_pasang",
    )
    op.drop_table("rekonsiliasi_batas_pasang")
