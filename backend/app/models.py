"""Model ORM untuk skema MySQL di PRD §7.

Tujuh tabel:

- ``runs``         : satu baris per job (unggahan berkas + pemrosesan Proses A/B);
  kunci kabupaten/kota adalah (**kdprov**, **kdkab**) dan ``tanggal_data`` (tanggal
  data) dipisah dari ``created_at`` (waktu unggah, UTC);
- ``wilayah``      : dimensi wilayah, satu baris per SubSLS (kode ``idsubsls``),
  diisi dari peta yang diunggah dengan aturan **upsert** (tidak pernah dihapus);
- ``titik_hasil``  : hasil per titik (ramping, hanya kolom yang dipakai dashboard);
  nama/kode wilayah tidak disimpan di sini, cukup id-nya (``wilayah_asal_id``,
  ``wilayah_edit_id``), dan ``level_6_full_code`` tetap disimpan sebagai teks
  karena jadi kunci wilayah **tugas** pada rekap. Yang disimpan **hanya titik yang
  perlu perhatian** (``flag_repair`` = 1, ``flag_edit_atr_repair`` = 1, atau tidak
  masuk poligon mana pun); titik ``benar_awal`` hanya terhitung di rekap
  (``rekap_desa``/``rekap_kabupaten``);
- ``rekap_desa``   : snapshot rekap progres per **desa** (``kdprov``+``kdkab``+
  ``kdkec``+``kddesa``) per job per dasar, plus satu baris "(tanpa wilayah)";
- ``rekap_kabupaten``: rekap yang sama dijumlahkan per **kabupaten/kota**
  (``kdprov``+``kdkab``) per job per dasar; dibaca untuk ringkasan dan tren;
- ``geotag_master``: geotag asli per kabupaten/kota yang diunggah admin provinsi.
  Berkasnya disimpan permanen (tidak ikut pemangkasan) dan dipakai ulang oleh
  banyak job Proses A. Versi lama tidak dihapus; job A mencatat versi yang dipakai.

Dua tabel rekap memakai kolom hitungan yang sama, dua dasar
(``DASAR_TUGAS``/``DASAR_POSISI``), dihitung lewat query GROUP BY di DB:
``jumlah``, ``belum``, ``benar_awal``, ``ditindak_posisi_benar``,
``ditindak_posisi_salah``, ``digeser``, ``tanpa_wilayah``.

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

from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
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

# Nilai kolom ``runs.status``: ``menunggu`` -> ``jalan`` -> ``sukses``/``gagal``.
STATUS_MENUNGGU = "menunggu"
STATUS_JALAN = "jalan"
STATUS_SUKSES = "sukses"
STATUS_GAGAL = "gagal"

# Nilai kolom ``rekap_desa.dasar``/``rekap_kabupaten.dasar``:
# - tugas : wilayah penugasan titik, dari ``titik_hasil.level_6_full_code``
#   (kode SubSLS pada data titik, dibandingkan model QGIS dengan hasil join);
# - posisi: wilayah tempat titik berada menurut hasil join peta
#   (``wilayah_edit_id`` untuk Proses B, kalau kosong ``wilayah_asal_id``).
DASAR_TUGAS = "tugas"
DASAR_POSISI = "posisi"

# Nilai kolom ``worker_heartbeat.status``.
WORKER_MENANGGUR = "menganggur"
WORKER_JALAN = "jalan"
WORKER_BERHENTI = "berhenti"

#: Kolom hitungan kedua tabel rekap (selain kunci dan kode wilayah).
KOLOM_HITUNGAN: tuple[str, ...] = (
    "jumlah",
    "belum",
    "benar_awal",
    "ditindak_posisi_benar",
    "ditindak_posisi_salah",
    "digeser",
    "tanpa_wilayah",
)

# TINYINT di MySQL, SMALLINT di SQLite (SQLite hanya punya tipe INTEGER).
AngkaKecil = SmallInteger().with_variant(TINYINT(), "mysql")

# id event operasional: BIGINT di MySQL, INTEGER di SQLite agar autoincrement.
IdBesar = BigInteger().with_variant(Integer, "sqlite")


def sekarang() -> datetime:
    """Waktu UTC (tanpa zona) untuk kolom waktu MySQL ``DATETIME``."""
    return datetime.now(UTC).replace(tzinfo=None)


def hari_ini() -> date:
    """Tanggal unggah (UTC) untuk default ``runs.tanggal_data``."""
    return datetime.now(UTC).date()


class Run(Base):
    """Satu kali unggah + pemrosesan (Proses A atau Proses B).

    Kunci kabupaten/kota di seluruh API dan query adalah (``kdprov``, ``kdkab``).
    ``created_at`` = waktu unggah (UTC), ``tanggal_data`` = tanggal data (boleh
    diisi saat unggah, default tanggal unggah).

    ``detail_tersedia`` = 1 kalau baris ``titik_hasil`` run ini masih disimpan
    (run **baseline** dan **sukses terakhir** per kabupaten/tipe); run lain hanya
    menyisakan baris ``runs`` dan rekapnya.
    """

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_kdprov_kdkab_tipe_tanggal", "kdprov", "kdkab", "tipe", "tanggal_data"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipe: Mapped[str] = mapped_column(String(1), index=True)
    kdprov: Mapped[str] = mapped_column(String(4))
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
    detail_tersedia: Mapped[int] = mapped_column(AngkaKecil, default=0)
    pesan: Mapped[str | None] = mapped_column(Text)
    tanggal_data: Mapped[date] = mapped_column(Date, default=hari_ini)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=sekarang)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    #: Waktu UTC heartbeat terakhir worker (diperbarui tiap batch simpan).
    #: Job ``jalan`` yang heartbeat-nya kedaluwarsa dianggap terhenti.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    #: Versi geotag master yang dipakai job A (NULL untuk job lama/Proses B).
    geotag_master_id: Mapped[int | None] = mapped_column(
        ForeignKey("geotag_master.id", ondelete="SET NULL"), index=True
    )
    #: Job A terakhir yang menjadi sumber peta/keluaran untuk job B.
    sumber_run_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )

    hasil: Mapped[list[TitikHasil]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class GeotagMaster(Base):
    """Geotag asli per kabupaten/kota yang diunggah admin provinsi.

    Berkas disimpan di ``DIR_MASTER`` (di luar folder unggahan run) agar tidak
    terhapus oleh pemangkasan berkas mentah. Setiap unggahan baru menjadi versi
    terbaru untuk (``kdprov``, ``kdkab``); versi lama tetap disimpan karena masih
    dirujuk oleh job Proses A yang sudah dibuat.
    """

    __tablename__ = "geotag_master"
    __table_args__ = (
        Index("ix_geotag_master_kdprov_kdkab", "kdprov", "kdkab"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kdprov: Mapped[str] = mapped_column(String(4))
    #: Kode 4 digit (provinsi + kabupaten/kota), mis. ``3307``.
    kdkab: Mapped[str] = mapped_column(String(4))
    tanggal_data: Mapped[date] = mapped_column(Date, default=hari_ini)
    nama_file: Mapped[str] = mapped_column(String(255))
    berkas: Mapped[str] = mapped_column(String(512))
    layer: Mapped[str | None] = mapped_column(String(64))
    jumlah_baris: Mapped[int | None] = mapped_column(Integer)
    user: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=sekarang)


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
    # BIGINT karena mode potongan memakai kunci urutan sementara yang lebih besar
    # dari batas INTEGER sebelum dirapikan menjadi 0..n-1.
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    urut: Mapped[int] = mapped_column(BigInteger, primary_key=True)

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


class RekapDesa(Base):
    """Snapshot rekap progres per **desa** per job, dipisah per ``dasar``.

    Diisi sekali di akhir job yang sukses lewat query GROUP BY (PRD §7), jadi
    dashboard tidak perlu memindai ``titik_hasil``. Barisnya **tidak pernah
    dihapus** (riwayat rekap tetap ada walau ``titik_hasil`` run tersebut sudah
    dipangkas).

    Kode desa = ``kdprov``+``kdkab``+``kdkec``+``kddesa``. Baris dengan kode NULL
    adalah kategori terpisah "(tanpa wilayah)": titik yang tidak bisa dipetakan ke
    wilayah pada dasar itu (dasar ``tugas``: ``level_6_full_code`` kosong atau tidak
    ada di tabel ``wilayah``; dasar ``posisi``: titik di luar semua poligon). Karena
    kolom kunci utama tidak boleh NULL di MySQL, kunci utama memakai ``id`` dan
    kombinasi kode dijaga UNIQUE.

    Hitungan dipisah (indikator progres PRD §5):

    - ``belum``                 : titik dengan ``flag_repair`` = 1;
    - ``benar_awal``            : ``flag_repair`` = 0 dan ``flag_edit_atr_repair``
      dianggap 0 (NULL pada Proses A) -- sudah benar tanpa tindakan manual;
    - ``ditindak_posisi_benar`` : ``flag_repair`` = 0, ``flag_edit_atr_repair`` = 1, dan
      ``flag_repair_initial`` = 0 -- petugas menindak atributnya dan posisi titik sekarang
      sudah di SubSLS tugasnya;
    - ``ditindak_posisi_salah`` : ``flag_repair`` = 0, ``flag_edit_atr_repair`` = 1, dan
      ``flag_repair_initial`` = 1 -- ditindak manual tetapi posisinya masih belum sesuai;
    - ``digeser``               : ``flag_position`` = 1 (titik dipindah; keterangan
      tersendiri, bisa tumpang tindih dengan kolom lain);
    - ``tanpa_wilayah``         : titik pada baris itu yang tidak masuk poligon wilkerstat
      mana pun (``wilayah_asal_id`` dan ``wilayah_edit_id`` sama-sama kosong);
    - ``jumlah`` = ``belum`` + ``benar_awal`` + ``ditindak_posisi_benar`` +
      ``ditindak_posisi_salah``.

    Persentase progres = (``ditindak_posisi_benar`` + ``ditindak_posisi_salah``) /
    (``belum`` + ``ditindak_posisi_benar`` + ``ditindak_posisi_salah``); kalau penyebutnya
    0 persentasenya kosong (NULL) -- dihitung di :func:`app.layanan.rekap_run`.
    """

    __tablename__ = "rekap_desa"
    __table_args__ = (
        # UNIQUE ini menjaga satu baris per desa; baris kategori "(tanpa wilayah)"
        # (kode NULL) tidak dijaga di MySQL (NULL boleh berulang), dijaga oleh
        # penulisan snapshot yang selalu dibuang lalu diisi ulang dari GROUP BY.
        UniqueConstraint(
            "run_id",
            "dasar",
            "kdprov",
            "kdkab",
            "kdkec",
            "kddesa",
            name="uq_rekap_desa_run_dasar_desa",
        ),
        Index("ix_rekap_desa_run_dasar", "run_id", "dasar"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    dasar: Mapped[str] = mapped_column(String(8))

    kdprov: Mapped[str | None] = mapped_column(String(4))
    kdkab: Mapped[str | None] = mapped_column(String(4))
    kdkec: Mapped[str | None] = mapped_column(String(8))
    kddesa: Mapped[str | None] = mapped_column(String(16))

    jumlah: Mapped[int] = mapped_column(Integer)
    belum: Mapped[int] = mapped_column(Integer)
    benar_awal: Mapped[int] = mapped_column(Integer)
    ditindak_posisi_benar: Mapped[int] = mapped_column(Integer)
    ditindak_posisi_salah: Mapped[int] = mapped_column(Integer)
    digeser: Mapped[int] = mapped_column(Integer)
    tanpa_wilayah: Mapped[int] = mapped_column(Integer)


class RekapKabupaten(Base):
    """Snapshot rekap progres per **kabupaten/kota** per job, dipisah per ``dasar``.

    Satu baris per (run, dasar) dengan kunci ``kdprov``+``kdkab`` milik run; kolomnya
    sama dengan :class:`RekapDesa` (lihat docstring-nya untuk arti tiap kolom) dan
    ``tanpa_wilayah`` di sini tetap berupa kolom, bukan baris terpisah.

    Indeks ``(kdprov, kdkab, dasar, run_id)`` dipakai query tren/ringkasan; barisnya
    tidak pernah dihapus.
    """

    __tablename__ = "rekap_kabupaten"
    __table_args__ = (
        Index("ix_rekap_kabupaten_kab_dasar_run", "kdprov", "kdkab", "dasar", "run_id"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    dasar: Mapped[str] = mapped_column(String(8), primary_key=True)
    kdprov: Mapped[str] = mapped_column(String(4), primary_key=True)
    kdkab: Mapped[str] = mapped_column(String(4), primary_key=True)

    jumlah: Mapped[int] = mapped_column(Integer)
    belum: Mapped[int] = mapped_column(Integer)
    benar_awal: Mapped[int] = mapped_column(Integer)
    ditindak_posisi_benar: Mapped[int] = mapped_column(Integer)
    ditindak_posisi_salah: Mapped[int] = mapped_column(Integer)
    digeser: Mapped[int] = mapped_column(Integer)
    tanpa_wilayah: Mapped[int] = mapped_column(Integer)


class WorkerHeartbeat(Base):
    """Denyut satu proses worker; satu baris per ``worker_id``.

    Baris ini diperbarui worker saat menganggur maupun saat mengerjakan job,
    sehingga Status Sistem dapat membedakan worker hidup tetapi menganggur dari
    worker yang mati tanpa pesan. Baris lama tidak dihapus agar riwayat singkat
    tetap terlihat; ``heartbeat_at`` yang kedaluwarsa berarti worker mati.
    """

    __tablename__ = "worker_heartbeat"
    __table_args__ = (
        Index("ix_worker_heartbeat_status_heartbeat", "status", "heartbeat_at"),
    )

    worker_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    pid: Mapped[int | None] = mapped_column(Integer)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )
    hostname: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default=WORKER_MENANGGUR)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=sekarang)
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime, default=sekarang, index=True
    )


class WorkerEvent(Base):
    """Catatan kejadian operasional worker untuk halaman Status Sistem.

    Event ditulis saat worker mulai/berhenti, klaim job, progres penting, sukses,
    gagal, job terhenti, dan pelanggaran anggaran memori. Tabel dipangkas berkala
    oleh worker (``WORKER_EVENT_RETENSI_HARI``/``WORKER_EVENT_MAKS``).
    """

    __tablename__ = "worker_event"
    __table_args__ = (
        Index("ix_worker_event_created", "created_at"),
        Index("ix_worker_event_run_created", "run_id", "created_at"),
        Index("ix_worker_event_worker_created", "worker_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(IdBesar, primary_key=True, autoincrement=True)
    worker_id: Mapped[str | None] = mapped_column(String(80))
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL")
    )
    level: Mapped[str] = mapped_column(String(16), default="info")
    jenis: Mapped[str] = mapped_column(String(32))
    pesan: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=sekarang)


#: Pengguna dianggap online bila heartbeat terakhirnya masih dalam rentang ini.
PENGGUNA_ONLINE_DETIK = 120
#: Jeda tanpa heartbeat yang dianggap sesi baru saat pengguna kembali aktif.
PENGGUNA_LOGIN_BARU_MENIT = 30


class PenggunaAktif(Base):
    """Kehadiran pengguna yang pernah masuk ke PointSE.

    Satu baris per ``sub`` SSO. Baris diperbarui oleh heartbeat dari shell
    dashboard (bukan setiap request API) agar beban tulis tetap kecil. Data ini
    hanya untuk pemantauan admin provinsi; bukan sumber otorisasi.
    """

    __tablename__ = "pengguna_aktif"
    __table_args__ = (
        Index(
            "ix_pengguna_aktif_kdprov_terakhir",
            "kdprov",
            "terakhir_aktif",
        ),
    )

    sub: Mapped[str] = mapped_column(String(128), primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    nama: Mapped[str] = mapped_column(String(128))
    nip: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(128))
    org: Mapped[str] = mapped_column(String(8))
    peran: Mapped[str] = mapped_column(String(32))
    kdprov: Mapped[str] = mapped_column(String(4))
    kdkab: Mapped[str | None] = mapped_column(String(4))
    foto_url: Mapped[str | None] = mapped_column(Text)
    login_pada: Mapped[datetime] = mapped_column(DateTime, default=sekarang)
    terakhir_aktif: Mapped[datetime] = mapped_column(DateTime, default=sekarang)


class Aktivitas(Base):
    """Jejak audit tindakan pengguna, termasuk identitas SSO pelakunya.

    Ditulis setelah tindakan berhasil (mis. job dibuat atau master diunggah)
    agar admin provinsi dapat melihat siapa melakukan apa. Baris audit tidak
    dipakai untuk otorisasi dan tidak dihapus otomatis.
    """

    __tablename__ = "aktivitas"
    __table_args__ = (
        Index("ix_aktivitas_kdprov_created", "kdprov", "created_at"),
        Index("ix_aktivitas_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(IdBesar, primary_key=True, autoincrement=True)
    sub: Mapped[str] = mapped_column(String(128))
    username: Mapped[str] = mapped_column(String(64))
    nama: Mapped[str] = mapped_column(String(128))
    nip: Mapped[str | None] = mapped_column(String(32))
    peran: Mapped[str] = mapped_column(String(32))
    kdprov: Mapped[str] = mapped_column(String(4))
    kdkab: Mapped[str | None] = mapped_column(String(4))
    foto_url: Mapped[str | None] = mapped_column(Text)
    aksi: Mapped[str] = mapped_column(String(32))
    objek: Mapped[str] = mapped_column(String(32))
    objek_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=sekarang)
