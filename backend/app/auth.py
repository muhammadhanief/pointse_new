"""Autentikasi token sesi dari frontend dan otorisasi per wilayah.

Alur SSO BPS dijalankan di frontend (OIDC Authorization Code + PKCE). Setelah
callback, frontend menyimpan sesi sebagai JWT HS256 di cookie httpOnly dan
meneruskannya ke backend sebagai ``Authorization: Bearer <token>``. Backend hanya
memverifikasi tanda tangan token itu; token tidak pernah dibuat di browser.

``org`` dari SSO dipetakan ke peran oleh :func:`app.peran.peran_dari_org`:

- admin provinsi: boleh unggah geotag master dan melihat seluruh kabupaten/kota
  di provinsinya;
- petugas kabupaten/kota: boleh menjalankan Proses A/B dan melihat datanya sendiri.

``AUTH_REQUIRED=false`` hanya untuk tes/mode lokal: semua permintaan dianggap
pengguna pengembang yang boleh mengakses semua wilayah.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.peran import PERAN_ADMIN_PROVINSI, Peran, peran_dari_org

#: Peran khusus saat ``AUTH_REQUIRED=false`` (tes/mode lokal).
PERAN_DEV = "dev"


class AksesDitolak(HTTPException):
    """Pengguna terautentikasi tetapi tidak berhak atas aksi/wilayah tersebut."""

    def __init__(self, detail: str = "tidak berhak mengakses wilayah ini") -> None:
        super().__init__(status_code=403, detail=detail)


@dataclass(frozen=True)
class Pengguna:
    """Identitas pengguna dari token sesi frontend."""

    sub: str
    username: str
    nama: str
    org: str
    peran: Peran
    nip: str | None = None
    email: str | None = None

    @property
    def kdprov(self) -> str:
        return self.peran.kdprov

    @property
    def kdkab(self) -> str | None:
        return self.peran.kdkab


def _pengguna_dev() -> Pengguna:
    """Pengguna longgar untuk tes/mode lokal tanpa SSO."""
    return Pengguna(
        sub="dev",
        username="dev",
        nama="Pengguna Lokal",
        org="*",
        peran=Peran(nama=PERAN_DEV, kdprov="*", kdkab=None),
    )


def _ambil_bearer(header: str | None) -> str | None:
    """Ambil token dari header ``Authorization: Bearer ...``."""
    if not header:
        return None
    skema, _, token = header.partition(" ")
    if skema.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def pengguna_saat_ini(
    request: Request,
    setelan: Settings = Depends(get_settings),
) -> Pengguna:
    """Dependency FastAPI: verifikasi token sesi dan kembalikan identitas pengguna."""
    if not setelan.auth_required:
        return _pengguna_dev()

    if not setelan.auth_secret:
        raise HTTPException(
            status_code=503,
            detail="autentikasi backend belum dikonfigurasi (AUTH_SECRET kosong)",
        )

    token = _ambil_bearer(request.headers.get("authorization"))
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="token sesi tidak ditemukan",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        klaim = jwt.decode(
            token,
            setelan.auth_secret,
            algorithms=["HS256"],
            audience=setelan.auth_audience,
            issuer=setelan.auth_issuer,
            options={"require": ["exp", "iat", "sub", "org"]},
        )
    except jwt.InvalidTokenError as galat:
        raise HTTPException(
            status_code=401,
            detail="token sesi tidak valid atau sudah kedaluwarsa",
            headers={"WWW-Authenticate": "Bearer"},
        ) from galat

    org = klaim.get("org")
    if not isinstance(org, str):
        raise HTTPException(status_code=401, detail="token sesi tidak memuat org")
    try:
        peran = peran_dari_org(org)
    except ValueError as galat:
        raise AksesDitolak(str(galat)) from galat

    username = str(klaim.get("username") or klaim.get("sub") or "")
    nama = str(klaim.get("nama") or username)
    sub = str(klaim.get("sub") or username)
    return Pengguna(
        sub=sub,
        username=username,
        nama=nama,
        org=org,
        peran=peran,
        nip=_teks_atau_none(klaim.get("nip")),
        email=_teks_atau_none(klaim.get("email")),
    )


def _teks_atau_none(nilai: object) -> str | None:
    """Ubah klaim opsional menjadi teks; ``None`` bila kosong."""
    if nilai is None:
        return None
    teks = str(nilai).strip()
    return teks or None


def _kode_kabupaten(kdprov: str, kdkab: str) -> str:
    """Normalisasi kode kabupaten/kota dari bentuk pendek peta (``07``)."""
    kab = str(kdkab).strip()
    if len(kab) == 2:
        return f"{kdprov[:2]}{kab}"
    return kab


def saring_akses(
    pengguna: Pengguna,
    kdprov: str | None,
    kdkab: str | None,
) -> tuple[str | None, str | None]:
    """Batasi filter wilayah sesuai peran; kembalikan filter efektif.

    Nilai ``None`` berarti permintaan tidak menyebut wilayah. Untuk petugas
    kabupaten/kota, hasilnya selalu wilayah miliknya. Untuk admin provinsi,
    hasilnya selalu provinsinya (dengan kabupaten/kota bila disebut).

    Raises:
        AksesDitolak: pengguna meminta wilayah di luar kewenangannya.
    """
    if pengguna.peran.nama == PERAN_DEV:
        return kdprov, kdkab

    prov = str(kdprov).strip() if kdprov is not None else None
    kab = str(kdkab).strip() if kdkab is not None else None
    prov = prov or None
    kab = kab or None
    provinsi_pengguna = pengguna.peran.kdprov

    if prov is not None and prov != provinsi_pengguna:
        raise AksesDitolak(
            f"tidak berhak mengakses provinsi {prov}; kewenangan Anda {provinsi_pengguna}"
        )

    if pengguna.peran.nama == PERAN_ADMIN_PROVINSI:
        if kab is None:
            return provinsi_pengguna, None
        kode = _kode_kabupaten(provinsi_pengguna, kab)
        if len(kode) != 4 or not kode.isdigit() or not kode.startswith(provinsi_pengguna):
            raise AksesDitolak(f"kode kabupaten/kota '{kdkab}' tidak valid")
        return provinsi_pengguna, kode

    # Petugas kabupaten/kota.
    kewenangan = pengguna.peran.kdkab
    if kab is None:
        return provinsi_pengguna, kewenangan
    kode = _kode_kabupaten(provinsi_pengguna, kab)
    if kode != kewenangan:
        raise AksesDitolak(
            f"tidak berhak mengakses kabupaten/kota {kode}; kewenangan Anda {kewenangan}"
        )
    return provinsi_pengguna, kewenangan


def pastikan_akses(pengguna: Pengguna, kdprov: str | None, kdkab: str | None) -> None:
    """Pastikan pengguna berhak atas wilayah tersebut (tanpa memakai hasil filter)."""
    saring_akses(pengguna, kdprov, kdkab)


def pastikan_peran(pengguna: Pengguna, peran: str) -> None:
    """Pastikan pengguna memiliki peran tertentu (pengguna dev selalu lolos)."""
    if pengguna.peran.nama == PERAN_DEV:
        return
    if pengguna.peran.nama != peran:
        raise AksesDitolak(f"aksi ini hanya untuk peran {peran}")
