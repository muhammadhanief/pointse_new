"""Autentikasi token Bearer dan otorisasi per wilayah.

Token sesi dibuat oleh alur login frontend dan dikirim backend sebagai
``Authorization: Bearer <token>``. Backend tidak membaca cookie dan tidak
membuat token sendiri; token diverifikasi dengan kunci HS256 dari
``AUTH_SECRET``.

``org`` dari SSO dipetakan ke peran oleh :func:`app.peran.peran_dari_org`:

- admin provinsi: boleh unggah geotag master dan melihat seluruh kabupaten/kota
  di provinsinya;
- petugas kabupaten/kota: boleh menjalankan Proses A/B dan melihat datanya sendiri.

``AUTH_MODE=dev`` hanya untuk tes/mode lokal: semua permintaan dianggap pengguna
pengembang yang boleh mengakses semua wilayah. Mode ini ditolak saat
``ENV=production``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.peran import PERAN_ADMIN_PROVINSI, Peran, peran_dari_org

#: Peran khusus saat ``AUTH_MODE=dev`` (tes/mode lokal).
PERAN_DEV = "dev"
#: Masa berlaku tiket unduh singkat (detik).
MASA_BERLAKU_TIKET_UNDUH_DETIK = 60


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
    foto_url: str | None = None

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


def buat_tiket_unduh(
    pengguna: Pengguna,
    setelan: Settings,
    masa_berlaku_detik: int = MASA_BERLAKU_TIKET_UNDUH_DETIK,
) -> str:
    """Buat tiket JWT singkat khusus unduhan langsung browser (query ``?tiket=``)."""
    rahasia = setelan.auth_secret.strip()
    if setelan.auth_mode == "dev" or not rahasia:
        return "dev"
    sekarang = int(time.time())
    muatan: dict[str, object] = {
        "sub": pengguna.sub,
        "username": pengguna.username,
        "nama": pengguna.nama,
        "org": pengguna.org,
        "tujuan": "unduh",
        "iat": sekarang,
        "exp": sekarang + max(10, int(masa_berlaku_detik)),
        "aud": setelan.auth_audience,
        "iss": setelan.auth_issuer,
    }
    if pengguna.nip:
        muatan["nip"] = pengguna.nip
    if pengguna.email:
        muatan["email"] = pengguna.email
    return str(jwt.encode(muatan, rahasia, algorithm="HS256"))


def pengguna_saat_ini(
    request: Request,
    setelan: Settings = Depends(get_settings),
) -> Pengguna:
    """Dependency FastAPI: verifikasi token Bearer (atau tiket unduh GET) dan kembalikan identitas."""
    if setelan.auth_mode == "dev":
        return _pengguna_dev()

    rahasia = setelan.auth_secret.strip()
    if not rahasia:
        raise HTTPException(
            status_code=503,
            detail="autentikasi backend belum dikonfigurasi (AUTH_SECRET kosong)",
        )

    token = _ambil_bearer(request.headers.get("authorization"))
    pakai_tiket = False
    if token is None and request.method in ("GET", "HEAD"):
        tiket = (request.query_params.get("tiket") or "").strip()
        if tiket:
            token = tiket
            pakai_tiket = True

    if token is None:
        raise HTTPException(
            status_code=401,
            detail="token sesi tidak ditemukan",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        klaim = jwt.decode(
            token,
            rahasia,
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

    if pakai_tiket and klaim.get("tujuan") != "unduh":
        raise HTTPException(
            status_code=401,
            detail="tiket unduh tidak valid",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
        foto_url=_teks_atau_none(klaim.get("foto_url")),
    )


def _teks_atau_none(nilai: object) -> str | None:
    """Ubah klaim opsional menjadi teks; ``None`` bila kosong."""
    if nilai is None:
        return None
    teks = str(nilai).strip()
    return teks or None


def kode_kabupaten(kdprov: str, kdkab: str) -> str:
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
        kode = kode_kabupaten(provinsi_pengguna, kab)
        if len(kode) != 4 or not kode.isdigit() or not kode.startswith(provinsi_pengguna):
            raise AksesDitolak(f"kode kabupaten/kota '{kdkab}' tidak valid")
        return provinsi_pengguna, kode

    # Petugas kabupaten/kota.
    kewenangan = pengguna.peran.kdkab
    if kab is None:
        return provinsi_pengguna, kewenangan
    kode = kode_kabupaten(provinsi_pengguna, kab)
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
