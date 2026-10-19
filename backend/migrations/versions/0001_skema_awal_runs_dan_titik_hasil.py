"""Skema awal: tabel ``runs`` dan ``titik_hasil`` (PRD §7).

Revision ID: 0001
Revises:
Create Date: 2026-10-19

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Buat tabel job (``runs``) dan hasil titik (``titik_hasil``)."""
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tipe", sa.String(length=1), nullable=False),
        sa.Column("kdkab", sa.String(length=4), nullable=False),
        sa.Column("user", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("nama_file_input", sa.String(length=255), nullable=False),
        sa.Column("nama_file_peta", sa.String(length=255), nullable=False),
        sa.Column("berkas_input", sa.String(length=512), nullable=False),
        sa.Column("berkas_peta", sa.String(length=512), nullable=False),
        sa.Column("layer_input", sa.String(length=64), nullable=True),
        sa.Column("layer_peta", sa.String(length=64), nullable=True),
        sa.Column("jumlah_baris", sa.Integer(), nullable=True),
        sa.Column("pesan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_kdkab"), "runs", ["kdkab"], unique=False)
    op.create_index(op.f("ix_runs_status"), "runs", ["status"], unique=False)
    op.create_index(op.f("ix_runs_tipe"), "runs", ["tipe"], unique=False)

    op.create_table(
        "titik_hasil",
        # BIGINT di MySQL; di SQLite harus INTEGER supaya auto-increment jalan.
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.String(length=64), nullable=False),
        sa.Column("unique_bang", sa.String(length=64), nullable=True),
        sa.Column("flag_psls", sa.SmallInteger(), nullable=True),
        sa.Column("flag_position", sa.SmallInteger(), nullable=True),
        sa.Column("flag_edit_atr_repair", sa.SmallInteger(), nullable=True),
        sa.Column("flag_repair_initial", sa.SmallInteger(), nullable=True),
        sa.Column("flag_repair", sa.SmallInteger(), nullable=True),
        sa.Column("level_6_full_code", sa.String(length=32), nullable=True),
        sa.Column("idsubsls_origin", sa.String(length=32), nullable=True),
        sa.Column("idsubsls_edited", sa.String(length=32), nullable=True),
        sa.Column("latitude_origin", sa.Double(), nullable=True),
        sa.Column("longitude_origin", sa.Double(), nullable=True),
        sa.Column("latitude_edited", sa.Double(), nullable=True),
        sa.Column("longitude_edited", sa.Double(), nullable=True),
        sa.Column("no_bang", sa.String(length=32), nullable=True),
        sa.Column("kode_bang_value", sa.String(length=8), nullable=True),
        sa.Column("ada_keluarga_value", sa.String(length=4), nullable=True),
        sa.Column("ada_bang_usaha_value", sa.String(length=4), nullable=True),
        sa.Column("jumlah_usaha_ditemukan", sa.String(length=8), nullable=True),
        sa.Column("kk", sa.SmallInteger(), nullable=True),
        sa.Column("btt", sa.SmallInteger(), nullable=True),
        sa.Column("bku", sa.SmallInteger(), nullable=True),
        sa.Column("bttk", sa.SmallInteger(), nullable=True),
        sa.Column("bbtt", sa.SmallInteger(), nullable=True),
        sa.Column("usaha", sa.String(length=8), nullable=True),
        sa.Column("kdprov", sa.String(length=2), nullable=True),
        sa.Column("nmprov", sa.String(length=64), nullable=True),
        sa.Column("kdkab", sa.String(length=4), nullable=True),
        sa.Column("nmkab", sa.String(length=64), nullable=True),
        sa.Column("kdkec", sa.String(length=8), nullable=True),
        sa.Column("nmkec", sa.String(length=64), nullable=True),
        sa.Column("kddesa", sa.String(length=16), nullable=True),
        sa.Column("nmdesa", sa.String(length=64), nullable=True),
        sa.Column("nmsls", sa.String(length=128), nullable=True),
        sa.Column("nama_usaha_bang", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "assignment_id", name="uq_titik_hasil_run_assignment"),
    )
    op.create_index("ix_titik_hasil_assignment_id", "titik_hasil", ["assignment_id"], unique=False)
    op.create_index(
        "ix_titik_hasil_idsubsls_origin", "titik_hasil", ["idsubsls_origin"], unique=False
    )
    op.create_index("ix_titik_hasil_kdkab", "titik_hasil", ["kdkab"], unique=False)
    op.create_index(
        "ix_titik_hasil_run_flag_repair", "titik_hasil", ["run_id", "flag_repair"], unique=False
    )
    op.create_index(op.f("ix_titik_hasil_run_id"), "titik_hasil", ["run_id"], unique=False)


def downgrade() -> None:
    """Hapus kedua tabel beserta indeksnya."""
    op.drop_index(op.f("ix_titik_hasil_run_id"), table_name="titik_hasil")
    op.drop_index("ix_titik_hasil_run_flag_repair", table_name="titik_hasil")
    op.drop_index("ix_titik_hasil_kdkab", table_name="titik_hasil")
    op.drop_index("ix_titik_hasil_idsubsls_origin", table_name="titik_hasil")
    op.drop_index("ix_titik_hasil_assignment_id", table_name="titik_hasil")
    op.drop_table("titik_hasil")
    op.drop_index(op.f("ix_runs_tipe"), table_name="runs")
    op.drop_index(op.f("ix_runs_status"), table_name="runs")
    op.drop_index(op.f("ix_runs_kdkab"), table_name="runs")
    op.drop_table("runs")
