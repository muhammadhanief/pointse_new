"""Skema balasan (Pydantic) untuk API pointse.

Dipisah dari model ORM supaya bentuk JSON API tidak ikut berubah saat kolom DB
berubah.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunOut(BaseModel):
    """Ringkasan satu job (baris tabel ``runs``).

    ``detail_tersedia`` = 1 kalau baris ``titik_hasil`` run ini masih disimpan
    (run baseline dan run sukses terakhir per kabupaten/tipe).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
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


class RunDetailOut(RunOut):
    """Ringkasan job + jumlah baris hasil yang sudah tersimpan."""

    jumlah_tersimpan: int


class DaftarRunOut(BaseModel):
    """Balasan daftar job dengan paging."""

    total: int
    baris: list[RunOut]


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
