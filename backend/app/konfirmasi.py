"""Konfirmasi pencermatan titik anomali.

Anomali tidak wajib habis; setiap temuan cukup **dijelaskan** kabupaten/kota.
Modul ini menyimpan penjelasan itu di tabel ``konfirmasi_anomali`` dengan kunci
yang stabil antar run (``jenis | assignment_id | unique_bang``), sehingga
penjelasan yang sudah dibuat tetap berlaku saat run B berikutnya memunculkan
temuan yang sama.

Dua status saja:

``akan_diperbaiki``
    Kabupaten/kota mengakui temuan dan akan memperbaikinya. Catatan opsional.
``sesuai_kenyataan``
    Temuan dianggap sesuai kondisi lapangan. Wajib disertai catatan
    (lihat :data:`CATATAN_WAJIB`).

Modul ini **tidak** mengubah rekap progres: rekap tetap memakai klaim kabupaten
(``titik_hasil.flag_repair_unggah``). Konfirmasi hanya lapisan tampilan/audit di
menu pencermatan.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app import auth
from app.models import (
    KONFIRMASI_AKAN_DIPERBAIKI,
    KONFIRMASI_SESUAI_KENYATAAN,
    AnomaliTitik,
    KonfirmasiAnomali,
    Run,
    sekarang,
)

logger = logging.getLogger("pointse.konfirmasi")

AKAN_DIPERBAIKI = KONFIRMASI_AKAN_DIPERBAIKI
SESUAI_KENYATAAN = KONFIRMASI_SESUAI_KENYATAAN

#: Pilihan status konfirmasi beserta labelnya.
STATUS: tuple[tuple[str, str], ...] = (
    (AKAN_DIPERBAIKI, "Akan Diperbaiki"),
    (SESUAI_KENYATAAN, "Sesuai Kondisi Kenyataan"),
)
LABEL = dict(STATUS)

#: Nilai filter "belum dikonfirmasi" (bukan nilai kolom; hanya untuk tampilan).
BELUM = "belum"
LABEL[BELUM] = "Belum dikonfirmasi"

#: Nilai filter "sudah dikonfirmasi" (gabungan kedua status; bukan nilai kolom).
SUDAH = "sudah"
LABEL[SUDAH] = "Sudah dikonfirmasi"

#: Status yang wajib disertai catatan.
CATATAN_WAJIB: tuple[str, ...] = (SESUAI_KENYATAAN,)


def kunci(
    jenis: str | None, assignment_id: str | None, unique_bang: str | None
) -> str:
    """Kunci stabil satu temuan: ``jenis | assignment_id | unique_bang``.

    Bagian kosong ditulis ``''`` supaya MySQL tidak membandingkan ``NULL``
    (yang membuat UNIQUE tidak berlaku).
    """
    return f"{jenis or ''}|{assignment_id or ''}|{unique_bang or ''}"


def syarat_cocok() -> Any:
    """Syarat join ``konfirmasi_anomali`` ke ``anomali_titik`` (+ ``runs``).

    Dicocokkan lewat kolom asalnya (bukan lewat ``kunci``) supaya querynya
    portabel (MySQL & SQLite tes). Karena ``kunci`` dibangun dari kolom yang
    sama, satu baris anomali cocok paling banyak dengan satu konfirmasi.
    """
    return and_(
        KonfirmasiAnomali.kdkab == Run.kdkab,
        KonfirmasiAnomali.jenis == AnomaliTitik.jenis,
        func.coalesce(KonfirmasiAnomali.assignment_id, "")
        == func.coalesce(AnomaliTitik.assignment_id, ""),
        func.coalesce(KonfirmasiAnomali.unique_bang, "")
        == func.coalesce(AnomaliTitik.unique_bang, ""),
    )


def baris_ke_keluaran(satu: KonfirmasiAnomali) -> dict[str, Any]:
    """Bentuk ringkas konfirmasi untuk API (label ikut dihitung)."""
    return {
        "status": satu.status,
        "label": LABEL.get(satu.status, satu.status),
        "catatan": satu.catatan,
        "oleh": satu.nama,
        "peran": satu.peran,
        "pada": satu.updated_at,
        "kunci": satu.kunci,
        "perlu_klarifikasi": bool(satu.perlu_klarifikasi),
        "klarifikasi_catatan": satu.klarifikasi_catatan,
        "klarifikasi_oleh": satu.klarifikasi_oleh,
        "klarifikasi_pada": satu.klarifikasi_pada,
    }


def simpan(
    sesi: Session,
    pengguna: auth.Pengguna,
    *,
    baris: Sequence[tuple[AnomaliTitik, str, str]],
    status: str,
    catatan: str | None,
) -> int:
    """Upsert konfirmasi untuk baris terpilih; kembalikan jumlah baris.

    ``baris`` adalah daftar ``(anomali_titik, kdkab, kdprov)``. Pengelompokan
    per kabupaten/kota membuat pemuatan konfirmasi lama tetap satu query per
    kabupaten (tabelnya kecil: hanya temuan yang sudah dijelaskan).
    """
    waktu = sekarang()
    per_kab: dict[str, list[tuple[AnomaliTitik, str]]] = defaultdict(list)
    for satu, kdkab, kdprov in baris:
        per_kab[kdkab].append((satu, kdprov))

    jumlah = 0
    for kdkab, isi in per_kab.items():
        ada = {
            satu.kunci: satu
            for satu in sesi.scalars(
                select(KonfirmasiAnomali).where(KonfirmasiAnomali.kdkab == kdkab)
            )
        }
        for satu, kdprov in isi:
            kode = kunci(satu.jenis, satu.assignment_id, satu.unique_bang)
            target = ada.get(kode)
            if target is None:
                target = KonfirmasiAnomali(
                    kdprov=kdprov,
                    kdkab=kdkab,
                    kunci=kode,
                    jenis=satu.jenis,
                    assignment_id=satu.assignment_id,
                    unique_bang=satu.unique_bang,
                    level_6_full_code=satu.level_6_full_code,
                    created_at=waktu,
                )
                sesi.add(target)
                ada[kode] = target
            target.status = status
            target.catatan = catatan
            target.run_b_id = satu.run_b_id
            target.level_6_full_code = satu.level_6_full_code
            # Konfirmasi ulang = jawaban kabupaten atas permintaan klarifikasi.
            target.perlu_klarifikasi = 0
            target.klarifikasi_catatan = None
            target.klarifikasi_oleh = None
            target.klarifikasi_pada = None
            target.sub = pengguna.sub
            target.username = pengguna.username
            target.nama = pengguna.nama
            target.nip = pengguna.nip
            target.peran = pengguna.peran.nama
            target.updated_at = waktu
            jumlah += 1

    sesi.commit()
    return jumlah


def hapus(
    sesi: Session,
    *,
    baris: Sequence[tuple[AnomaliTitik, str, str]],
) -> int:
    """Hapus konfirmasi baris terpilih (kembali "Belum dikonfirmasi")."""
    per_kab: dict[str, set[str]] = defaultdict(set)
    for satu, kdkab, _kdprov in baris:
        per_kab[kdkab].add(kunci(satu.jenis, satu.assignment_id, satu.unique_bang))

    jumlah = 0
    for kdkab, kuncis in per_kab.items():
        for satu in sesi.scalars(
            select(KonfirmasiAnomali).where(KonfirmasiAnomali.kdkab == kdkab)
        ):
            if satu.kunci in kuncis:
                sesi.delete(satu)
                jumlah += 1
    sesi.commit()
    return jumlah


def minta_klarifikasi(
    sesi: Session,
    pengguna: auth.Pengguna,
    *,
    baris: Sequence[tuple[AnomaliTitik, str, str]],
    catatan: str,
) -> int:
    """Tandai konfirmasi terpilih perlu klarifikasi (status tidak diubah).

    Hanya baris yang sudah dikonfirmasi yang bisa dimintai klarifikasi; baris
    yang belum dikonfirmasi memang sudah terlihat sebagai pekerjaan kabupaten.
    Konfirmasi ulang oleh kabupaten/kota menghapus tanda ini (lihat :func:`simpan`).
    """
    waktu = sekarang()
    per_kab: dict[str, set[str]] = defaultdict(set)
    for satu, kdkab, _kdprov in baris:
        per_kab[kdkab].add(kunci(satu.jenis, satu.assignment_id, satu.unique_bang))

    jumlah = 0
    for kdkab, kuncis in per_kab.items():
        for satu in sesi.scalars(
            select(KonfirmasiAnomali).where(KonfirmasiAnomali.kdkab == kdkab)
        ):
            if satu.kunci in kuncis:
                satu.perlu_klarifikasi = 1
                satu.klarifikasi_catatan = catatan
                satu.klarifikasi_oleh = pengguna.nama
                satu.klarifikasi_pada = waktu
                jumlah += 1
    sesi.commit()
    return jumlah
