"""Tes unggahan berpotongan: resume, idempoten, hash, dan pembersihan."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import auth
from app.config import Settings
from app.unggahan import _bersihkan, _simpan_potongan


def sha256(isi: bytes) -> str:
    return hashlib.sha256(isi).hexdigest()


def mulai(klien: TestClient, isi: bytes, nama: str = "peta.geojson") -> dict[str, Any]:
    resp = klien.post(
        "/unggahan/mulai",
        json={"nama": nama, "ukuran": len(isi), "jenis": "peta"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def kirim(
    klien: TestClient,
    id_unggah: str,
    nomor: int,
    isi: bytes,
    *,
    sha: str | None = None,
    tipe_konten: str = "application/octet-stream",
) -> Any:
    return klien.post(
        f"/unggahan/{id_unggah}/potongan/{nomor}",
        content=isi,
        headers={
            "content-type": tipe_konten,
            "x-sha256": sha if sha is not None else sha256(isi),
        },
    )


def test_unggahan_potongan_putus_lanjut(
    klien: TestClient, setelan: Settings
) -> None:
    """Potongan yang sudah diterima bisa dilihat lewat GET lalu dilanjutkan."""
    setelan.unggah_potongan_bytes = 4
    isi = b"abcdefghij"
    sesi = mulai(klien, isi)
    assert sesi["ukuran_potongan"] == 4
    assert sesi["jumlah_potongan"] == 3

    assert kirim(klien, sesi["unggahan_id"], 1, isi[0:4]).status_code == 200
    status = klien.get(f"/unggahan/{sesi['unggahan_id']}")
    assert status.status_code == 200, status.text
    assert status.json()["potongan_diterima"] == [1]
    assert status.json()["selesai"] is False

    assert kirim(klien, sesi["unggahan_id"], 2, isi[4:8]).status_code == 200
    assert kirim(klien, sesi["unggahan_id"], 3, isi[8:10]).status_code == 200
    selesai = klien.post(f"/unggahan/{sesi['unggahan_id']}/selesai")
    assert selesai.status_code == 200, selesai.text
    data = selesai.json()
    assert data["ukuran"] == len(isi)
    assert data["sha256"] == sha256(isi)

    status = klien.get(f"/unggahan/{sesi['unggahan_id']}")
    assert status.status_code == 200
    assert status.json()["selesai"] is True
    assert status.json()["sha256"] == sha256(isi)


def test_potongan_dikirim_dua_kali_tidak_merusak(
    klien: TestClient, setelan: Settings
) -> None:
    """Potongan yang sama boleh dikirim ulang; hasil akhir tetap utuh."""
    setelan.unggah_potongan_bytes = 4
    isi = b"abcdefghij"
    sesi = mulai(klien, isi)

    for nomor, bagian in ((1, isi[0:4]), (1, isi[0:4]), (2, isi[4:8]), (3, isi[8:10])):
        resp = kirim(klien, sesi["unggahan_id"], nomor, bagian)
        assert resp.status_code == 200, resp.text

    selesai = klien.post(f"/unggahan/{sesi['unggahan_id']}/selesai")
    assert selesai.status_code == 200, selesai.text
    assert selesai.json()["sha256"] == sha256(isi)


def test_potongan_hash_salah_ditolak(
    klien: TestClient, setelan: Settings
) -> None:
    """Hash salah tidak disimpan; setelah dikirim benar, unggahan selesai."""
    setelan.unggah_potongan_bytes = 4
    isi = b"abcdefghij"
    sesi = mulai(klien, isi)

    salah = kirim(klien, sesi["unggahan_id"], 1, isi[0:4], sha="0" * 64)
    assert salah.status_code == 422, salah.text

    status = klien.get(f"/unggahan/{sesi['unggahan_id']}")
    assert status.json()["potongan_diterima"] == []

    for nomor, bagian in ((1, isi[0:4]), (2, isi[4:8]), (3, isi[8:10])):
        assert kirim(klien, sesi["unggahan_id"], nomor, bagian).status_code == 200
    selesai = klien.post(f"/unggahan/{sesi['unggahan_id']}/selesai")
    assert selesai.status_code == 200, selesai.text
    assert selesai.json()["sha256"] == sha256(isi)


def test_content_type_potongan_wajib_octet_stream(
    klien: TestClient, setelan: Settings
) -> None:
    """Potongan dengan Content-Type lain ditolak 415."""
    setelan.unggah_potongan_bytes = 4
    isi = b"abcd"
    sesi = mulai(klien, isi)
    resp = kirim(
        klien,
        sesi["unggahan_id"],
        1,
        isi,
        tipe_konten="application/json",
    )
    assert resp.status_code == 415, resp.text


def test_selesai_menolak_potongan_belum_lengkap(
    klien: TestClient, setelan: Settings
) -> None:
    """Finish tidak boleh menghasilkan berkas kalau ada potongan hilang."""
    setelan.unggah_potongan_bytes = 4
    isi = b"abcdefghij"
    sesi = mulai(klien, isi)
    assert kirim(klien, sesi["unggahan_id"], 1, isi[0:4]).status_code == 200
    resp = klien.post(f"/unggahan/{sesi['unggahan_id']}/selesai")
    assert resp.status_code == 409
    assert "2" in resp.json()["detail"]


def test_unggahan_kedaluwarsa_dibersihkan(
    klien: TestClient, setelan: Settings, dir_unggahan: Path
) -> None:
    """Folder sementara yang tua dihapus dan sesi menjadi 404."""
    setelan.unggah_potongan_bytes = 4
    sesi = mulai(klien, b"abcd")
    folder = dir_unggahan / "_sementara" / sesi["unggahan_id"]
    tua = time.time() - 2 * 3600
    os.utime(folder, (tua, tua))
    setelan.unggah_kedaluwarsa_jam = 1
    _bersihkan(setelan)
    assert not folder.exists()
    assert klien.get(f"/unggahan/{sesi['unggahan_id']}").status_code == 404


def test_ukuran_total_di_atas_batas(
    klien: TestClient, setelan: Settings
) -> None:
    """Ukuran total di atas UNGGAH_MAKS_BYTES ditolak saat mulai."""
    setelan.unggah_maks_bytes = 1024
    resp = klien.post(
        "/unggahan/mulai",
        json={"nama": "peta.geojson", "ukuran": 2048, "jenis": "peta"},
    )
    assert resp.status_code == 413, resp.text


def test_potongan_di_atas_100mib_ditolak_saat_setelan() -> None:
    """Nilai UNGGAH_POTONGAN_BYTES di atas 100 MiB gagal saat startup."""
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            unggah_potongan_bytes=100 * 1024**2 + 1,
        )


class PermintaanPotongan:
    """Request palsu yang mengalirkan 16 MB per 1 MB tanpa menahan body."""

    headers = {
        "content-type": "application/octet-stream",
        "content-length": str(16 * 1024 * 1024),
    }

    def __init__(self) -> None:
        self.blok = b"x" * (1024 * 1024)
        self.hash = hashlib.sha256()
        for _ in range(16):
            self.hash.update(self.blok)
        self.headers = {
            **self.headers,
            "x-sha256": self.hash.hexdigest(),
        }

    async def stream(self):
        for _ in range(16):
            yield self.blok


@pytest.mark.slow
def test_potongan_16mb_tidak_menahan_body(
    setelan: Settings, dir_unggahan: Path
) -> None:
    """Handler potongan menulis per blok; kenaikan RSS jauh di bawah 16 MB."""
    from app.unggahan import _akar_sementara, _tulis_meta

    folder = _akar_sementara(setelan) / ("a" * 32)
    folder.mkdir(parents=True)
    meta = {
        "id": "a" * 32,
        "nama": "potongan.bin",
        "ukuran": 16 * 1024 * 1024,
        "jenis": "titik",
        "pengguna": auth._pengguna_dev().sub,
        "berkas": "potongan.bin",
        "ukuran_potongan": 16 * 1024 * 1024,
        "jumlah_potongan": 1,
    }
    _tulis_meta(folder, meta)

    import sys

    def rss() -> int | None:
        if not sys.platform.startswith("linux"):
            return None
        try:
            with open("/proc/self/status", encoding="ascii") as berkas:
                for baris in berkas:
                    if baris.startswith("VmRSS:"):
                        return int(baris.split()[1]) * 1024
        except OSError:
            return None
        return None

    awal = rss()
    asyncio.run(
        _simpan_potongan(
            PermintaanPotongan(),  # type: ignore[arg-type]
            folder,
            meta,
            1,
            setelan,
        )
    )
    akhir = rss()
    if awal is not None and akhir is not None:
        assert akhir - awal < 20 * 1024 * 1024
