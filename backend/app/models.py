"""Model ORM untuk skema MySQL di PRD §7 (``runs`` dan ``titik_hasil``).

Catatan pilihan tipe:

- Kolom atribut yang di berkas sumber tersimpan sebagai teks (``no_bang``,
  ``kode_bang_value``, ``jumlah_usaha_ditemukan``, ...) tetap disimpan
  ``VARCHAR`` supaya nilainya sama persis (mis. angka nol di depan pada
  ``no_bang``). Kolom flag hasil hitungan (``flag_*``, ``kk``, ``btt``, ...)
  disimpan ``SMALLINT`` karena dihitung sendiri oleh Proses A/B.
- Koordinat disimpan ``DOUBLE`` (bukan ``FLOAT``) supaya presisi 7-8 angka di
  belakang koma tidak hilang.
- ``titik_hasil`` memuat gabungan kolom keluaran Proses A dan Proses B; kolom
  khusus Proses B (``flag_position``, ``idsubsls_edited``, ...) bernilai NULL
  untuk hasil Proses A.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Nilai kolom ``runs.tipe``
TIPE_A = "A"
TIPE_B = "B"

# Nilai kolom ``runs.status`` (``digantikan`` = hasilnya sudah digantikan job
# yang lebih baru untuk kabupaten/tipe yang sama)
STATUS_MENUNGGU = "menunggu"
STATUS_JALAN = "jalan"
STATUS_SUKSES = "sukses"
STATUS_GAGAL = "gagal"
STATUS_DIGANTIKAN = "digantikan"


def sekarang() -> datetime:
    """Waktu UTC (tanpa zona) untuk kolom waktu MySQL ``DATETIME``."""
    return datetime.now(UTC).replace(tzinfo=None)


class Run(Base):
    """Satu kali unggah + pemrosesan (Proses A atau Proses B)."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipe: Mapped[str] = mapped_column(String(1), index=True)
    kdkab: Mapped[str] = mapped_column(String(4), index=True)
    user: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True, default=STATUS_MENUNGGU)

    # Berkas mentah hanya di disk server (PRD §3); DB menyimpan nama + path.
    nama_file_input: Mapped[str] = mapped_column(String(255))
    nama_file_peta: Mapped[str] = mapped_column(String(255))
    berkas_input: Mapped[str] = mapped_column(String(512))
    berkas_peta: Mapped[str] = mapped_column(String(512))
    layer_input: Mapped[str | None] = mapped_column(String(64))
    layer_peta: Mapped[str | None] = mapped_column(String(64))

    jumlah_baris: Mapped[int | None] = mapped_column(Integer)
    pesan: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=sekarang)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    hasil: Mapped[list[TitikHasil]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class TitikHasil(Base):
    """Hasil Proses A/B per titik (satu baris = satu ``assignment_id``)."""

    __tablename__ = "titik_hasil"
    __table_args__ = (
        UniqueConstraint("run_id", "assignment_id", name="uq_titik_hasil_run_assignment"),
        Index("ix_titik_hasil_assignment_id", "assignment_id"),
        Index("ix_titik_hasil_idsubsls_origin", "idsubsls_origin"),
        Index("ix_titik_hasil_kdkab", "kdkab"),
        Index("ix_titik_hasil_run_flag_repair", "run_id", "flag_repair"),
    )

    # BIGINT di MySQL, INTEGER di SQLite (SQLite hanya auto-increment untuk INTEGER)
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )

    assignment_id: Mapped[str] = mapped_column(String(64))
    unique_bang: Mapped[str | None] = mapped_column(String(64))
    flag_psls: Mapped[int | None] = mapped_column(SmallInteger)
    flag_position: Mapped[int | None] = mapped_column(SmallInteger)
    flag_edit_atr_repair: Mapped[int | None] = mapped_column(SmallInteger)
    flag_repair_initial: Mapped[int | None] = mapped_column(SmallInteger)
    flag_repair: Mapped[int | None] = mapped_column(SmallInteger)
    level_6_full_code: Mapped[str | None] = mapped_column(String(32))
    idsubsls_origin: Mapped[str | None] = mapped_column(String(32))
    idsubsls_edited: Mapped[str | None] = mapped_column(String(32))
    latitude_origin: Mapped[float | None] = mapped_column(Double)
    longitude_origin: Mapped[float | None] = mapped_column(Double)
    latitude_edited: Mapped[float | None] = mapped_column(Double)
    longitude_edited: Mapped[float | None] = mapped_column(Double)
    no_bang: Mapped[str | None] = mapped_column(String(32))
    kode_bang_value: Mapped[str | None] = mapped_column(String(8))
    ada_keluarga_value: Mapped[str | None] = mapped_column(String(4))
    ada_bang_usaha_value: Mapped[str | None] = mapped_column(String(4))
    jumlah_usaha_ditemukan: Mapped[str | None] = mapped_column(String(8))
    kk: Mapped[int | None] = mapped_column(SmallInteger)
    btt: Mapped[int | None] = mapped_column(SmallInteger)
    bku: Mapped[int | None] = mapped_column(SmallInteger)
    bttk: Mapped[int | None] = mapped_column(SmallInteger)
    bbtt: Mapped[int | None] = mapped_column(SmallInteger)
    usaha: Mapped[str | None] = mapped_column(String(8))
    kdprov: Mapped[str | None] = mapped_column(String(2))
    nmprov: Mapped[str | None] = mapped_column(String(64))
    kdkab: Mapped[str | None] = mapped_column(String(4))
    nmkab: Mapped[str | None] = mapped_column(String(64))
    kdkec: Mapped[str | None] = mapped_column(String(8))
    nmkec: Mapped[str | None] = mapped_column(String(64))
    kddesa: Mapped[str | None] = mapped_column(String(16))
    nmdesa: Mapped[str | None] = mapped_column(String(64))
    nmsls: Mapped[str | None] = mapped_column(String(128))
    nama_usaha_bang: Mapped[str | None] = mapped_column(String(255))

    run: Mapped[Run] = relationship(back_populates="hasil")
