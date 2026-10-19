"""Model ORM untuk skema MySQL di PRD §7.

Empat tabel:

- ``runs``         : satu baris per job (unggahan berkas + pemrosesan Proses A/B);
- ``wilayah``      : dimensi wilayah, satu baris per SubSLS (kode ``idsubsls``),
  diisi dari peta yang diunggah dengan aturan **upsert** (tidak pernah dihapus);
- ``titik_hasil``  : hasil per titik (ramping, hanya kolom yang dipakai dashboard);
  nama/kode wilayah tidak disimpan di sini, cukup id-nya (``wilayah_asal_id``,
  ``wilayah_edit_id``), dan ``level_6_full_code`` tetap disimpan sebagai teks
  karena jadi kunci wilayah **tugas** pada rekap;
- ``rekap_subsls`` : snapshot rekap progres per SubSLS per job, dua dasar
  (``DASAR_TUGAS``/``DASAR_POSISI``), dihitung lewat query GROUP BY di DB; hitungan
  dipisah menjadi ``belum``/``sudah_posisi``/``sudah_manual``/``tanpa_wilayah``.

Catatan pilihan tipe:

- Kolom flag dan indikator kategori disimpan angka kecil (``TINYINT`` di MySQL,
  ``SMALLINT`` di SQLite karena SQLite tidak punya TINYINT): ``flag_*`` dan
  ``kk``/``btt``/``bku``/``bttk``/``bbtt`` bernilai 0/1, ``usaha`` jumlah usaha.
- Koordinat disimpan ``DOUBLE`` supaya presisi 7-8 angka di belakang koma tidak
  hilang (dipakai peta titik dan ekspor).
- ``titik_hasil`` memuat kolom Proses A dan Proses B; kolom khusus Proses B
  (``flag_position``, ``flag_edit_atr_repair``, ``wilayah_edit_id``,
  ``latitude_edited``, ``longitude_edited``) bernilai NULL untuk hasil Proses A.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
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
from sqlalchemy.dialects.mysql import TINYINT
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

# Nilai kolom ``rekap_subsls.dasar``:
# - tugas : wilayah penugasan titik, dari ``titik_hasil.level_6_full_code``
#   (kode SubSLS pada data titik, dibandingkan model QGIS dengan hasil join);
# - posisi: wilayah tempat titik berada menurut hasil join peta
#   (``wilayah_edit_id`` untuk Proses B, kalau kosong ``wilayah_asal_id``).
DASAR_TUGAS = "tugas"
DASAR_POSISI = "posisi"

# TINYINT di MySQL, SMALLINT di SQLite (SQLite hanya punya tipe INTEGER).
AngkaKecil = SmallInteger().with_variant(TINYINT(), "mysql")


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
    # Titik yang tidak masuk/menyentuh poligon wilkerstat mana pun (hasil join kosong).
    jumlah_tanpa_wilayah: Mapped[int | None] = mapped_column(Integer)
    pesan: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=sekarang)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    hasil: Mapped[list[TitikHasil]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class Wilayah(Base):
    """Dimensi wilayah: satu baris per SubSLS peta (kunci ``idsubsls``).

    Baris diisi dari peta yang diunggah (nama pendek seperti ``kdkab`` = ``07``
    mengikuti berkas sumber) dan tidak pernah dihapus; peta berikutnya hanya
    memperbarui nama/kode yang sudah ada.
    """

    __tablename__ = "wilayah"
    __table_args__ = (
        UniqueConstraint("idsubsls", name="uq_wilayah_idsubsls"),
        Index("ix_wilayah_kdkab", "kdkab"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idsubsls: Mapped[str] = mapped_column(String(16))
    idsls: Mapped[str | None] = mapped_column(String(16))
    nmsls: Mapped[str | None] = mapped_column(String(128))
    kdprov: Mapped[str | None] = mapped_column(String(4))
    nmprov: Mapped[str | None] = mapped_column(String(64))
    kdkab: Mapped[str | None] = mapped_column(String(4))
    nmkab: Mapped[str | None] = mapped_column(String(64))
    kdkec: Mapped[str | None] = mapped_column(String(8))
    nmkec: Mapped[str | None] = mapped_column(String(64))
    kddesa: Mapped[str | None] = mapped_column(String(16))
    nmdesa: Mapped[str | None] = mapped_column(String(64))


class TitikHasil(Base):
    """Hasil Proses A/B per titik (satu baris = satu ``assignment_id`` per job)."""

    __tablename__ = "titik_hasil"
    __table_args__ = (
        UniqueConstraint("run_id", "assignment_id", name="uq_titik_hasil_run_assignment"),
        Index("ix_titik_hasil_wilayah_asal", "wilayah_asal_id"),
        Index("ix_titik_hasil_wilayah_edit", "wilayah_edit_id"),
        Index("ix_titik_hasil_run_flag_repair", "run_id", "flag_repair"),
    )

    # Kunci utama gabungan: urut = urutan keluaran proses (dipakai untuk paging).
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    urut: Mapped[int] = mapped_column(Integer, primary_key=True)

    assignment_id: Mapped[str] = mapped_column(String(64))
    level_6_full_code: Mapped[str | None] = mapped_column(String(16))

    # Wilayah penugasan/posisi; NULL untuk titik di luar poligon wilkerstat.
    wilayah_asal_id: Mapped[int | None] = mapped_column(ForeignKey("wilayah.id"))
    wilayah_edit_id: Mapped[int | None] = mapped_column(ForeignKey("wilayah.id"))

    flag_psls: Mapped[int | None] = mapped_column(AngkaKecil)
    flag_position: Mapped[int | None] = mapped_column(AngkaKecil)
    flag_edit_atr_repair: Mapped[int | None] = mapped_column(AngkaKecil)
    flag_repair_initial: Mapped[int | None] = mapped_column(AngkaKecil)
    flag_repair: Mapped[int | None] = mapped_column(AngkaKecil)
    kk: Mapped[int | None] = mapped_column(AngkaKecil)
    btt: Mapped[int | None] = mapped_column(AngkaKecil)
    bku: Mapped[int | None] = mapped_column(AngkaKecil)
    bttk: Mapped[int | None] = mapped_column(AngkaKecil)
    bbtt: Mapped[int | None] = mapped_column(AngkaKecil)
    usaha: Mapped[int | None] = mapped_column(SmallInteger)

    latitude_origin: Mapped[float | None] = mapped_column(Double)
    longitude_origin: Mapped[float | None] = mapped_column(Double)
    latitude_edited: Mapped[float | None] = mapped_column(Double)
    longitude_edited: Mapped[float | None] = mapped_column(Double)

    run: Mapped[Run] = relationship(back_populates="hasil")


class RekapSubsls(Base):
    """Snapshot rekap progres per SubSLS per job, dipisah per ``dasar``.

    Diisi sekali di akhir job yang sukses lewat query GROUP BY (PRD §7), jadi
    dashboard tidak perlu memindai ``titik_hasil``. Barisnya bertahan walau
    ``titik_hasil`` job tersebut sudah digantikan job yang lebih baru.

    Hitungan dipisah (indikator progres PRD §5):

    - ``belum``          : titik dengan ``flag_repair`` = 1;
    - ``sudah_posisi``   : ``flag_repair`` = 0 dan ``flag_edit_atr_repair`` bukan 1
      (perbaikan lewat posisi; untuk Proses A yang kolomnya NULL, NULL dianggap 0);
    - ``sudah_manual``   : ``flag_repair`` = 0 dan ``flag_edit_atr_repair`` = 1
      (atribut diperbaiki manual);
    - ``tanpa_wilayah``  : titik pada baris itu yang tidak masuk poligon wilkerstat
      mana pun (``wilayah_asal_id`` dan ``wilayah_edit_id`` sama-sama kosong);
    - ``jumlah`` = ``belum`` + ``sudah_posisi`` + ``sudah_manual``.

    ``wilayah_id`` NULL = kategori terpisah "(tanpa wilayah)": titik yang tidak bisa
    dipetakan ke wilayah pada dasar itu (dasar ``tugas``: ``level_6_full_code``
    kosong atau tidak ada di tabel ``wilayah``; dasar ``posisi``: titik di luar semua
    poligon). Karena baris kategori ini tidak menunjuk wilayah, kunci utama dipindah
    ke ``id`` dan ``wilayah_id`` dibuat boleh NULL supaya FK tidak pernah gagal.
    """

    __tablename__ = "rekap_subsls"
    __table_args__ = (
        # UNIQUE ini menjaga satu baris per wilayah; baris kategori "(tanpa wilayah)"
        # (wilayah_id NULL) tidak dijaga di MySQL (NULL boleh berulang), dijaga oleh
        # penulisan snapshot yang selalu dibuang lalu diisi ulang dari GROUP BY.
        UniqueConstraint(
            "run_id", "dasar", "wilayah_id", name="uq_rekap_subsls_run_dasar_wilayah"
        ),
        Index("ix_rekap_subsls_run_dasar", "run_id", "dasar"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    wilayah_id: Mapped[int | None] = mapped_column(ForeignKey("wilayah.id"))
    dasar: Mapped[str] = mapped_column(String(8))

    jumlah: Mapped[int] = mapped_column(Integer)
    belum: Mapped[int] = mapped_column(Integer)
    sudah_posisi: Mapped[int] = mapped_column(Integer)
    sudah_manual: Mapped[int] = mapped_column(Integer)
    tanpa_wilayah: Mapped[int] = mapped_column(Integer)
