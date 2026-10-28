"""Tes kehadiran pengguna dan pemantauan admin provinsi."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import auth
from app.main import app
from app.models import PenggunaAktif, sekarang
from app.peran import PERAN_ADMIN_PROVINSI, PERAN_PETUGAS_KABKOT, Peran


def _pengguna(
    *,
    sub: str = "admin33",
    kdprov: str = "33",
    kdkab: str | None = None,
    peran: str = PERAN_ADMIN_PROVINSI,
    foto_url: str | None = None,
) -> auth.Pengguna:
    return auth.Pengguna(
        sub=sub,
        username=sub,
        nama=f"Pengguna {sub}",
        org=kdprov + (kdkab[2:] if kdkab else "000"),
        peran=Peran(nama=peran, kdprov=kdprov, kdkab=kdkab),
        foto_url=foto_url,
    )


def _baris(
    sub: str,
    *,
    kdprov: str = "33",
    kdkab: str | None = None,
    menit_lalu: int = 0,
) -> PenggunaAktif:
    waktu = sekarang() - timedelta(minutes=menit_lalu)
    return PenggunaAktif(
        sub=sub,
        username=sub,
        nama=f"Pengguna {sub}",
        org=kdprov + (kdkab[2:] if kdkab else "000"),
        peran=PERAN_ADMIN_PROVINSI if kdkab is None else PERAN_PETUGAS_KABKOT,
        kdprov=kdprov,
        kdkab=kdkab,
        login_pada=waktu,
        terakhir_aktif=waktu,
    )


def test_kehadiran_dan_daftar_pengguna(klien: TestClient, sesi: Session) -> None:
    """Heartbeat menyimpan identitas dan menandai pengguna online."""
    admin = _pengguna(foto_url="https://sso.example/admin33.jpg")
    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin
    try:
        resp = klien.post("/kehadiran")
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 200
    row = sesi.get(PenggunaAktif, "admin33")
    assert row is not None
    assert row.nama == "Pengguna admin33"
    assert row.foto_url == "https://sso.example/admin33.jpg"
    assert row.terakhir_aktif >= row.login_pada

    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin
    try:
        resp = klien.get("/pengguna")
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["online"] == 1
    assert data["baris"][0]["sub"] == "admin33"
    assert data["baris"][0]["online"] is True


def test_daftar_pengguna_dibatasi_provinsi(klien: TestClient, sesi: Session) -> None:
    """Admin provinsi tidak melihat pengguna dari provinsi lain."""
    sesi.add_all(
        [
            _baris("admin33"),
            _baris("petugas3307", kdkab="3307"),
            _baris("admin34", kdprov="34"),
        ]
    )
    sesi.commit()

    admin = _pengguna()
    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin
    try:
        resp = klien.get("/pengguna")
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 200
    data = resp.json()
    assert {item["sub"] for item in data["baris"]} == {"admin33", "petugas3307"}
    assert data["total"] == 2


def test_daftar_pengguna_bisa_dicari(klien: TestClient, sesi: Session) -> None:
    """Parameter ``q`` menyaring nama/username/NIP/kode wilayah."""
    sesi.add_all(
        [
            _baris("admin33"),
            _baris("petugas3307", kdkab="3307"),
            _baris("petugas3374", kdkab="3374"),
        ]
    )
    sesi.commit()

    admin = _pengguna()
    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin
    try:
        resp = klien.get("/pengguna", params={"q": "3307"})
        kosong = klien.get("/pengguna", params={"q": "tidak-ada"})
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 200
    assert [item["sub"] for item in resp.json()["baris"]] == ["petugas3307"]
    assert kosong.status_code == 200
    assert kosong.json()["baris"] == []
    assert kosong.json()["total"] == 0


def test_daftar_pengguna_hanya_admin(klien: TestClient) -> None:
    """Petugas kabupaten/kota tidak boleh membuka pemantauan pengguna."""
    petugas = _pengguna(
        sub="petugas3307",
        kdkab="3307",
        peran=PERAN_PETUGAS_KABKOT,
    )
    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: petugas
    try:
        resp = klien.get("/pengguna")
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 403


def test_heartbeat_mempertahankan_foto_dan_menandai_login_baru(
    klien: TestClient, sesi: Session
) -> None:
    """Foto lama tidak hilang bila token berikutnya tidak memuat foto."""
    lama = sekarang() - timedelta(minutes=31)
    sesi.add(
        PenggunaAktif(
            sub="admin33",
            username="admin33",
            nama="Nama Lama",
            org="33000",
            peran=PERAN_ADMIN_PROVINSI,
            kdprov="33",
            kdkab=None,
            foto_url="https://sso.example/lama.jpg",
            login_pada=lama,
            terakhir_aktif=lama,
        )
    )
    sesi.commit()

    admin = _pengguna()
    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin
    try:
        resp = klien.post("/kehadiran")
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 200
    row = sesi.get(PenggunaAktif, "admin33")
    assert row is not None
    assert row.foto_url == "https://sso.example/lama.jpg"
    assert row.login_pada > lama
    assert row.terakhir_aktif > lama
