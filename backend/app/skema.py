"""Skema balasan (Pydantic) untuk API pointse.

Dipisah dari model ORM supaya bentuk JSON API tidak ikut berubah saat kolom DB
berubah.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RunOut(BaseModel):
    """Ringkasan satu job (baris tabel ``runs``).

    ``detail_tersedia`` = 1 kalau baris ``titik_hasil`` run ini masih disimpan
    (run baseline dan run sukses terakhir per kabupaten/tipe).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    #: Nomor urut untuk tampilan, dihitung per (kdprov, kdkab, tipe).
    nomor_urut: int | None = None
    tipe: str
    kdprov: str
    kdkab: str
    user: str | None = None
    status: str
    nama_file_input: str
    nama_file_peta: str
    layer_input: str | None = None
    layer_peta: str | None = None
    jumlah_baris: int | None = None
    jumlah_tanpa_wilayah: int | None = None
    detail_tersedia: bool = False
    pesan: str | None = None
    tanggal_data: date
    created_at: datetime
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    geotag_master_id: int | None = None
    #: Nomor versi master pada kdkab run ini.
    geotag_master_nomor: int | None = None
    sumber_run_a_id: int | None = None
    #: Nomor urut run A sumber pada (kdprov, kdkab, tipe A).
    sumber_run_a_nomor: int | None = None
    #: Semester peta SLS yang divalidasi run V (mis. ``2026_1``); NULL untuk A/B.
    semester: str | None = None
    #: Nomor antrean global khusus job ``menunggu`` (1 = paling depan, urutan
    #: klaim worker); ``None`` untuk status lain.
    antrean_ke: int | None = None


class UnggahanOut(BaseModel):
    """Hasil satu unggahan body mentah yang sudah selesai."""

    unggahan_id: str
    nama: str
    ukuran: int
    sha256: str
    jenis: str


class UnggahanMulaiIn(BaseModel):
    """Permintaan memulai sesi unggahan berpotongan."""

    nama: str
    ukuran: int
    jenis: Literal["master", "peta", "titik"]


class UnggahanMulaiOut(BaseModel):
    """Sesi unggahan baru beserta ukuran potongan yang harus dipakai."""

    unggahan_id: str
    nama: str
    ukuran: int
    jenis: str
    ukuran_potongan: int
    jumlah_potongan: int


class UnggahanStatusOut(UnggahanMulaiOut):
    """Status sesi untuk melanjutkan unggahan yang terputus."""

    potongan_diterima: list[int]
    selesai: bool = False
    sha256: str | None = None


class PotonganOut(BaseModel):
    """Balasan setelah satu potongan diterima."""

    unggahan_id: str
    potongan: int
    ukuran: int
    diterima: bool = True


