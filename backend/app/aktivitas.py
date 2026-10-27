"""Jejak audit aktivitas pengguna.

Pencatatan dilakukan setelah tindakan berhasil, dan juga saat berkas unggahan
ditolak validasi (aksi ``unggah_ditolak``) supaya kegagalan tetap terlihat di
log aktivitas. Kegagalan menulis audit tidak boleh membatalkan tindakan utama
yang sudah tersimpan, jadi helper ini menangani rollback sendiri dan hanya
menulis log server.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_session
from app.models import Aktivitas
from app.peran import PERAN_ADMIN_PROVINSI
from app.skema import AktivitasOut, DaftarAktivitasOut

logger = logging.getLogger("pointse.aktivitas")
router = APIRouter()


def catat(
    sesi: Session,
    pengguna: auth.Pengguna,
    *,
    aksi: str,
    objek: str,
    objek_id: int | None = None,
    detail: str | None = None,
) -> Aktivitas | None:
    """Catat satu aktivitas; jangan gagalkan request utama bila audit gagal."""
    baris = Aktivitas(
        sub=pengguna.sub,
        username=pengguna.username,
        nama=pengguna.nama,
        nip=pengguna.nip,
        peran=pengguna.peran.nama,
        kdprov=pengguna.kdprov,
        kdkab=pengguna.kdkab,
        foto_url=pengguna.foto_url,
        aksi=aksi,
        objek=objek,
        objek_id=objek_id,
        detail=detail,
    )
    try:
        sesi.add(baris)
        sesi.commit()
        return baris
    except Exception:
        sesi.rollback()
        logger.exception("Gagal mencatat aktivitas %s %s", aksi, objek)
        return None


@router.get("/aktivitas", response_model=DaftarAktivitasOut)
def daftar_aktivitas(
    limit: int = Query(200, ge=1, le=500),
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> DaftarAktivitasOut:
    """Daftar aktivitas terbaru di provinsi admin."""
    auth.pastikan_peran(pengguna, PERAN_ADMIN_PROVINSI)
    kdprov, _ = auth.saring_akses(pengguna, None, None)

    perintah = select(Aktivitas)
    if kdprov is not None:
        perintah = perintah.where(Aktivitas.kdprov == kdprov)
    perintah = perintah.order_by(Aktivitas.created_at.desc()).limit(limit)

    baris = [
        AktivitasOut.model_validate(satu)
        for satu in sesi.scalars(perintah)
    ]
    return DaftarAktivitasOut(total=len(baris), baris=baris)
