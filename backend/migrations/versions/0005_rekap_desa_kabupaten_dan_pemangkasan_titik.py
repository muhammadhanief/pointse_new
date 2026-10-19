"""Rekap per desa/kabupaten, tanggal data, dan pemangkasan detail titik.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-19

Perubahan skema:

- ``runs.kdprov`` (kunci kabupaten/kota di seluruh API/query jadi **kdprov+kdkab**);
- ``runs.tanggal_data`` (tanggal data; default tanggal unggah, boleh diisi saat
  unggah) -- ``created_at`` tetap waktu unggah (UTC);
- ``runs.detail_tersedia`` (1 = baris ``titik_hasil`` run ini masih disimpan: run
  baseline dan run sukses terakhir per kabupaten/kota+tipe);
- indeks tren ``runs(kdprov, kdkab, tipe, tanggal_data)``;
- tabel ``rekap_desa`` (per desa per dasar, plus satu baris "(tanpa wilayah)" per
  dasar) dan ``rekap_kabupaten`` (dijumlahkan per kabupaten/kota per dasar);
- tabel ``rekap_subsls`` **dihapus** (digantikan ``rekap_desa``/``rekap_kabupaten``).

Migrasi data (dilewati di mode offline ``alembic upgrade --sql`` karena perlu
membaca baris):

1. ``runs.kdprov`` diisi dari kode provinsi di tabel ``wilayah`` (peta yang pernah
   diunggah) dan ``runs.tanggal_data`` dari tanggal ``created_at``;
2. untuk tiap run yang masih punya baris ``titik_hasil``: ``rekap_desa`` dan
   ``rekap_kabupaten`` diisi dari ``titik_hasil`` tanpa memproses ulang berkas
   (memakai agregasi :mod:`app.rekap` yang sama dengan worker), lalu **diverifikasi
   sama dengan snapshot ``rekap_subsls`` lama**; kalau ada selisih, migrasi digagalkan;
3. baris ``titik_hasil`` yang tidak perlu perhatian dipangkas (hanya baseline dan
   run terakhir per kabupaten/kota+tipe yang disimpan, lihat ``runs.detail_tersedia``);
4. ``rekap_subsls`` dihapus.

Downgrade mengembalikan bentuk skema 0004, tetapi **isi ``rekap_subsls`` tidak bisa
dipulihkan** (tabelnya sudah dihapus di upgrade): isinya turunan dari ``titik_hasil``
yang bisa dibangun ulang dengan menjalankan ulang job.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from app import rekap as modul_rekap
from app.models import KOLOM_HITUNGAN

revision = "0005"
down_revision = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ANGKA_KECIL = sa.SmallInteger().with_variant(mysql.TINYINT(), "mysql")

# Kolom kode desa pada rekap (baris "(tanpa wilayah)" berkode NULL).
KOLOM_KODE_DESA: tuple[str, ...] = ("kdprov", "kdkab", "kdkec", "kddesa")


def _buat_rekap_desa() -> None:
    """Buat tabel ``rekap_desa`` (kunci utama ``id`` karena kode desa boleh NULL)."""
    op.create_table(
        "rekap_desa",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("dasar", sa.String(length=8), nullable=False),
        sa.Column("kdprov", sa.String(length=4), nullable=True),
        sa.Column("kdkab", sa.String(length=4), nullable=True),
        sa.Column("kdkec", sa.String(length=8), nullable=True),
        sa.Column("kddesa", sa.String(length=16), nullable=True),
        *[sa.Column(nama, sa.Integer(), nullable=False) for nama in KOLOM_HITUNGAN],
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "dasar",
            "kdprov",
            "kdkab",
            "kdkec",
            "kddesa",
            name="uq_rekap_desa_run_dasar_desa",
        ),
    )
    op.create_index("ix_rekap_desa_run_dasar", "rekap_desa", ["run_id", "dasar"], unique=False)


def _buat_rekap_kabupaten() -> None:
    """Buat tabel ``rekap_kabupaten`` (indeks tren kdprov+kdkab+dasar+run_id)."""
    op.create_table(
        "rekap_kabupaten",
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("dasar", sa.String(length=8), nullable=False),
        sa.Column("kdprov", sa.String(length=4), nullable=False),
        sa.Column("kdkab", sa.String(length=4), nullable=False),
        *[sa.Column(nama, sa.Integer(), nullable=False) for nama in KOLOM_HITUNGAN],
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "dasar", "kdprov", "kdkab"),
    )
    op.create_index(
        "ix_rekap_kabupaten_kab_dasar_run",
        "rekap_kabupaten",
        ["kdprov", "kdkab", "dasar", "run_id"],
        unique=False,
    )


def _buat_rekap_subsls() -> None:
    """Bentuk ``rekap_subsls`` 0004 (dipakai hanya oleh :func:`downgrade`)."""
    op.create_table(
        "rekap_subsls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("wilayah_id", sa.Integer(), nullable=True),
        sa.Column("dasar", sa.String(length=8), nullable=False),
        *[sa.Column(nama, sa.Integer(), nullable=False) for nama in KOLOM_HITUNGAN],
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


def _ada_tabel(koneksi: sa.Connection, nama: str) -> bool:
    """Apakah ``nama`` ada di basis data."""
    return bool(sa.inspect(koneksi).has_table(nama))


def _verifikasi(koneksi: sa.Connection, run_id: int, dasar: str) -> None:
    """Verifikasi rekap baru sama dengan snapshot ``rekap_subsls`` lama.

    Pembandingnya agregat per desa: ``rekap_subsls`` (per SubSLS) dijumlahkan lewat
    tabel ``wilayah``, jadi hasilnya harus sama dengan baris ``rekap_desa``.
    """
    if not _ada_tabel(koneksi, "rekap_subsls"):
        return

    kode_lama = ", ".join(f"COALESCE(w.{nama}, '')" for nama in KOLOM_KODE_DESA)
    baris_lama = koneksi.execute(
        sa.text(
            f"SELECT {kode_lama}, {', '.join(f'SUM(rs.{n})' for n in KOLOM_HITUNGAN)} "  # noqa: S608
            "FROM rekap_subsls rs LEFT JOIN wilayah w ON w.id = rs.wilayah_id "
            f"WHERE rs.run_id = :run AND rs.dasar = :dasar GROUP BY {kode_lama}"
        ),
        {"run": run_id, "dasar": dasar},
    )
    kode_baru = ", ".join(f"COALESCE({nama}, '')" for nama in KOLOM_KODE_DESA)
    baris_baru = koneksi.execute(
        sa.text(
            f"SELECT {kode_baru}, {', '.join(KOLOM_HITUNGAN)} FROM rekap_desa "  # noqa: S608
            "WHERE run_id = :run AND dasar = :dasar"
        ),
        {"run": run_id, "dasar": dasar},
    )

    def jadi_peta(baris: object) -> dict[tuple[str, ...], tuple[int, ...]]:
        peta: dict[tuple[str, ...], tuple[int, ...]] = {}
        for satu in baris:  # type: ignore[union-attr]
            kode = tuple(str(nilai) for nilai in satu[: len(KOLOM_KODE_DESA)])
            peta[kode] = tuple(int(nilai) for nilai in satu[len(KOLOM_KODE_DESA) :])
        return peta

    lama, baru = jadi_peta(baris_lama), jadi_peta(baris_baru)
    if lama == baru:
        return

    beda = [
        f"{kunci}: lama={lama.get(kunci)} baru={baru.get(kunci)}"
        for kunci in sorted(set(lama) | set(baru))
        if lama.get(kunci) != baru.get(kunci)
    ]
    raise RuntimeError(
        f"rekap hasil migrasi tidak sama dengan rekap_subsls lama "
        f"(run {run_id}, dasar {dasar}): " + "; ".join(beda[:5])
    )


def _isi_data() -> None:
    """Isi kolom baru + rekap baru dari data yang ada (tanpa memproses ulang berkas)."""
    koneksi = op.get_bind()

    # 1. Backfill kolom baru dari data yang sudah ada.
    koneksi.execute(sa.text("UPDATE runs SET tanggal_data = DATE(created_at)"))
    koneksi.execute(
        sa.text(
            "UPDATE runs SET kdprov = COALESCE(("
            "SELECT MIN(w.kdprov) FROM wilayah w "
            "WHERE w.kdkab = runs.kdkab AND w.kdprov IS NOT NULL), '')"
        )
    )

    run_ids = [
        int(baris[0])
        for baris in koneksi.execute(
            sa.text("SELECT DISTINCT run_id FROM titik_hasil ORDER BY run_id")
        )
    ]
    if not run_ids:
        return

    def run_ringkas(run_id: int) -> SimpleNamespace | None:
        """Kolom ``runs`` yang dipakai rekap, tanpa memuat model ORM lengkap.

        Migrasi tidak boleh bergantung pada kolom yang baru ditambahkan migrasi
        berikutnya (mis. ``heartbeat_at`` di 0006), jadi dibaca eksplisit.
        """
        baris = (
            koneksi.execute(
                sa.text("SELECT id, tipe, kdprov, kdkab FROM runs WHERE id = :id"),
                {"id": run_id},
            )
            .mappings()
            .first()
        )
        return None if baris is None else SimpleNamespace(**baris)

    # Session di atas koneksi migrasi: commit-nya hanya melepas savepoint, jadi
    # transaksi migrasi tetap utuh.
    sesi = Session(bind=koneksi, join_transaction_mode="create_savepoint")
    try:
        for run_id in run_ids:
            run = run_ringkas(run_id)
            if run is not None:
                # Rekap dibaca dari semua titik dulu, sebelum titik dipangkas di bawah.
                modul_rekap.simpan_rekap(sesi, run)  # type: ignore[arg-type]
                for dasar in modul_rekap.DASAR:
                    _verifikasi(koneksi, run_id, dasar)
        sesi.flush()
        for run_id in run_ids:
            run = run_ringkas(run_id)
            if run is not None:
                modul_rekap.pangkas_titik_hasil(sesi, run)  # type: ignore[arg-type]
        sesi.commit()
    finally:
        sesi.close()

    # Penanda konsisten dengan isi titik_hasil yang benar-benar tersimpan.
    koneksi.execute(
        sa.text(
            "UPDATE runs SET detail_tersedia = 1 "
            "WHERE detail_tersedia = 0 AND id IN (SELECT run_id FROM titik_hasil)"
        )
    )


def _tambah_kolom_runs() -> None:
    """Tambah kolom baru ``runs`` (``kdprov``, ``tanggal_data``, ``detail_tersedia``).

    Kolomnya ``NOT NULL`` dengan ``server_default`` supaya tabel lama tetap bisa
    di-ALTER; nilainya diisi sungguhan oleh :func:`_isi_data`. Di SQLite, ``ADD
    COLUMN`` dengan default non-konstan (``CURRENT_DATE``) tidak boleh kalau tabel
    sudah berisi baris, jadi tabelnya dibangun ulang dulu (hanya di SQLite; di
    MySQL tahap ini cuma ``ALTER TABLE``).
    """
    kolom = (
        sa.Column("kdprov", sa.String(length=4), nullable=False, server_default=""),
        sa.Column(
            "tanggal_data", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")
        ),
        sa.Column("detail_tersedia", ANGKA_KECIL, nullable=False, server_default="0"),
    )
    if op.get_context().dialect.name == "sqlite":
        with op.batch_alter_table("runs", recreate="always") as batch:
            for satu in kolom:
                batch.add_column(satu)
    else:
        for satu in kolom:
            op.add_column("runs", satu)


def upgrade() -> None:
    """Tambah kolom/tabel rekap baru, isi dari data lama, lalu hapus ``rekap_subsls``."""
    _tambah_kolom_runs()
    op.create_index(
        "ix_runs_kdprov_kdkab_tipe_tanggal",
        "runs",
        ["kdprov", "kdkab", "tipe", "tanggal_data"],
        unique=False,
    )

    _buat_rekap_desa()
    _buat_rekap_kabupaten()

    if not context.is_offline_mode():
        _isi_data()

    op.drop_index("ix_rekap_subsls_run_dasar", table_name="rekap_subsls")
    op.drop_table("rekap_subsls")


def downgrade() -> None:
    """Kembalikan skema 0004 (isi ``rekap_subsls`` tidak bisa dipulihkan)."""
    op.drop_index("ix_rekap_kabupaten_kab_dasar_run", table_name="rekap_kabupaten")
    op.drop_table("rekap_kabupaten")
    op.drop_index("ix_rekap_desa_run_dasar", table_name="rekap_desa")
    op.drop_table("rekap_desa")

    op.drop_index("ix_runs_kdprov_kdkab_tipe_tanggal", table_name="runs")
    op.drop_column("runs", "detail_tersedia")
    op.drop_column("runs", "tanggal_data")
    op.drop_column("runs", "kdprov")

    _buat_rekap_subsls()