class MasterGeotagOut(BaseModel):
    """Satu versi geotag master (tanpa path berkas di disk)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    #: Nomor versi untuk tampilan, dihitung per kdkab.
    nomor_versi: int | None = None
    kdprov: str
    kdkab: str
    tanggal_data: date
    nama_file: str
    layer: str | None = None
    jumlah_baris: int | None = None
    user: str | None = None
    created_at: datetime


class DaftarMasterOut(BaseModel):
    """Balasan daftar geotag master (terbaru lebih dulu)."""

    total: int
    baris: list[MasterGeotagOut]


class RunDetailOut(RunOut):
    """Ringkasan job + jumlah baris hasil yang sudah tersimpan."""

    jumlah_tersimpan: int


class DaftarRunOut(BaseModel):
    """Balasan daftar job dengan paging."""

    total: int
    baris: list[RunOut]


class KonfirmasiValidasiSlsOut(BaseModel):
    """Konfirmasi satu temuan validasi SLS beserta keputusan persetujuan provinsi."""

    status: str
    label: str
    catatan: str | None = None
    oleh: str | None = None
    username: str | None = None
    peran: str | None = None
    pada: datetime | None = None
    kunci: str | None = None
    #: Status persetujuan provinsi: ``disetujui`` / ``ditolak`` / ``None`` (menunggu).
    persetujuan_status: str | None = None
    persetujuan_catatan: str | None = None
    persetujuan_oleh: str | None = None
    persetujuan_pada: datetime | None = None


class ValidasiUnmatchBarisOut(BaseModel):
    """Satu temuan unmatch run V: pasangan sisi peta vs sisi master + konfirmasi."""

    id: int | None = None
    jenis: str
    idsls_peta: str | None = None
    idsubsls_peta: str | None = None
    idsls_master: str | None = None
    idsubsls_master: str | None = None
    nmsls: str | None = None
    catatan: str | None = None
    kunci: str | None = None
    konfirmasi: KonfirmasiValidasiSlsOut | None = None


class ValidasiRingkasanBarisOut(BaseModel):
    """Satu kabupaten/kota: run V terakhir + target/selesai/sisa + hitungan jenis."""

    kdprov: str
    kdkab: str
    run_id: int
    status: str
    tanggal_data: date
    semester: str | None = None
    #: Kapan run terakhir selesai diproses (jam:menit:detik); None bila masih antre/jalan.
    selesai_pada: datetime | None = None
    #: Pengunggah run terakhir (None bila tak tercatat/belum ada run).
    petugas: str | None = None
    total: int
    per_jenis: dict[str, int] = Field(default_factory=dict)
    #: Target = jumlah pasangan master kab ini (None bila master belum ada).
    target: int | None = None
    #: Pasangan master yang cocok persis tanpa temuan (None bila run belum final).
    selesai: int | None = None
    #: Sisa = target - selesai (None bila salah satunya belum diketahui).
    sisa: int | None = None
    #: Ringkasan progres konfirmasi temuan pada run V terakhir ini.
    terkonfirmasi: int = 0
    akan_diperbaiki: int = 0
    sesuai_kenyataan: int = 0
    disetujui: int = 0
    ditolak: int = 0
    menunggu_persetujuan: int = 0


class KonfirmasiValidasiSlsMasuk(BaseModel):
    """Permintaan simpan konfirmasi temuan validasi SLS (kabupaten/kota maupun provinsi)."""

    unmatch_ids: list[int] = Field(default_factory=list)
    status: str
    catatan: str | None = Field(None, max_length=2000)


class PersetujuanValidasiSlsMasuk(BaseModel):
    """Permintaan persetujuan/penolakan Admin Provinsi atas alasan 'Sesuai Kondisi Kenyataan'."""

    unmatch_ids: list[int] = Field(default_factory=list)
    keputusan: str
    catatan: str | None = Field(None, max_length=2000)


class ValidasiRingkasanOut(BaseModel):
    """Ringkasan validasi SLS per kabupaten/kota (run V terakhir tiap kab)."""

    baris: list[ValidasiRingkasanBarisOut]


class ValidasiUnmatchOut(BaseModel):
    """Daftar unmatch satu run V (paging, urut ``idsls``)."""

    run_id: int
    total: int
    limit: int
    offset: int
    baris: list[ValidasiUnmatchBarisOut]


class HasilOut(BaseModel):
    """Balasan hasil titik (paging).

    ``detail_tersedia`` menjelaskan apakah baris ``titik_hasil`` run ini masih ada;
    kalau ``false``, ``total`` = 0 karena detailnya sudah dipangkas (angka rekapnya
    tetap utuh di ``rekap_desa``/``rekap_kabupaten``).
    """

    run_id: int
    detail_tersedia: bool
    total: int
    limit: int
    offset: int
    baris: list[dict[str, Any]]


class RekapBarisOut(BaseModel):
    """Rekap progres satu wilayah.

    ``persen_progres`` = (``ditindak_posisi_benar`` + ``ditindak_posisi_salah``) /
    (``belum`` + ``ditindak_posisi_benar`` + ``ditindak_posisi_salah``); ``None``
    (kosong) kalau penyebutnya 0.
    """

    kode: str | None = None
    nama: str | None = None
    jumlah: int
    belum: int
    ditindak_posisi_benar: int
    ditindak_posisi_salah: int
    benar_awal: int
    digeser: int
    tanpa_wilayah: int
    persen_progres: float | None = None


class RekapOut(BaseModel):
    """Rekap progres satu job, dikelompokkan per tingkat wilayah.

    Dipakai tingkat ``kabupaten``/``kecamatan``/``desa`` (dibaca dari
    ``rekap_kabupaten``/``rekap_desa``).
    """

    run_id: int
    tingkat: str
    dasar: str
    total: int
    belum: int
    ditindak_posisi_benar: int
    ditindak_posisi_salah: int
    benar_awal: int
    digeser: int
    tanpa_wilayah: int
    persen_progres: float | None = None
    baris: list[RekapBarisOut]


class RekapDetailBarisOut(BaseModel):
    """Rekap satu SLS/SubSLS (dihitung dari ``titik_hasil``).

    Hanya ``belum`` dan ``ditindak`` (jumlah ``ditindak_posisi_benar`` +
    ``ditindak_posisi_salah``) yang bisa dihitung: titik ``benar_awal`` sudah
    dipangkas dari penyimpanan (hanya terhitung di ``rekap_desa``/``rekap_kabupaten``).
    """

    kode: str | None = None
    nama: str | None = None
    belum: int
    ditindak: int
    persen_progres: float | None = None


class RekapDetailOut(BaseModel):
    """Balasan drill-down SLS/SubSLS satu job.

    Bentuknya sengaja berbeda dari :class:`RekapOut` (``ditindak`` gabungan, tanpa
    ``jumlah``/``benar_awal``/``digeser``) karena dihitung dari ``titik_hasil``.
    """

    run_id: int
    tingkat: str
    dasar: str
    belum: int
    ditindak: int
    persen_progres: float | None = None
    baris: list[RekapDetailBarisOut]


class RingkasanTipeOut(BaseModel):
    """Run sukses terakhir satu tipe untuk satu kabupaten/kota."""

    tipe: str
    run_id: int
    tanggal_data: date
    belum: int
    ditindak: int
    persen_progres: float | None = None


class RingkasanBarisOut(BaseModel):
    """Ringkasan satu kabupaten/kota (satu baris per kabupaten/kota)."""

    kdprov: str
    kdkab: str
    nmprov: str | None = None
    nmkab: str | None = None
    belum_ada_upload_tipe_b: bool
    terakhir: list[RingkasanTipeOut]


class RingkasanOut(BaseModel):
    """Ringkasan provinsi: daftar kabupaten/kota."""

    baris: list[RingkasanBarisOut]


class ProgresBTargetOut(BaseModel):
    """Target Proses B dari run Proses A terbaru."""

    run_a_id: int
    nomor_urut: int | None = None
    tanggal_data: date
    total: int
    flag_1: int


class ProgresBBarisOut(BaseModel):
    """Satu upload Proses B dan posisinya terhadap target awal."""

    run_id: int
    nomor_urut: int | None = None
    tanggal_data: date
    selesai_pada: datetime | None = None
    total: int
    sisa_flag_1: int
    beres: int
    persen: float | None = None
    perubahan: int


class ProgresBOut(BaseModel):
    """Perjalanan Proses B satu kabupaten/kota."""

    kdprov: str
    kdkab: str
    nmprov: str | None = None
    nmkab: str | None = None
    target: ProgresBTargetOut | None = None
    baris: list[ProgresBBarisOut] = Field(default_factory=list)


class TabulasiProgresRunOut(BaseModel):
    """Run sumber angka tabulasi (target A atau pembanding B)."""

    run_id: int
    nomor_urut: int | None = None
    tanggal_data: date
    #: Nama pengunggah run sumber (A atau B).
    pengunggah: str | None = None


class TabulasiProgresBarisOut(BaseModel):
    """Satu baris tabulasi untuk satu wilayah pada satu tingkat."""

    kode: str | None = None
    induk: str | None = None
    nama: str | None = None
    level: str
    jumlah: int
    target: int
    selesai: int
    sisa: int
    persen: float | None = None
    status: str
    ada_b: bool
    #: Nama pengunggah Proses B terakhir untuk wilayah/kabupaten ini.
    pengunggah: str | None = None
    #: Cakupan B pada anak langsung baris ini (mis. 5 dari 18 kecamatan).
    cakupan_ada: int = 0
    cakupan_total: int = 0
    cakupan_unit: str | None = None


class TabulasiProgresOut(BaseModel):
    """Tabulasi drill-down kabupaten/kota -> kecamatan -> desa."""

    tingkat: str
    dasar: str
    kdprov: str
    kdkab: str | None = None
    kdkec: str | None = None
    nmprov: str | None = None
    nmkab: str | None = None
    nmkec: str | None = None
    target: TabulasiProgresRunOut | None = None
    pembanding: TabulasiProgresRunOut | None = None
    baris: list[TabulasiProgresBarisOut] = Field(default_factory=list)


class TrenBarisOut(BaseModel):
    """Satu titik tren: per (kabupaten/kota atau provinsi, tipe, tanggal data)."""

    tingkat: str
    kdprov: str
    kdkab: str | None = None
    tipe: str
    tanggal_data: date
    run_id: int | None = None
    belum: int
    ditindak: int
    persen_progres: float | None = None


class TrenOut(BaseModel):
    """Tren progres per tanggal data."""

    tingkat: str
    dasar: str
    tipe: str | None = None
    baris: list[TrenBarisOut]


class SelisihOut(BaseModel):
    """Selisih (akhir - awal) kolom hitungan rekap."""

    jumlah: int
    belum: int
    benar_awal: int
    ditindak_posisi_benar: int
    ditindak_posisi_salah: int
    digeser: int
    tanpa_wilayah: int


class PerubahanDesaOut(BaseModel):
    """Selisih rekap satu desa; kode ``null`` = kategori "(tanpa wilayah)"."""

    kdprov: str | None = None
    kdkab: str | None = None
    kdkec: str | None = None
    kddesa: str | None = None
    selisih: SelisihOut


class PerubahanTitikBarisOut(BaseModel):
    """Perubahan status satu titik (``assignment_id``).

    ``status_*`` = ``belum``/``benar_awal``/``ditindak_posisi_benar``/
    ``ditindak_posisi_salah``; titik yang tidak ada di ``titik_hasil`` sebuah run
    berarti ``benar_awal`` pada run itu (detailnya sudah dipangkas).
    """

    assignment_id: str
    status_awal: str
    status_akhir: str
    flag_repair_awal: int | None = None
    flag_repair_akhir: int | None = None
    flag_edit_atr_repair_awal: int | None = None
    flag_edit_atr_repair_akhir: int | None = None
    flag_repair_initial_awal: int | None = None
    flag_repair_initial_akhir: int | None = None


class PerubahanTitikOut(BaseModel):
    """Perubahan status per titik (hanya baseline vs run sukses terakhir)."""

    run_awal: int
    run_akhir: int
    total: int
    limit: int
    offset: int
    baris: list[PerubahanTitikBarisOut]


class PerubahanOut(BaseModel):
    """Perubahan antara dua run: selisih rekap + (kalau memenuhi syarat) per titik."""

    run_awal: int
    run_akhir: int
    dasar: str
    kabupaten: SelisihOut
    desa: list[PerubahanDesaOut]
    titik: PerubahanTitikOut | None = None
    catatan: str | None = None


class JobSistemOut(BaseModel):
    """Ringkasan job untuk halaman status sistem (tanpa path berkas)."""

    id: int
    tipe: str
    kdprov: str
    kdkab: str
    user: str | None = None
    status: str
    jumlah_baris: int | None = None
    jumlah_tanpa_wilayah: int | None = None
    pesan: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    #: Umur heartbeat dalam detik; ``None`` bila job tidak sedang berjalan.
    umur_heartbeat_detik: int | None = None


class AntreanOut(BaseModel):
    """Hitungan job per status dan waktu tunggu paling lama."""

    menunggu: int
    jalan: int
    sukses: int
    #: Run validasi ber-temuan tetapi masih punya pasangan fully-clean.
    belum_clean: int = 0
    gagal: int
    total: int
    tertua_menunggu: datetime | None = None


class MemoriOut(BaseModel):
    """Pemakaian memori server dan proses API/worker (satuan MB)."""

    total_mb: float | None = None
    tersedia_mb: float | None = None
    terpakai_mb: float | None = None
    persen_terpakai: float | None = None
    swap_total_mb: float | None = None
    swap_terpakai_mb: float | None = None
    api_rss_mb: float | None = None
    worker_rss_mb: float | None = None


class DiskOut(BaseModel):
    """Pemakaian disk tempat berkas unggahan (satuan MB)."""

    total_mb: float | None = None
    terpakai_mb: float | None = None
    tersedia_mb: float | None = None
    persen_terpakai: float | None = None


class SistemOut(BaseModel):
    """Metrik host yang tidak bergantung pada worker."""

    hostname: str
    cpu: int | None = None
    load_1: float | None = None
    load_5: float | None = None
    load_15: float | None = None
    memori: MemoriOut
    disk: DiskOut


class WorkerOut(BaseModel):
    """Status proses worker dan batas memorinya."""

    aktif: bool
    pid: int | None = None
    rss_mb: float | None = None
    batas_memori_mb: int
    jumlah_proses: int = 0


class KonfigurasiWorkerOut(BaseModel):
    """Nilai worker yang berguna untuk membaca status antrean."""

    poll_detik: float
    heartbeat_detik: float
    timeout_menit: int
    chunk_titik: int
    max_workers: int


class WorkerHeartbeatOut(BaseModel):
    """Satu baris denyut worker; ``aktif`` dihitung dari umur heartbeat."""

    worker_id: str
    pid: int | None = None
    run_id: int | None = None
    hostname: str | None = None
    status: str
    started_at: datetime
    heartbeat_at: datetime
    umur_heartbeat_detik: int
    aktif: bool


class WorkerEventOut(BaseModel):
    """Satu kejadian operasional worker untuk riwayat Status Sistem."""

    id: int
    worker_id: str | None = None
    run_id: int | None = None
    level: str
    jenis: str
    pesan: str
    created_at: datetime


class BackupOut(BaseModel):
    """Status backup harian dari berkas JSON ``deploy/backup.sh``."""

    dikonfigurasi: bool = False
    file_ada: bool = False
    status: str = "belum_dikonfigurasi"
    waktu_mulai: datetime | None = None
    waktu_selesai: datetime | None = None
    berkas: str | None = None
    ukuran_bytes: int | None = None
    pesan: str | None = None
    umur_jam: float | None = None


class SistemStatusOut(BaseModel):
    """Balasan halaman admin Status Sistem.

    ``worker.aktif`` dibaca dari berkas flock, bukan dari heartbeat job, supaya
    worker yang menganggur tetap terlihat hidup. ``job_aktif`` berisi job
    berstatus ``jalan`` (biasanya satu); daftar dipakai agar job terhenti yang
    tertinggal tetap terlihat.
    """

    waktu: datetime
    sistem: SistemOut
    worker: WorkerOut
    konfigurasi: KonfigurasiWorkerOut
    antrean: AntreanOut
    job_aktif: list[JobSistemOut]
    job_terakhir: JobSistemOut | None = None
    heartbeats: list[WorkerHeartbeatOut] = []
    kejadian: list[WorkerEventOut] = []
    backup: BackupOut = BackupOut()
    peringatan: list[str]


class PenggunaAktifOut(BaseModel):
    """Satu pengguna yang pernah/login dan heartbeat-nya tercatat."""

    model_config = ConfigDict(from_attributes=True)

    sub: str
    username: str
    nama: str
    nip: str | None = None
    email: str | None = None
    org: str
    peran: str
    kdprov: str
    kdkab: str | None = None
    foto_url: str | None = None
    login_pada: datetime
    terakhir_aktif: datetime
    online: bool = False


class DaftarPenggunaAktifOut(BaseModel):
    """Daftar pengguna untuk halaman pemantauan admin provinsi."""

    total: int
    online: int
    baris: list[PenggunaAktifOut]


class AktivitasOut(BaseModel):
    """Satu tindakan pengguna yang tercatat di jejak audit."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sub: str
    username: str
    nama: str
    nip: str | None = None
    peran: str
    kdprov: str
    kdkab: str | None = None
    foto_url: str | None = None
    aksi: str
    objek: str
    objek_id: int | None = None
    detail: str | None = None
    created_at: datetime


