"""``rekap_subsls``: hitungan terpisah + baris "(tanpa wilayah)".

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19

Perubahan:

- ``rekap_subsls.sudah`` diganti ``sudah_posisi`` dan ``sudah_manual``, ditambah
  ``tanpa_wilayah`` (titik pada baris itu yang tidak masuk poligon mana pun);
- kunci utama pindah dari ``(run_id, wilayah_id, dasar)`` ke ``id`` dan
  ``wilayah_id`` dibuat boleh NULL: MySQL tidak mengizinkan kolom kunci utama
  bernilai NULL, padahal titik yang tidak bisa dipetakan ke wilayah pada dasar itu
  (dasar ``tugas``: ``level_6_full_code`` kosong/tidak ada di peta; dasar
  ``posisi``: titik di luar semua poligon) perlu dihitung pada kategori terpisah
  "(tanpa wilayah)" supaya foreign key tidak pernah gagal dan tidak ada titik yang
  hilang dari rekap.

Tidak ada migrasi data: ``rekap_subsls`` hanyalah snapshot turunan dari
``titik_hasil``, jadi tabelnya dibuat ulang dari nol dan tiap job bisa dihitung
ulang dengan menjalankannya kembali (atau memanggil ``app.worker.simpan_rekap``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Buat ulang ``rekap_subsls`` dengan kolom hitungan terpisah."""
    op.drop_index("ix_rekap_subsls_run_dasar", table_name="rekap_subsls")
    op.drop_table("rekap_subsls")

    op.create_table(
        "rekap_subsls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("wilayah_id", sa.Integer(), nullable=True),
        sa.Column("dasar", sa.String(length=8), nullable=False),
        sa.Column("jumlah", sa.Integer(), nullable=False),
        sa.Column("belum", sa.Integer(), nullable=False),
        sa.Column("sudah_posisi", sa.Integer(), nullable=False),
        sa.Column("sudah_manual", sa.Integer(), nullable=False),
        sa.Column("tanpa_wilayah", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wilayah_id"], ["wilayah.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "dasar", "wilayah_id", name="uq_rekap_subsls_run_dasar_wilayah"
        ),
    )
    op.create_index(
        "ix_rekap_subsls_run_dasar", "rekap_subsls", ["run_id", "dasar"], unique=False
    )


def downgrade() -> None:
    """Kembalikan ``rekap_subsls`` ke bentuk 0002."""
    op.drop_index("ix_rekap_subsls_run_dasar", table_name="rekap_subsls")
    op.drop_table("rekap_subsls")

    op.create_table(
        "rekap_subsls",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("wilayah_id", sa.Integer(), nullable=False),
        sa.Column("dasar", sa.String(length=8), nullable=False),
        sa.Column("jumlah", sa.Integer(), nullable=False),
        sa.Column("sudah", sa.Integer(), nullable=False),
        sa.Column("belum", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wilayah_id"], ["wilayah.id"]),
        sa.PrimaryKeyConstraint("run_id", "wilayah_id", "dasar"),
    )
    op.create_index(
        "ix_rekap_subsls_run_dasar", "rekap_subsls", ["run_id", "dasar"], unique=False
    )
