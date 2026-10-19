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
    """Rekap progres satu wilayah."""

    kode: str | None = None
    nama: str | None = None
    jumlah: int
    sudah: int
    belum: int
    persen_belum: float


class RekapOut(BaseModel):
    """Rekap progres satu job, dikelompokkan per tingkat wilayah."""

    run_id: int
    tingkat: str
    dasar: str
    total: int
    sudah: int
    belum: int
    persen_belum: float
    baris: list[RekapBarisOut]