class DaftarAktivitasOut(BaseModel):
    """Daftar aktivitas terbaru untuk admin provinsi."""

    total: int
    baris: list[AktivitasOut]


class AnomaliRunOut(BaseModel):
    """Run Proses B yang anomalinya ditampilkan (sukses terakhir)."""

    run_id: int
    tanggal_data: date
    pengunggah: str | None = None
    #: Kode kabupaten/kota pemilik run (4 digit).
    kdkab: str | None = None
    target: int = 0
    selesai: int = 0
    #: 0 = job ini belum dihitung ulang setelah fitur anomali ada.
    anomali_versi: int = 0
    #: Total titik anomali run ini (0 = bersih). ``None`` = job lama.
    jumlah_anomali: int | None = None


class DaftarAnomaliRunOut(BaseModel):
    """Riwayat run Proses B sukses satu kabupaten/kota (dropdown riwayat run)."""

    baris: list[AnomaliRunOut] = []


class AnomaliJenisOut(BaseModel):
    """Satu pilihan dropdown jenis anomali beserta jumlahnya."""

    kode: str
    label: str
    jumlah: int


class AnomaliBarisOut(BaseModel):
    """Satu titik yang menurut sistem masih bermasalah."""

    #: Id baris ``anomali_titik`` (dipakai aksi konfirmasi per baris).
    id: int | None = None
    jenis: str
    #: Kode kabupaten/kota asal baris (untuk filter banyak wilayah).
    kdkab: str | None = None
    assignment_id: str | None = None
    assignment_id_baru: str | None = None
    unique_bang: str | None = None
    level_6_full_code: str | None = None
    level_6_full_code_b: str | None = None
    wilayah: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    flag_unggah: int | None = None
    flag_model: int | None = None
    keterangan: str | None = None
    #: Kunci stabil temuan (``jenis|assignment_id|unique_bang``).
    kunci: str | None = None
    #: Konfirmasi kabupaten/kota untuk temuan ini, bila ada.
    konfirmasi: KonfirmasiAnomaliOut | None = None


