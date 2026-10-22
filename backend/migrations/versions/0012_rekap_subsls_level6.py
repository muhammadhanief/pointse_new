"""Snapshot rekap per level 6/SubSLS untuk hitungan target vs capaian B.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-22

Tabel ``rekap_subsls`` lama dihapus di migrasi 0005. Tabel baru ini berbeda:
selain ``wilayah_id``, kode level 6 disimpan langsung supaya kode tugas yang
tidak ada di peta tetap bisa dihitung sebagai baris "(tanpa wilayah)".

Tidak ada backfill di migrasi: titik ``flag_repair=0`` run lama sudah dipangkas
dan tidak cukup untuk membangun ulang capaian B. Snapshot akan terisi untuk job
baru; job lama perlu diproses ulang bila ingin angka level 6-nya lengkap.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

KOLOM_HITUNGAN: tuple[str, ...] = (
    "jumlah",
    "belum",
    "benar_awal",
    "ditindak_posisi_benar",
    "ditindak_posisi_salah",
    "digeser",
    "tanpa_wilayah",
)


def upgrade() -> None:
    """Buat tabel snapshot level 6 beserta indeks baca per run/dasar."""
    op.create_table(
        "rekap_subsls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("dasar", sa.String(length=8), nullable=False),
        sa.Column("level_6_full_code", sa.String(length=16), nullable=True),
        sa.Column("wilayah_id", sa.Integer(), nullable=True),
        *[sa.Column(nama, sa.Integer(), nullable=False) for nama in KOLOM_HITUNGAN],
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wilayah_id"], ["wilayah.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "dasar",
            "level_6_full_code",
            name="uq_rekap_subsls_run_dasar_level6",
        ),
    )
    op.create_index(
        "ix_rekap_subsls_run_dasar",
        "rekap_subsls",
        ["run_id", "dasar"],
        unique=False,
    )


def downgrade() -> None:
    """Hapus tabel snapshot level 6."""
    op.drop_index("ix_rekap_subsls_run_dasar", table_name="rekap_subsls")
    op.drop_table("rekap_subsls")
