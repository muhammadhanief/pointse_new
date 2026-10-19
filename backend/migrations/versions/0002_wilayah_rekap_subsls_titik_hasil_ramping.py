"""Normalkan wilayah, rampingkan ``titik_hasil``, tambah ``rekap_subsls``.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19

Perubahan:

- tabel ``wilayah`` (dimensi wilayah per SubSLS, diisi dari peta dengan upsert)
  dan ``rekap_subsls`` (snapshot rekap per job untuk dua dasar: ``tugas`` dan
  ``posisi``);
- ``titik_hasil`` dibuat ulang: hanya kolom yang dipakai dashboard, kunci utama
  ``(run_id, urut)``, dan wilayah ditunjuk lewat ``wilayah_asal_id`` /
  ``wilayah_edit_id``;
- ``runs.jumlah_tanpa_wilayah`` (jumlah titik di luar poligon wilkerstat).

Tidak ada migrasi data: isi ``titik_hasil`` lama dibuang dan job bisa dijalankan
ulang dari berkas mentah yang tersimpan di disk server.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002"
down_revision = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# TINYINT di MySQL, SMALLINT di SQLite (SQLite hanya punya tipe INTEGER).
ANGKA_KECIL = sa.SmallInteger().with_variant(mysql.TINYINT(), "mysql")

KOLOM_WILAYAH: tuple[sa.Column, ...] = (
    sa.Column("idsubsls", sa.String(length=16), nullable=False),
    sa.Column("idsls", sa.String(length=16), nullable=True),
    sa.Column("nmsls", sa.String(length=128), nullable=True),
    sa.Column("kdprov", sa.String(length=4), nullable=True),
    sa.Column("nmprov", sa.String(length=64), nullable=True),
    sa.Column("kdkab", sa.String(length=4), nullable=True),
    sa.Column("nmkab", sa.String(length=64), nullable=True),
    sa.Column("kdkec", sa.String(length=8), nullable=True),
    sa.Column("nmkec", sa.String(length=64), nullable=True),
    sa.Column("kddesa", sa.String(length=16), nullable=True),
    sa.Column("nmdesa", sa.String(length=64), nullable=True),
)


def upgrade() -> None:
    """Buat ``wilayah`` + ``rekap_subsls`` dan ganti ``titik_hasil``."""
    op.create_table(
        "wilayah",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        *KOLOM_WILAYAH,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idsubsls", name="uq_wilayah_idsubsls"),
    )
    op.create_index("ix_wilayah_kdkab", "wilayah", ["kdkab"], unique=False)

    op.add_column("runs", sa.Column("jumlah_tanpa_wilayah", sa.Integer(), nullable=True))

    # Skema lama tidak kompatibel (nama wilayah + kolom atribut panjang): dibuang.
    op.drop_table("titik_hasil")

    op.create_table(
        "titik_hasil",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("urut", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.String(length=64), nullable=False),
        sa.Column("level_6_full_code", sa.String(length=16), nullable=True),
        sa.Column("wilayah_asal_id", sa.Integer(), nullable=True),
        sa.Column("wilayah_edit_id", sa.Integer(), nullable=True),
        sa.Column("flag_psls", ANGKA_KECIL, nullable=True),
        sa.Column("flag_position", ANGKA_KECIL, nullable=True),
        sa.Column("flag_edit_atr_repair", ANGKA_KECIL, nullable=True),
        sa.Column("flag_repair_initial", ANGKA_KECIL, nullable=True),
        sa.Column("flag_repair", ANGKA_KECIL, nullable=True),
        sa.Column("kk", ANGKA_KECIL, nullable=True),
        sa.Column("btt", ANGKA_KECIL, nullable=True),
        sa.Column("bku", ANGKA_KECIL, nullable=True),
        sa.Column("bttk", ANGKA_KECIL, nullable=True),
        sa.Column("bbtt", ANGKA_KECIL, nullable=True),
        sa.Column("usaha", sa.SmallInteger(), nullable=True),
        sa.Column("latitude_origin", sa.Double(), nullable=True),
        sa.Column("longitude_origin", sa.Double(), nullable=True),
        sa.Column("latitude_edited", sa.Double(), nullable=True),
        sa.Column("longitude_edited", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wilayah_asal_id"], ["wilayah.id"]),
        sa.ForeignKeyConstraint(["wilayah_edit_id"], ["wilayah.id"]),
        sa.PrimaryKeyConstraint("run_id", "urut"),
        sa.UniqueConstraint("run_id", "assignment_id", name="uq_titik_hasil_run_assignment"),
    )
    op.create_index(
        "ix_titik_hasil_wilayah_asal", "titik_hasil", ["wilayah_asal_id"], unique=False
    )
    op.create_index(
        "ix_titik_hasil_wilayah_edit", "titik_hasil", ["wilayah_edit_id"], unique=False
    )
    op.create_index(
        "ix_titik_hasil_run_flag_repair", "titik_hasil", ["run_id", "flag_repair"], unique=False
    )

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


def downgrade() -> None:
    """Kembalikan skema 0001 (``titik_hasil`` lebar, tanpa ``wilayah``)."""
    op.drop_index("ix_rekap_subsls_run_dasar", table_name="rekap_subsls")
    op.drop_table("rekap_subsls")

    op.drop_index("ix_titik_hasil_run_flag_repair", table_name="titik_hasil")
    op.drop_index("ix_titik_hasil_wilayah_edit", table_name="titik_hasil")
    op.drop_index("ix_titik_hasil_wilayah_asal", table_name="titik_hasil")
    op.drop_table("titik_hasil")

    op.create_table(
        "titik_hasil",
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

    op.drop_column("runs", "jumlah_tanpa_wilayah")

    op.drop_index("ix_wilayah_kdkab", table_name="wilayah")
    op.drop_table("wilayah")