class StatusKonfirmasiOut(BaseModel):
    """Satu status konfirmasi beserta jumlahnya (filter & ringkasan)."""

    kode: str
    label: str
    jumlah: int = 0


class RingkasanKonfirmasiOut(BaseModel):
    """Progres konfirmasi untuk filter aktif ("dikonfirmasi X dari Y")."""

    total: int = 0
    terkonfirmasi: int = 0
    belum: int = 0
    per_status: list[StatusKonfirmasiOut] = []


class KonfirmasiAnomaliOut(BaseModel):
    """Konfirmasi satu titik (dibaca dari ``konfirmasi_anomali``)."""

    status: str
    label: str
    catatan: str | None = None
    oleh: str | None = None
    peran: str | None = None
    pada: datetime | None = None
    kunci: str | None = None
    #: Admin provinsi meminta klarifikasi atas konfirmasi ini.
    perlu_klarifikasi: bool = False
    klarifikasi_catatan: str | None = None
    klarifikasi_oleh: str | None = None
    klarifikasi_pada: datetime | None = None


class AnomaliOut(BaseModel):
    """Isi halaman Anomali titik."""

    run: AnomaliRunOut | None = None
    #: Semua run B yang ikut dihitung (lebih dari satu bila memilih banyak
    #: kabupaten/kota).
    runs: list[AnomaliRunOut] = []
    jenis: list[AnomaliJenisOut]
    total: int
    baris: list[AnomaliBarisOut]
    #: Progres konfirmasi untuk filter jenis/pencarian aktif.
    ringkasan: RingkasanKonfirmasiOut = RingkasanKonfirmasiOut()
    #: Daftar status konfirmasi untuk dropdown filter.
    status_pilihan: list[StatusKonfirmasiOut] = []


