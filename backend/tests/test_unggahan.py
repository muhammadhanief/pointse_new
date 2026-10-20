"""Tes unggahan body mentah (application/octet-stream) dan pemakaian unggahan_id."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app import auth
from app.config import Settings
from app.unggahan import unggah_berkas
from app.worker import proses_satu_job

KODE_A1 = "3307010001000100"
KODE_A2 = "3307010002000200"


def sha256(isi: bytes) -> str:
    return hashlib.sha256(isi).hexdigest()


def unggah(
    klien: TestClient,
    berkas: Path | bytes,
    nama: str,
    jenis: str = "peta",
    *,
    tipe_konten: str = "application/octet-stream",
) -> Any:
    isi = berkas.read_bytes() if isinstance(berkas, Path) else berkas
    return klien.post(
        "/unggahan",
        params={"jenis": jenis, "nama": nama},
        content=isi,
        headers={"content-type": tipe_konten},
    )


def test_unggah_body_mentah_master(
    klien: TestClient,
    tmp_path: Path,
    dir_master: Path,
    dir_unggahan: Path,
) -> None:
    """Body mentah dihitung SHA-256-nya, disimpan, lalu dipakai /geotag-master."""
    berkas = data_kecil.tulis(
        data_kecil.titik_a(data_kecil.baris_titik_a("1", KODE_A1, 0.2, 0.2)),
        tmp_path / "master.geojson",
    )
    isi = berkas.read_bytes()
    resp = unggah(klien, isi, "master.geojson", "master")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["ukuran"] == len(isi)
    assert data["sha256"] == sha256(isi)
    assert data["jenis"] == "master"

    simpan = dir_unggahan / "_unggahan" / data["unggahan_id"]
    assert (simpan / "master.geojson").read_bytes() == isi

    resp = klien.post(
        "/geotag-master",
        data={
            "kdprov": "33",
            "kdkab": "3307",
            "unggahan_id": data["unggahan_id"],
            "tanggal_data": "2026-10-01",
        },
    )
    assert resp.status_code == 201, resp.text
    master = resp.json()
    assert master["kdkab"] == "3307"
    assert master["jumlah_baris"] == 1
    assert master["tanggal_data"] == "2026-10-01"
    assert any(
        jalur.is_file() and jalur.name.endswith("master.geojson")
        for jalur in dir_master.rglob("*")
    )
    assert not simpan.exists()


def test_content_type_wajib_octet_stream(klien: TestClient) -> None:
    """Content-Type selain application/octet-stream ditolak 415."""
    resp = unggah(
        klien,
        b"isi",
        "peta.geojson",
        "peta",
        tipe_konten="application/json",
    )
    assert resp.status_code == 415
    assert "application/octet-stream" in resp.json()["detail"]


class PermintaanTerputus:
    """Body berhenti sebelum content-length terpenuhi."""

    headers = {
        "content-type": "application/octet-stream",
        "content-length": "10",
    }

    async def stream(self):
        yield b"12345"


def test_body_terputus_ditolak(
    setelan: Settings, dir_unggahan: Path
) -> None:
    """Body yang berhenti di tengah tidak boleh disimpan sebagai berkas utuh."""
    with pytest.raises(HTTPException) as galat:
        asyncio.run(
            unggah_berkas(
                request=PermintaanTerputus(),  # type: ignore[arg-type]
                jenis="peta",
                nama="terputus.geojson",
                setelan=setelan,
                pengguna=auth._pengguna_dev(),
            )
        )
    assert galat.value.status_code == 400
    sementara = dir_unggahan / "_sementara"
    assert not sementara.exists() or not any(sementara.iterdir())


def test_nama_berkas_cadangan_ditolak(klien: TestClient) -> None:
    """Nama yang bentrok dengan meta.json atau keluar folder ditolak 422."""
    for nama in ("meta.json", "../meta.json", "..", "."):
        resp = unggah(klien, b"isi", nama, "peta")
        assert resp.status_code == 422, (nama, resp.text)


def test_ukuran_di_atas_batas_env(
    klien: TestClient, setelan: Settings, dir_unggahan: Path
) -> None:
    """Ukuran di atas UNGGAH_MAKS_BYTES ditolak 413 tanpa menyisakan berkas."""
    setelan.unggah_maks_bytes = 1024
    resp = unggah(klien, b"x" * 2048, "peta.geojson", "peta")
    assert resp.status_code == 413
    sementara = dir_unggahan / "_sementara"
    assert not sementara.exists() or not any(sementara.iterdir())


def test_unggah_peta_membuat_job(klien: TestClient, tmp_path: Path) -> None:
    """Peta body mentah dipakai POST /runs lewat unggahan_id."""
    master = data_kecil.tulis(
        data_kecil.titik_a(data_kecil.baris_titik_a("1", KODE_A1, 0.2, 0.2)),
        tmp_path / "master.geojson",
    )
    assert (
        klien.post(
            "/geotag-master",
            data={"kdprov": "33", "kdkab": "3307"},
            files={"titik": ("master.geojson", master.read_bytes())},
        ).status_code
        == 201
    )

    peta = data_kecil.tulis(data_kecil.peta(), tmp_path / "peta.geojson")
    isi = peta.read_bytes()
    unggahan = unggah(klien, isi, "peta.geojson", "peta").json()
    resp = klien.post(
        "/runs", data={"tipe": "A", "unggahan_id": unggahan["unggahan_id"]}
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["tipe"] == "A"
    assert data["status"] == "menunggu"
    assert data["kdprov"] == "33"


def test_unggah_titik_b_memakai_sumber_a(
    klien: TestClient,
    sesi_pabrik: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    """Titik body mentah dipakai /runs dengan unggahan_id dan sumber run A."""
    master = data_kecil.tulis(
        data_kecil.titik_a(data_kecil.baris_titik_a("1", KODE_A1, 0.2, 0.2)),
        tmp_path / "master.geojson",
    )
    assert (
        klien.post(
            "/geotag-master",
            data={"kdprov": "33", "kdkab": "3307"},
            files={"titik": ("master.geojson", master.read_bytes())},
        ).status_code
        == 201
    )
    peta = data_kecil.tulis(
        data_kecil.peta(
            {"A1": {"idsubsls": KODE_A1}, "A2": {"idsubsls": KODE_A2}}
        ),
        tmp_path / "peta.geojson",
    )
    run_a = klien.post(
        "/runs",
        data={"tipe": "A"},
        files={"peta": ("peta.geojson", peta.read_bytes())},
    ).json()
    while proses_satu_job(sesi_pabrik):
        pass

    titik = data_kecil.tulis(
        data_kecil.titik_b(data_kecil.baris_titik_b("1", KODE_A1, 0.2, 0.2)),
        tmp_path / "titik_b.geojson",
    )
    unggahan = unggah(klien, titik.read_bytes(), "titik_b.geojson", "titik").json()
    resp = klien.post(
        "/runs",
        data={
            "tipe": "B",
            "unggahan_id": unggahan["unggahan_id"],
            "sumber_run_a_id": str(run_a["id"]),
        },
    )
    assert resp.status_code == 201, resp.text
    run_b = resp.json()
    assert run_b["tipe"] == "B"
    assert run_b["sumber_run_a_id"] == run_a["id"]
