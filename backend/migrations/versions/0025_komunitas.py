"""Tabel modul Komunitas untuk berbagi error GS Pusat dan solusinya.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-10

Menambahkan tiga tabel ringan untuk fitur Komunitas:
- ``komunitas_topik``: topik masalah/error ``.txt`` saat unggah ke
  ``dataspasial.bps.go.id/gs`` beserta solusi dan rencana rule baru
  (Identifikasi / Pengecekan / Validasi).
- ``komunitas_komentar``: diskusi/balasan dan penanda solusi terverifikasi.
- ``komunitas_dukungan``: penanda pengguna kab/kota lain yang mengalami
  masalah serupa (+1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ID_BESAR = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
ANGKA_KECIL = sa.SmallInteger()


def upgrade() -> None:
    """Buat tabel ``komunitas_topik``, ``komunitas_komentar``, dan ``komunitas_dukungan``."""
    op.create_table(
        "komunitas_topik",
        sa.Column("id", ID_BESAR, primary_key=True, autoincrement=True),
        sa.Column("kdprov", sa.String(4), nullable=False),
        sa.Column("kdkab", sa.String(4), nullable=True),
        sa.Column("kategori", sa.String(24), nullable=False),
        sa.Column("judul", sa.String(200), nullable=False),
        sa.Column("error_txt", sa.Text(), nullable=True),
        sa.Column("deskripsi", sa.Text(), nullable=False),
        sa.Column("solusi_awal", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("solusi_komentar_id", ID_BESAR, nullable=True),
        sa.Column("rule_target", sa.String(24), nullable=True),
        sa.Column("rule_catatan", sa.Text(), nullable=True),
        sa.Column("rule_oleh", sa.String(128), nullable=True),
        sa.Column("rule_pada", sa.DateTime(), nullable=True),
        sa.Column("jumlah_komentar", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jumlah_dukungan", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sub", sa.String(128), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("nama", sa.String(128), nullable=False),
        sa.Column("nip", sa.String(32), nullable=True),
        sa.Column("peran", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_komunitas_topik_prov_status_created",
        "komunitas_topik",
        ["kdprov", "status", "created_at"],
    )
    op.create_index(
        "ix_komunitas_topik_kategori_created",
        "komunitas_topik",
        ["kategori", "created_at"],
    )

    op.create_table(
        "komunitas_komentar",
        sa.Column("id", ID_BESAR, primary_key=True, autoincrement=True),
        sa.Column("topik_id", ID_BESAR, nullable=False),
        sa.Column("kdprov", sa.String(4), nullable=False),
        sa.Column("kdkab", sa.String(4), nullable=True),
        sa.Column("isi", sa.Text(), nullable=False),
        sa.Column("adalah_solusi", ANGKA_KECIL, nullable=False, server_default="0"),
        sa.Column("sub", sa.String(128), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("nama", sa.String(128), nullable=False),
        sa.Column("nip", sa.String(32), nullable=True),
        sa.Column("peran", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["topik_id"], ["komunitas_topik.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_komunitas_komentar_topik_created",
        "komunitas_komentar",
        ["topik_id", "created_at"],
    )

    op.create_table(
        "komunitas_dukungan",
        sa.Column("id", ID_BESAR, primary_key=True, autoincrement=True),
        sa.Column("topik_id", ID_BESAR, nullable=False),
        sa.Column("sub", sa.String(128), nullable=False),
        sa.Column("nama", sa.String(128), nullable=False),
        sa.Column("kdkab", sa.String(4), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["topik_id"], ["komunitas_topik.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("topik_id", "sub", name="uq_komunitas_dukungan_topik_sub"),
    )
    op.create_index(
        "ix_komunitas_dukungan_topik",
        "komunitas_dukungan",
        ["topik_id"],
    )


def downgrade() -> None:
    """Hapus tabel modul Komunitas."""
    op.drop_index("ix_komunitas_dukungan_topik", table_name="komunitas_dukungan")
    op.drop_table("komunitas_dukungan")
    op.drop_index("ix_komunitas_komentar_topik_created", table_name="komunitas_komentar")
    op.drop_table("komunitas_komentar")
    op.drop_index("ix_komunitas_topik_kategori_created", table_name="komunitas_topik")
    op.drop_index("ix_komunitas_topik_prov_status_created", table_name="komunitas_topik")
    op.drop_table("komunitas_topik")