class GeserRunOut(BaseModel):
    """Run Proses B pada halaman Pergeseran titik."""

    run_id: int
    tanggal_data: date
    pengunggah: str | None = None
    kdkab: str | None = None
    target: int = 0
    selesai: int = 0
    #: Banyak titik bergeser >= ambang simpan (10 m) pada run ini.
    jumlah_geser: int = 0


class DaftarGeserRunOut(BaseModel):
    """Riwayat run Proses B sukses satu kabupaten/kota (dropdown riwayat)."""

    baris: list[GeserRunOut] = []


class GeserBarisOut(BaseModel):
    """Satu titik yang bergeser dari titik asal (Master GS)."""

    id: int | None = None
    kdkab: str | None = None
    assignment_id: str | None = None
    unique_bang: str | None = None
    level_6_full_code: str | None = None
    level_6_full_code_b: str | None = None
    wilayah: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    #: Jarak geser (meter) dari titik asal, hasil hitung :mod:`app.geser`.
    jarak_geser_m: float | None = None
    flag_unggah: int | None = None
    flag_model: int | None = None
    keterangan: str | None = None


class GeserOut(BaseModel):
    """Isi halaman Pergeseran titik."""

    run: GeserRunOut | None = None
    runs: list[GeserRunOut] = []
    total: int
    #: Ambang meter yang sedang dipakai (filter tampilan).
    min_meter: float
    baris: list[GeserBarisOut]


