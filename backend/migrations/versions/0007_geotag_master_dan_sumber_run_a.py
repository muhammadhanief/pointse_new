"""Geotag master per kabupaten dan sumber run A untuk Proses B.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19

Perubahan skema:

- tabel ``geotag_master``: geotag asli per kabupaten/kota yang diunggah admin
  provinsi. Berkasnya disimpan permanen dan dipakai ulang oleh banyak run A;
- ``runs.geotag_master_id``: versi master yang dipakai run A;
- ``runs.sumber_run_a_id``: run A terakhir yang menjadi sumber peta untuk run B.

Di SQLite constraint foreign key tidak ditambahkan lewat migrasi (SQLite tidak
mendukung ``ALTER TABLE ADD CONSTRAINT``); tes skema tetap memakai ORM untuk
membuat constraint. Di MySQL/MariaDB foreign key dibuat seperti biasa.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Buat tabel master geotag dan tautkan run A/B ke sumbernya."""
    op.create_table(
        "geotag_master",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kdprov", sa.String(length=4), nullable=False),
        sa.Column("kdkab", sa.String(length=4), nullable=False),
        sa.Column("tanggal_data", sa.Date(), nullable=False),
        sa.Column("nama_file", sa.String(length=255), nullable=False),
        sa.Column("berkas", sa.String(length=512), nullable=False),
        sa.Column("layer", sa.String(length=64), nullable=True),
        sa.Column("jumlah_baris", sa.Integer(), nullable=True),
        sa.Column("user", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_geotag_master_kdprov_kdkab",
        "geotag_master",
        ["kdprov", "kdkab"],
        unique=False,
    )

    if op.get_context().dialect.name == "sqlite":
        # SQLite tidak mendukung ALTER TABLE ADD CONSTRAINT; bangun ulang tabel.
        with op.batch_alter_table("runs", recreate="always") as batch:
            batch.add_column(sa.Column("geotag_master_id", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("sumber_run_a_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_runs_geotag_master_id",
                "geotag_master",
                ["geotag_master_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_foreign_key(
                "fk_runs_sumber_run_a_id",
                "runs",
                ["sumber_run_a_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.add_column("runs", sa.Column("geotag_master_id", sa.Integer(), nullable=True))
        op.add_column("runs", sa.Column("sumber_run_a_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_runs_geotag_master_id",
            "runs",
            "geotag_master",
            ["geotag_master_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            "fk_runs_sumber_run_a_id",
            "runs",
            "runs",
            ["sumber_run_a_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index(
        "ix_runs_geotag_master_id", "runs", ["geotag_master_id"], unique=False
    )
    op.create_index(
        "ix_runs_sumber_run_a_id", "runs", ["sumber_run_a_id"], unique=False
    )


def downgrade() -> None:
    """Hapus tautan sumber dan tabel master geotag."""
    op.drop_index("ix_runs_sumber_run_a_id", table_name="runs")
    op.drop_index("ix_runs_geotag_master_id", table_name="runs")
    if op.get_context().dialect.name == "sqlite":
        with op.batch_alter_table("runs", recreate="always") as batch:
            batch.drop_constraint("fk_runs_sumber_run_a_id", type_="foreignkey")
            batch.drop_constraint("fk_runs_geotag_master_id", type_="foreignkey")
            batch.drop_column("sumber_run_a_id")
            batch.drop_column("geotag_master_id")
    else:
        op.drop_constraint("fk_runs_sumber_run_a_id", "runs", type_="foreignkey")
        op.drop_constraint("fk_runs_geotag_master_id", "runs", type_="foreignkey")
        op.drop_column("runs", "sumber_run_a_id")
        op.drop_column("runs", "geotag_master_id")
    op.drop_index("ix_geotag_master_kdprov_kdkab", table_name="geotag_master")
    op.drop_table("geotag_master")
