"""``rekap_subsls``: kolom tindakan dipisah (benar_awal / ditindak_posisi_*).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19

Perubahan:

- ``sudah_posisi`` dan ``sudah_manual`` diganti empat kolom yang lebih jelas:
  ``benar_awal`` (``flag_repair`` = 0 tanpa tindakan manual), ``ditindak_posisi_benar``
  (``flag_repair`` = 0, ``flag_edit_atr_repair`` = 1, ``flag_repair_initial`` = 0), dan
  ``ditindak_posisi_salah`` (``flag_repair`` = 0, ``flag_edit_atr_repair`` = 1,
  ``flag_repair_initial`` = 1);
- tambah ``digeser`` (titik dengan ``flag_position`` = 1).

Persentase progres tidak disimpan di tabel ini: dihitung saat dibaca
(``app.layanan.rekap_run``) sebagai
(``ditindak_posisi_benar`` + ``ditindak_posisi_salah``) /
(``belum`` + ``ditindak_posisi_benar`` + ``ditindak_posisi_salah``).

Tidak ada migrasi data: ``rekap_subsls`` hanya snapshot turunan dari ``titik_hasil``,
jadi tabelnya dibuat ulang dari nol dan isinya dibangun ulang dengan
``app.worker.simpan_rekap`` (tanpa memproses ulang berkas masukan).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Susunan kolom hitungan (selain run_id/wilayah_id/dasar) di kedua arah migrasi.
HITUNGAN_0003: tuple[str, ...] = (
    "jumlah",
    "belum",
    "sudah_posisi",
    "sudah_manual",
    "tanpa_wilayah",
)

HITUNGAN_0004: tuple[str, ...] = (
    "jumlah",
    "belum",
    "ditindak_posisi_benar",
    "ditindak_posisi_salah",
    "benar_awal",
    "digeser",
    "tanpa_wilayah",
)


def _buat_ulang(kolom_hitungan: Sequence[str]) -> None:
    """Buat ulang ``rekap_subsls`` dengan susunan kolom hitungan tertentu."""
    op.drop_index("ix_rekap_subsls_run_dasar", table_name="rekap_subsls")
    op.drop_table("rekap_subsls")

    op.create_table(
        "rekap_subsls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("wilayah_id", sa.Integer(), nullable=True),
        sa.Column("dasar", sa.String(length=8), nullable=False),
        *[sa.Column(nama, sa.Integer(), nullable=False) for nama in kolom_hitungan],
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


def upgrade() -> None:
    """Buat ulang ``rekap_subsls`` dengan kolom tindakan + ``digeser``."""
    _buat_ulang(HITUNGAN_0004)


def downgrade() -> None:
    """Kembalikan ``rekap_subsls`` ke bentuk 0003."""
    _buat_ulang(HITUNGAN_0003)
