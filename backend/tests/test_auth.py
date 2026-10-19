"""Tes verifikasi token sesi frontend dan otorisasi per wilayah (T4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import (
    AksesDitolak,
    Pengguna,
    pastikan_peran,
    pengguna_saat_ini,
    saring_akses,
)
from app.config import Settings
from app.peran import PERAN_ADMIN_PROVINSI, PERAN_PETUGAS_KABKOT

SECRET = "rahasia-uji-yang-panjangnya-lebih-dari-32-karakter"
ISSUER = "pointse"
AUDIENCE = "pointse-backend"


def _setelan(auth_required: bool = True) -> Settings:
    return Settings(
        auth_required=auth_required,
        auth_secret=SECRET,
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
    )


def _token(
    org: str,
    *,
    sub: str = "jane.smith",
    username: str = "jane.smith",
    nama: str = "Jane Smith",
    rahasia: str = SECRET,
    kedaluwarsa: bool = False,
) -> str:
    sekarang = datetime.now(UTC)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": sub,
        "username": username,
        "nama": nama,
        "org": org,
        "iat": int(sekarang.timestamp()),
        "exp": int((sekarang + (-1 if kedaluwarsa else 1) * timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, rahasia, algorithm="HS256")


def _request(token: str | None = None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
    )


def test_tanpa_token_ditolak() -> None:
    with pytest.raises(HTTPException) as galat:
        pengguna_saat_ini(_request(), _setelan())
    assert galat.value.status_code == 401
    assert galat.value.headers == {"WWW-Authenticate": "Bearer"}


def test_token_admin_provinsi_5_digit() -> None:
    pengguna = pengguna_saat_ini(_request(_token("33000")), _setelan())
    assert pengguna.username == "jane.smith"
    assert pengguna.peran.nama == PERAN_ADMIN_PROVINSI
    assert pengguna.kdprov == "33"
    assert pengguna.kdkab is None


def test_token_petugas_kabkot_5_digit() -> None:
    pengguna = pengguna_saat_ini(_request(_token("33070")), _setelan())
    assert pengguna.peran.nama == PERAN_PETUGAS_KABKOT
    assert pengguna.kdprov == "33"
    assert pengguna.kdkab == "3307"


def test_token_kedaluwarsa_atau_tanda_tangan_salah_ditolak() -> None:
    for token in (
        _token("33000", kedaluwarsa=True),
        _token("33000", rahasia="rahasia-lain-yang-juga-panjang-lebih-32-karakter"),
    ):
        with pytest.raises(HTTPException) as galat:
            pengguna_saat_ini(_request(token), _setelan())
        assert galat.value.status_code == 401


def test_org_tidak_valid_ditolak() -> None:
    with pytest.raises(HTTPException) as galat:
        pengguna_saat_ini(_request(_token("123456")), _setelan())
    assert galat.value.status_code == 403


def test_mode_tanpa_auth_memberi_pengguna_dev() -> None:
    pengguna = pengguna_saat_ini(_request(), _setelan(auth_required=False))
    assert pengguna.peran.nama == "dev"
    assert saring_akses(pengguna, "34", "3401") == ("34", "3401")


def _pengguna(org: str) -> Pengguna:
    return pengguna_saat_ini(_request(_token(org)), _setelan())


def test_admin_provinsi_dibatasi_provinsinya() -> None:
    pengguna = _pengguna("33000")
    assert saring_akses(pengguna, None, None) == ("33", None)
    assert saring_akses(pengguna, "33", "07") == ("33", "3307")
    with pytest.raises(AksesDitolak):
        saring_akses(pengguna, "34", None)


def test_petugas_kabkot_dibatasi_kabupatennya() -> None:
    pengguna = _pengguna("33070")
    assert saring_akses(pengguna, None, None) == ("33", "3307")
    assert saring_akses(pengguna, "33", "07") == ("33", "3307")
    with pytest.raises(AksesDitolak):
        saring_akses(pengguna, "33", "3308")
    with pytest.raises(AksesDitolak):
        saring_akses(pengguna, "34", None)


def test_pastikan_peran() -> None:
    admin = _pengguna("33000")
    petugas = _pengguna("33070")
    pastikan_peran(admin, PERAN_ADMIN_PROVINSI)
    with pytest.raises(AksesDitolak):
        pastikan_peran(admin, PERAN_PETUGAS_KABKOT)
    pastikan_peran(petugas, PERAN_PETUGAS_KABKOT)
    with pytest.raises(AksesDitolak):
        pastikan_peran(petugas, PERAN_ADMIN_PROVINSI)


def test_api_mewajibkan_token(klien, setelan: Settings) -> None:
    """Endpoint selain /health menolak permintaan tanpa token saat auth aktif."""
    setelan.auth_required = True
    setelan.auth_secret = SECRET
    setelan.auth_issuer = ISSUER
    setelan.auth_audience = AUDIENCE

    assert klien.get("/runs").status_code == 401
    resp = klien.get("/runs", headers={"Authorization": f"Bearer {_token('33000')}"})
    assert resp.status_code == 200, resp.text

    # Admin provinsi tidak boleh mengunggah geotag master untuk provinsi lain.
    resp = klien.get(
        "/runs",
        params={"kdprov": "34"},
        headers={"Authorization": f"Bearer {_token('33000')}"},
    )
    assert resp.status_code == 403

    # Petugas kabupaten/kota tidak boleh mengunggah master.
    resp = klien.post(
        "/geotag-master",
        data={"kdprov": "33", "kdkab": "3307"},
        files={"titik": ("master.gpkg", b"bukan-gpkg")},
        headers={"Authorization": f"Bearer {_token('33070')}"},
    )
    assert resp.status_code == 403
