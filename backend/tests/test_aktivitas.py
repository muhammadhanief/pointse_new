"""Tes jejak audit aktivitas pengguna."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import aktivitas, auth
from app.main import app
from app.models import Aktivitas
from app.peran import PERAN_ADMIN_PROVINSI, PERAN_PETUGAS_KABKOT, Peran


def _pengguna(
    *,
    sub: str = "admin33",
    kdprov: str = "33",
    kdkab: str | None = None,
    peran: str = PERAN_ADMIN_PROVINSI,
) -> auth.Pengguna:
    return auth.Pengguna(
        sub=sub,
        username=sub,
        nama=f"Pengguna {sub}",
        org=kdprov + (kdkab[2:] if kdkab else "000"),
        peran=Peran(nama=peran, kdprov=kdprov, kdkab=kdkab),
        nip="19900101",
    )


def _baris(
    sub: str,
    *,
    kdprov: str = "33",
    kdkab: str | None = None,
    aksi: str = "unggah_a",
) -> Aktivitas:
    return Aktivitas(
        sub=sub,
        username=sub,
        nama=f"Pengguna {sub}",
        nip="19900101",
        peran=PERAN_ADMIN_PROVINSI if kdkab is None else PERAN_PETUGAS_KABKOT,
        kdprov=kdprov,
        kdkab=kdkab,
        aksi=aksi,
        objek="run",
        objek_id=1,
        detail="berkas.geojson",
    )


def test_catat_aktivitas_menyimpan_identitas(sesi: Session) -> None:
    """Helper audit menyimpan subjek, username, NIP, dan detail tindakan."""
    pengguna = _pengguna()
    baris = aktivitas.catat(
        sesi,
        pengguna,
        aksi="unggah_a",
        objek="run",
        objek_id=7,
        detail="peta.geojson",
    )

    assert baris is not None
    tersimpan = sesi.get(Aktivitas, baris.id)
    assert tersimpan is not None
    assert tersimpan.sub == "admin33"
    assert tersimpan.username == "admin33"
    assert tersimpan.nip == "19900101"
    assert tersimpan.aksi == "unggah_a"
    assert tersimpan.objek_id == 7


def test_daftar_aktivitas_dibatasi_provinsi(
    klien: TestClient, sesi: Session
) -> None:
    """Admin provinsi hanya melihat aktivitas provinsinya."""
    sesi.add_all(
        [
            _baris("admin33"),
            _baris("petugas3307", kdkab="3307", aksi="unggah_b"),
            _baris("admin34", kdprov="34"),
        ]
    )
    sesi.commit()

    admin = _pengguna()
    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin
    try:
        resp = klien.get("/aktivitas")
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert {item["sub"] for item in data["baris"]} == {
        "admin33",
        "petugas3307",
    }
    assert data["baris"][0]["aksi"] in {"unggah_a", "unggah_b"}


def test_daftar_aktivitas_hanya_admin(klien: TestClient) -> None:
    """Petugas kabupaten/kota tidak boleh membuka jejak audit."""
    petugas = _pengguna(
        sub="petugas3307",
        kdkab="3307",
        peran=PERAN_PETUGAS_KABKOT,
    )
    app.dependency_overrides[auth.pengguna_saat_ini] = lambda: petugas
    try:
        resp = klien.get("/aktivitas")
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

    assert resp.status_code == 403