class KonfirmasiMasuk(BaseModel):
    """Permintaan simpan/batal konfirmasi (satu atau banyak titik).

    Dua mode: ``anomali_ids`` (baris tertentu) atau filter (``semua=true``
    dengan ``kdprov``/``kdkab``/``jenis``/``q``/``run_b_id``/``status_filter``);
    server yang menentukan id pada mode filter supaya klien tidak bisa
    mengonfirmasi baris di luar filter.
    """

    status: str = ""
    catatan: str | None = Field(None, max_length=2000)
    #: Mode baris tertentu.
    anomali_ids: list[int] | None = None
    #: Mode filter (dipakai bila ``semua``).
    kdprov: str | None = None
    kdkab: list[str] | None = None
    jenis: list[str] | None = None
    q: str | None = Field(None, max_length=100)
    run_b_id: int | None = None
    status_filter: str | None = None
    semua: bool = False


class HasilKonfirmasiOut(BaseModel):
    """Hasil aksi konfirmasi/batal: jumlah baris yang terpengaruh."""

    jumlah: int


class KomunitasKomentarOut(BaseModel):
    """Satu balasan/solusi pada topik Komunitas."""

    id: int
    topik_id: int
    kdprov: str
    kdkab: str | None = None
    isi: str
    adalah_solusi: bool = False
    oleh: str
    username: str
    peran: str
    created_at: datetime


