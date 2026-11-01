"""Jarak geser titik untuk poin pencermatan "Digeser >= 10 m".

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-01

``flag_position`` dari model QGIS hanya membandingkan ``latitude`` dan
menganggap pergeseran sekecil apa pun sebagai "digeser", sehingga titik yang
hanya bergeser beberapa sentimeter (getaran GPS) ikut terhitung. Menu
pencermatan titik memakai jarak datar sebenarnya (kedua koordinat) dengan ambang
:data:`app.geser.JARAK_GESER_MIN_M` (10 m).

- ``titik_hasil.jarak_geser_m`` diisi worker saat job Proses B selesai dihitung
  (lihat :func:`app.worker.tambah_kolom_jarak`), sebelum anomali dihitung.
- ``anomali_titik.jarak_geser_m`` menyimpan jarak baris jenis ``digeser`` supaya
  keterangan/ekspor tetap terbaca walau ``titik_hasil`` sudah dirampingkan.

Migrasi additive: kolom nullable, run lama bernilai NULL (tidak memunculkan
baris ``digeser`` sampai dihitung ulang lewat
``scripts/hitung_ulang_digeser.py``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Tambah kolom jarak geser di ``titik_hasil`` dan ``anomali_titik``."""
    op.add_column(
        "titik_hasil", sa.Column("jarak_geser_m", sa.Double(), nullable=True)
    )
    op.add_column(
        "anomali_titik", sa.Column("jarak_geser_m", sa.Double(), nullable=True)
    )


def downgrade() -> None:
    """Hapus kolom jarak geser."""
    op.drop_column("anomali_titik", "jarak_geser_m")
    op.drop_column("titik_hasil", "jarak_geser_m")