"""Heartbeat job dan ``titik_hasil.urut`` BIGINT (mode hemat memori).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-19

Perubahan skema:

- ``runs.heartbeat_at`` -- waktu UTC heartbeat terakhir worker, diperbarui tiap
  batch penyimpanan. Job ``jalan`` yang heartbeat-nya lebih lama dari
  ``JOB_TIMEOUT_MENIT`` (default 10 menit) dianggap terhenti: worker menandainya
  ``gagal`` dengan pesan khusus dan membersihkan hasil separuhnya, sehingga job
  baru untuk kabupaten/tipe yang sama tidak terhalang selamanya;
- ``titik_hasil.urut`` menjadi ``BIGINT``. Mode ``PROSES_CHUNK_TITIK`` menulis
  kunci urutan sementara ``posisi_poligon * 1e9 + nomor_urut_titik`` (bisa
  melebihi batas ``INTEGER``) sebelum dirapikan menjadi ``0..n-1`` di akhir job.

Downgrade mengembalikan ``urut`` ke ``INTEGER``; kalau masih ada baris hasil mode
potongan yang belum dirapikan (job mati di tengah jalan), perkecil dulu dengan
menjalankan ulang job tersebut.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _ubah_urut(tipe: sa.types.TypeEngine, tipe_lama: sa.types.TypeEngine) -> None:
    """Ubah tipe ``titik_hasil.urut`` (SQLite harus bangun ulang tabel)."""
    if op.get_context().dialect.name == "sqlite":
        with op.batch_alter_table("titik_hasil", recreate="always") as batch:
            batch.alter_column(
                "urut",
                type_=tipe,
                existing_type=tipe_lama,
                existing_nullable=False,
            )
    else:
        op.alter_column(
            "titik_hasil",
            "urut",
            type_=tipe,
            existing_type=tipe_lama,
            existing_nullable=False,
        )


def upgrade() -> None:
    """Tambah ``runs.heartbeat_at`` dan lebarkan ``titik_hasil.urut``."""
    op.add_column("runs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    _ubah_urut(sa.BigInteger(), sa.Integer())


def downgrade() -> None:
    """Kembalikan ``urut`` ke INTEGER dan hapus heartbeat."""
    _ubah_urut(sa.Integer(), sa.BigInteger())
    op.drop_column("runs", "heartbeat_at")