class KomunitasTopikOut(BaseModel):
    """Satu topik diskusi Komunitas (ringkasan maupun detail)."""

    id: int
    kdprov: str
    kdkab: str | None = None
    kategori: str
    judul: str
    error_txt: str | None = None
    deskripsi: str
    solusi_awal: str | None = None
    status: str
    solusi_komentar_id: int | None = None
    rule_target: str | None = None
    rule_catatan: str | None = None
    rule_oleh: str | None = None
    rule_pada: datetime | None = None
    jumlah_komentar: int = 0
    jumlah_dukungan: int = 1
    didukung_saya: bool = False
    oleh: str
    username: str
    peran: str
    created_at: datetime
    updated_at: datetime


class KomunitasTopikDetailOut(KomunitasTopikOut):
    """Detail satu topik Komunitas beserta daftar komentarnya."""

    komentar: list[KomunitasKomentarOut] = Field(default_factory=list)


class DaftarKomunitasTopikOut(BaseModel):
    """Daftar topik Komunitas beserta hitungan per status."""

    total: int
    terbuka: int = 0
    terpecahkan: int = 0
    jadi_rule: int = 0
    baris: list[KomunitasTopikOut] = Field(default_factory=list)


class KomunitasTopikMasuk(BaseModel):
    """Permintaan pembuatan topik masalah baru di Komunitas."""

    kategori: str = Field(..., max_length=24)
    judul: str = Field(..., min_length=5, max_length=200)
    error_txt: str | None = Field(None, max_length=15000)
    deskripsi: str = Field(..., min_length=5, max_length=8000)
    solusi_awal: str | None = Field(None, max_length=8000)


