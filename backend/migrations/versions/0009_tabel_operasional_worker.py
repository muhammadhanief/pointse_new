"""Tabel operasional worker: heartbeat dan riwayat kejadian.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-20

Menambahkan dua tabel yang dipakai halaman Status Sistem (T7):

- ``worker_heartbeat`` -- satu baris per worker hidup, diperbarui tiap
  ``WORKER_HEARTBEAT_DETIK`` baik saat menganggur maupun mengerjakan job;
- ``worker_event`` -- riwayat kejadian worker (mulai, klaim, sukses, gagal,
  job terhenti, anggaran memori). Baris lama dipangkas worker.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ID_BESAR = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    """Buat tabel heartbeat worker dan riwayat event."""
    op.create_table(
        "worker_heartbeat",
        sa.Column("worker_id", sa.String(length=80), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("hostname", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    op.create_index("ix_worker_heartbeat_run_id", "worker_heartbeat", ["run_id"])
    op.create_index(
        "ix_worker_heartbeat_heartbeat_at", "worker_heartbeat", ["heartbeat_at"]
    )
    op.create_index(
        "ix_worker_heartbeat_status_heartbeat",
        "worker_heartbeat",
        ["status", "heartbeat_at"],
    )

    op.create_table(
        "worker_event",
        sa.Column("id", ID_BESAR, autoincrement=True, nullable=False),
        sa.Column("worker_id", sa.String(length=80), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("jenis", sa.String(length=32), nullable=False),
        sa.Column("pesan", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_event_created", "worker_event", ["created_at"])
    op.create_index(
        "ix_worker_event_run_created", "worker_event", ["run_id", "created_at"]
    )
    op.create_index(
        "ix_worker_event_worker_created",
        "worker_event",
        ["worker_id", "created_at"],
    )


def downgrade() -> None:
    """Hapus tabel event lalu heartbeat."""
    for nama in (
        "ix_worker_event_worker_created",
        "ix_worker_event_run_created",
        "ix_worker_event_created",
    ):
        op.drop_index(nama, table_name="worker_event")
    op.drop_table("worker_event")

    for nama in (
        "ix_worker_heartbeat_status_heartbeat",
        "ix_worker_heartbeat_heartbeat_at",
        "ix_worker_heartbeat_run_id",
    ):
        op.drop_index(nama, table_name="worker_heartbeat")
    op.drop_table("worker_heartbeat")
