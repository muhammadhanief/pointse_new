"""Skema balasan (Pydantic) untuk API pointse.

Dipisah dari model ORM supaya bentuk JSON API tidak ikut berubah saat kolom DB
berubah.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunOut(BaseModel):
    """Ringkasan satu job (baris tabel ``runs``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tipe: str
    kdkab: str
    user: str | None = None
    status: str
    nama_file_input: str
    nama_file_peta: str
    layer_input: str | None = None
    layer_peta: str | None = None
    jumlah_baris: int | None = None
    jumlah_tanpa_wilayah: int | None = None
    pesan: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunDetailOut(RunOut):
    """Ringkasan job + jumlah baris hasil yang sudah tersimpan."""

    jumlah_tersimpan: int


class DaftarRunOut(BaseModel):
    """Balasan daftar job dengan paging."""

    total: int
    baris: list[RunOut]


class HasilOut(BaseModel):
    """Balasan hasil titik (paging)."""

    run_id: int
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
    """Rekap progres satu job, dikelompokkan per tingkat wilayah."""

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