class KomunitasKomentarMasuk(BaseModel):
    """Permintaan tambah balasan/solusi pada topik Komunitas."""

    isi: str = Field(..., min_length=2, max_length=8000)
    tandai_sebagai_solusi: bool = False


class KomunitasRuleMasuk(BaseModel):
    """Permintaan Admin Provinsi untuk mengatur status & target rule baru."""

    status: str = Field(..., max_length=24)
    rule_target: str | None = Field(None, max_length=24)
    rule_catatan: str | None = Field(None, max_length=4000)


class RekonsiliasiBatasPasangBarisOut(BaseModel):
    """Satu baris pasangan kabupaten/kota bertetangga pada Rekonsiliasi Batas."""

    kdkab_a: str
    nmkab_a: str
    kdkab_b: str
    nmkab_b: str
    run_a_id: int | None = None
    run_b_id: int | None = None
    tanggal_a: date | None = None
    tanggal_b: date | None = None
    waktu_a: datetime | None = None
    waktu_b: datetime | None = None
    pengunggah_a: str | None = None
    pengunggah_b: str | None = None
    ada_peta_a: bool = False
    ada_peta_b: bool = False
    status: str
    jumlah_overlap: int = 0
    jumlah_gap: int = 0
    total_temuan: int = 0
    total_luas_overlap_m2: float = 0.0
    total_luas_gap_m2: float = 0.0
    ada_geojson: bool = False
    pesan: str | None = None
    updated_at: datetime | None = None


class RekonsiliasiBatasRingkasanOut(BaseModel):
    """Ringkasan seluruh pasangan perbatasan kabupaten/kota."""

    total_pasang: int
    clean: int = 0
    belum_clean: int = 0
    menunggu_tetangga: int = 0
    belum_unggah: int = 0
    total_overlap: int = 0
    total_gap: int = 0
    total_luas_overlap_m2: float = 0.0
    total_luas_gap_m2: float = 0.0
    baris: list[RekonsiliasiBatasPasangBarisOut] = Field(default_factory=list)


class RekonsiliasiBatasTemuanOut(BaseModel):
    """Satu rincian temuan Gap atau Overlap pada pasangan perbatasan."""

    id: int
    jenis: str
    tingkat: str
    idsls_a: str | None = None
    idsubsls_a: str | None = None
    nmsls_a: str | None = None
    idsls_b: str | None = None
    idsubsls_b: str | None = None
    nmsls_b: str | None = None
    luas_m2: float
    lat: float
    lon: float
    catatan: str | None = None


class RekonsiliasiBatasDetailOut(RekonsiliasiBatasPasangBarisOut):
    """Detail satu pasangan perbatasan beserta daftar temuan Gap & Overlap."""

    temuan: list[RekonsiliasiBatasTemuanOut] = Field(default_factory=list)
