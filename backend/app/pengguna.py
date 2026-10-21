"""Kehadiran pengguna dan pemantauan admin provinsi.

Shell dashboard mengirim heartbeat berkala ke ``POST /kehadiran``. Baris disimpan
satu per ``sub`` SSO; data ini **bukan** sumber otorisasi, hanya untuk halaman
pemantauan admin. Admin provinsi hanya melihat pengguna di provinsinya.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import aktivitas, auth
from app.db import get_session
from app.models import (
    PENGGUNA_LOGIN_BARU_MENIT,
    PENGGUNA_ONLINE_DETIK,
    PenggunaAktif,
    sekarang,
)
from app.peran import PERAN_ADMIN_PROVINSI
from app.skema import DaftarPenggunaAktifOut, PenggunaAktifOut

router = APIRouter()


def _terapkan_identitas(
    baris: PenggunaAktif,
    pengguna: auth.Pengguna,
) -> None:
    """Perbarui identitas dari token; foto lama dipertahankan bila token kosong."""
    baris.username = pengguna.username
    baris.nama = pengguna.nama
    baris.nip = pengguna.nip
    baris.email = pengguna.email
    baris.org = pengguna.org
    baris.peran = pengguna.peran.nama
    baris.kdprov = pengguna.kdprov
    baris.kdkab = pengguna.kdkab
    if pengguna.foto_url:
        baris.foto_url = pengguna.foto_url


@router.post("/kehadiran")
def catat_kehadiran(
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> dict[str, str]:
    """Catat/segarkan kehadiran pengguna yang sedang membuka dashboard."""
    waktu = sekarang()
    baris = sesi.get(PenggunaAktif, pengguna.sub)
    baru = baris is None
    login_baru = False

    if baris is None:
        baris = PenggunaAktif(
            sub=pengguna.sub,
            username=pengguna.username,
            nama=pengguna.nama,
            nip=pengguna.nip,
            email=pengguna.email,
            org=pengguna.org,
            peran=pengguna.peran.nama,
            kdprov=pengguna.kdprov,
            kdkab=pengguna.kdkab,
            foto_url=pengguna.foto_url,
            login_pada=waktu,
            terakhir_aktif=waktu,
        )
        sesi.add(baris)
    else:
        jeda = (waktu - baris.terakhir_aktif).total_seconds()
        login_baru = jeda >= PENGGUNA_LOGIN_BARU_MENIT * 60
        if login_baru:
            baris.login_pada = waktu
        _terapkan_identitas(baris, pengguna)
        baris.terakhir_aktif = waktu

    sesi.commit()
    if baru or login_baru:
        aktivitas.catat(
            sesi,
            pengguna,
            aksi="login",
            objek="sesi",
            detail=f"Masuk sebagai {pengguna.peran.nama}",
        )
    return {"status": "ok"}


@router.get("/pengguna", response_model=DaftarPenggunaAktifOut)
def daftar_pengguna(
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> DaftarPenggunaAktifOut:
    """Daftar pengguna di provinsi admin, terbaru aktif lebih dulu."""
    auth.pastikan_peran(pengguna, PERAN_ADMIN_PROVINSI)
    kdprov, _ = auth.saring_akses(pengguna, None, None)

    perintah = select(PenggunaAktif)
    if kdprov is not None:
        perintah = perintah.where(PenggunaAktif.kdprov == kdprov)
    perintah = perintah.order_by(PenggunaAktif.terakhir_aktif.desc()).limit(500)

    waktu = sekarang()
    daftar: list[PenggunaAktifOut] = []
    for baris in sesi.scalars(perintah):
        item = PenggunaAktifOut.model_validate(baris)
        item.online = (
            waktu - baris.terakhir_aktif
        ).total_seconds() <= PENGGUNA_ONLINE_DETIK
        daftar.append(item)

    return DaftarPenggunaAktifOut(
        total=len(daftar),
        online=sum(1 for item in daftar if item.online),
        baris=daftar,
    )
