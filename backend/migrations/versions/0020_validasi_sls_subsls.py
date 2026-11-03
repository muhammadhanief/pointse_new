"""Validasi SLS 2026 S1 sampai level SubSLS.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-04

Matching validasi run V kini dua level: ``idsls`` (14 digit, beda himpunan
SLS) dan ``idsubsls`` (18 digit, beda komposisi SubSLS di dalam SLS yang
cocok). Kolom ``validasi_sls_unmatch.idsls`` ikut menyimpan kode 18 digit,
jadi lebarnya ditambah 16 -> 20. Widening saja: data lama (14 digit) tidak
berubah, nullable/tidak-null tidak berubah.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Lebarkan ``validasi_sls_unmatch.idsls`` menjadi VARCHAR(20)."""
    op.alter_column(
        "validasi_sls_unmatch",
        "idsls",
        existing_type=sa.String(length=16),
        type_=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Kembalikan ke VARCHAR(16) (gagal bila ada baris 18 digit)."""
    op.alter_column(
        "validasi_sls_unmatch",
        "idsls",
        existing_type=sa.String(length=20),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
