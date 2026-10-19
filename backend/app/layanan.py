"""Layanan unggah berkas dan query laporan (dipakai API dan tes).

Semua fungsi di sini sinkron (``def``), tanpa akses jaringan: FastAPI
menjalankannya di threadpool, jadi event loop tidak terblokir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

import pyogrio
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    STATUS_MENUNGGU,
    TIPE_A,
    TIPE_B,
    Run,
    TitikHasil,
)
from app.proses_a import KOLOM_PETA, KOLOM_TITIK
from app.proses_b import KOLOM_TITIK_B

# Kolom wajib tiap berkas masukan, per tipe proses.
KOLOM_WAJIB: dict[str, dict[str, Sequence[str]]] = {
    TIPE_A: {"titik": KOLOM_TITIK, "peta": KOLOM_PETA},
    TIPE_B: {"titik": KOLOM_TITIK_B, "peta": KOLOM_PETA},
}

# Tingkat rekap progres (PRD §5): kolom kode + kolom nama.
TINGKAT: dict[str, tuple[str, str]] = {
    "kabupaten": ("kdkab", "nmkab"),
    "kecamatan": ("kdkec", "nmkec"),
    "desa": ("kddesa", "nmdesa"),
    "sls": ("idsubsls_origin", "nmsls"),
}

Tingkat = Literal["kabupaten", "kecamatan", "desa", "sls"]

UKURAN_POTONGAN = 1024 * 1024  # 1 MB per potong saat menyimpan unggahan


class KesalahanUnggahan(ValueError):
    """Berkas unggahan tidak bisa dipakai; pesannya untuk pengguna."""


@dataclass(frozen=True)
class InfoUnggahan:
    """Hasil pemeriksaan berkas unggahan sebelum baris ``runs`` dibuat."""

    kdkab: str
    layer_input: str | None
    layer_peta: str | None


def simpan_berkas(sumber: BinaryIO, tujuan: Path) -> int:
    """Tulis berkas unggahan ke disk per potong (hemat memori); kembalikan ukurannya."""
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    ukuran = 0
    with tujuan.open("wb") as keluar:
        while potongan := sumber.read(UKURAN_POTONGAN):
            keluar.write(potongan)
            ukuran += len(potongan)
    return ukuran


def pilih_layer(
    berkas: Path, kolom_wajib: Sequence[str], layer: str | None, peran: str
) -> str | None:
    """Cari layer yang punya semua ``kolom_wajib`` (hanya baca metadata berkas).

    Kalau ``layer`` diisi, layer itulah yang dipakai (dan diperiksa kolomnya).
    """
    try:
        daftar = [str(nama) for nama in pyogrio.list_layers(berkas)[:, 0]]
    except Exception as galat:  # noqa: BLE001 - pesan apa pun diteruskan ke pengguna
        raise KesalahanUnggahan(f"berkas {peran} tidak bisa dibaca: {galat}") from galat

    if not daftar:
        raise KesalahanUnggahan(f"berkas {peran} tidak punya layer apa pun")
    if layer is not None and layer not in daftar:
        raise KesalahanUnggahan(
            f"layer '{layer}' tidak ada di berkas {peran}; pilihan: {', '.join(daftar)}"
        )

    for nama in [layer] if layer is not None else daftar:
        kolom = {str(k) for k in pyogrio.read_info(berkas, layer=nama)["fields"]}
        if set(kolom_wajib) <= kolom:
            return nama

    kurang = ", ".join(sorted(set(kolom_wajib)))
    raise KesalahanUnggahan(
        f"layer berkas {peran} tidak punya kolom wajib ({kurang}); "
        f"layer tersedia: {', '.join(daftar)}"
    )


def periksa_peta(berkas: Path, layer: str | None) -> tuple[str | None, str]:
    """Periksa peta dan ambil kdkab-nya; peta harus satu kabupaten/kota.

    Satu job hanya untuk satu kabupaten/kota (PRD §8, aturan "satu job aktif per
    kabupaten/tipe"), jadi nilai ``kdkab`` di peta harus tunggal.
    """
    nama_layer = pilih_layer(berkas, KOLOM_PETA, layer, "peta")
    data = pyogrio.read_dataframe(
        berkas, layer=nama_layer, columns=["kdkab"], read_geometry=False
    )
    kdkab = sorted({str(nilai).strip() for nilai in data["kdkab"].dropna() if str(nilai).strip()})

    if not kdkab:
        raise KesalahanUnggahan("kolom kdkab di berkas peta kosong")
    if len(kdkab) > 1:
        contoh = ", ".join(kdkab[:5])
        raise KesalahanUnggahan(
            f"berkas peta memuat {len(kdkab)} kabupaten/kota ({contoh}, ...); "
            "satu job hanya untuk satu kabupaten/kota"
        )
    return nama_layer, kdkab[0]


def periksa_unggahan(
    tipe: str,
    berkas_input: Path,
    berkas_peta: Path,
    layer_input: str | None,
    layer_peta: str | None,
) -> InfoUnggahan:
    """Periksa kedua berkas unggahan; kembalikan kdkab + layer yang dipakai."""
    if tipe not in KOLOM_WAJIB:
        raise KesalahanUnggahan(f"tipe harus {TIPE_A} atau {TIPE_B}, bukan '{tipe}'")

    kolom = KOLOM_WAJIB[tipe]
    nama_input = pilih_layer(berkas_input, kolom["titik"], layer_input, "titik")
    nama_peta, kdkab = periksa_peta(berkas_peta, layer_peta)
    return InfoUnggahan(kdkab=kdkab, layer_input=nama_input, layer_peta=nama_peta)


def buat_run(
    sesi: Session,
    *,
    tipe: str,
    info: InfoUnggahan,
    user: str | None,
    nama_input: str,
    nama_peta: str,
    berkas_input: Path,
    berkas_peta: Path,
) -> Run:
    """Buat baris ``runs`` berstatus ``menunggu`` (siap diambil worker)."""
    run = Run(
        tipe=tipe,
        kdkab=info.kdkab,
        user=user,
        status=STATUS_MENUNGGU,
        nama_file_input=nama_input,
        nama_file_peta=nama_peta,
        berkas_input=str(berkas_input),
        berkas_peta=str(berkas_peta),
        layer_input=info.layer_input,
        layer_peta=info.layer_peta,
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)
    return run


def ambil_run(sesi: Session, run_id: int) -> Run | None:
    """Ambil satu job berdasarkan id."""
    return sesi.get(Run, run_id)


def jumlah_tersimpan(sesi: Session, run_id: int) -> int:
    """Jumlah baris hasil yang tersimpan untuk satu job."""
    return int(
        sesi.scalar(
            select(func.count()).select_from(TitikHasil).where(TitikHasil.run_id == run_id)
        )
        or 0
    )


def daftar_run(
    sesi: Session,
    *,
    tipe: str | None = None,
    status: str | None = None,
    kdkab: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Run]]:
    """Daftar job terbaru lebih dulu, dengan penyaring opsional (paging)."""
    saring = []
    if tipe is not None:
        saring.append(Run.tipe == tipe)
    if status is not None:
        saring.append(Run.status == status)
    if kdkab is not None:
        saring.append(Run.kdkab == kdkab)

    total = int(sesi.scalar(select(func.count()).select_from(Run).where(*saring)) or 0)
    baris = list(
        sesi.scalars(
            select(Run).where(*saring).order_by(Run.id.desc()).limit(limit).offset(offset)
        )
    )
    return total, baris


def hasil_run(
    sesi: Session, run_id: int, *, limit: int = 100, offset: int = 0
) -> tuple[int, list[dict[str, object]]]:
    """Sebagian baris hasil (paging), urut seperti keluaran Proses A/B."""
    kolom = [kol for kol in TitikHasil.__table__.columns if kol.name != "id"]
    total = int(
        sesi.scalar(
            select(func.count()).select_from(TitikHasil).where(TitikHasil.run_id == run_id)
        )
        or 0
    )
    baris = sesi.execute(
        select(*kolom)
        .where(TitikHasil.run_id == run_id)
        .order_by(TitikHasil.id)
        .limit(limit)
        .offset(offset)
    ).mappings()
    return total, [dict(b) for b in baris]


def _kasus(syarat: object) -> object:
    """``CASE WHEN syarat THEN 1 ELSE 0 END`` portabel (MySQL & SQLite)."""
    return case((syarat, 1), else_=0)


def _persen(belum: object, jumlah: object) -> object:
    """Persentase titik belum diperbaiki, dihitung di basis data."""
    return func.round(100.0 * belum / func.nullif(jumlah, 0), 2)


def rekap_run(sesi: Session, run_id: int, tingkat: Tingkat) -> dict[str, object]:
    """Rekap progres per wilayah: hitungan dan persentase ``flag_repair``.

    Dihitung lewat query (GROUP BY) di basis data, bukan di Python (PRD §7).
    """
    kolom_kode, kolom_nama = (getattr(TitikHasil, nama) for nama in TINGKAT[tingkat])

    belum = func.coalesce(func.sum(_kasus(TitikHasil.flag_repair == 1)), 0)
    sudah = func.coalesce(func.sum(_kasus(TitikHasil.flag_repair == 0)), 0)
    jumlah = func.count()

    per_kelompok = sesi.execute(
        select(
            kolom_kode.label("kode"),
            kolom_nama.label("nama"),
            jumlah.label("jumlah"),
            sudah.label("sudah"),
            belum.label("belum"),
            _persen(belum, jumlah).label("persen_belum"),
        )
        .where(TitikHasil.run_id == run_id)
        .group_by(kolom_kode, kolom_nama)
        .order_by(kolom_kode)
    ).mappings()

    baris = [
        {
            "kode": None if hasil["kode"] is None else str(hasil["kode"]),
            "nama": None if hasil["nama"] is None else str(hasil["nama"]),
            "jumlah": int(hasil["jumlah"]),
            "sudah": int(hasil["sudah"]),
            "belum": int(hasil["belum"]),
            "persen_belum": float(hasil["persen_belum"] or 0.0),
        }
        for hasil in per_kelompok
    ]
    for satu in baris:
        if satu["nama"] is None:
            satu["nama"] = "(titik tidak masuk wilayah)"

    total = sum(satu["jumlah"] for satu in baris)
    sudah_total = sum(satu["sudah"] for satu in baris)
    belum_total = sum(satu["belum"] for satu in baris)
    return {
        "run_id": run_id,
        "tingkat": tingkat,
        "total": total,
        "sudah": sudah_total,
        "belum": belum_total,
        "persen_belum": round(100.0 * belum_total / total, 2) if total else 0.0,
        "baris": baris,
    }
