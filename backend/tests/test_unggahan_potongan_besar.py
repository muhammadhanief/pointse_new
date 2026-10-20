"""Uji alur potongan dengan berkas hasil edit Proses B yang asli (151 MB)."""

from __future__ import annotations

import filecmp
import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings

BERKAS = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "Titik Bangunan dan SLS"
    / "3307"
    / "hasil_edit_runmodel2.gpkg"
)


def rss_bytes() -> int | None:
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


def hash_berkas(jalur: Path) -> tuple[str, int]:
    hash_sha = hashlib.sha256()
    ukuran = 0
    with jalur.open("rb") as masuk:
        while True:
            blok = masuk.read(4 * 1024 * 1024)
            if not blok:
                break
            ukuran += len(blok)
            hash_sha.update(blok)
    return hash_sha.hexdigest(), ukuran


@pytest.mark.slow
@pytest.mark.skipif(not BERKAS.is_file(), reason="berkas uji 151 MB tidak ada")
def test_unggahan_151mb_byte_identik(
    klien: TestClient,
    setelan: Settings,
    dir_unggahan: Path,
) -> None:
    """Semua potongan disusun ulang menjadi berkas identik byte demi byte."""
    ukuran = BERKAS.stat().st_size
    resp = klien.post(
        "/unggahan/mulai",
        json={"nama": BERKAS.name, "ukuran": ukuran, "jenis": "titik"},
    )
    assert resp.status_code == 201, resp.text
    sesi = resp.json()
    id_unggah = sesi["unggahan_id"]
    potongan = sesi["ukuran_potongan"]
    total = sesi["jumlah_potongan"]
    assert total > 1

    with BERKAS.open("rb") as masuk:
        for nomor in range(1, total + 1):
            bagian = masuk.read(potongan)
            assert bagian
            resp = klien.post(
                f"/unggahan/{id_unggah}/potongan/{nomor}",
                content=bagian,
                headers={
                    "content-type": "application/octet-stream",
                    "x-sha256": hashlib.sha256(bagian).hexdigest(),
                },
            )
            assert resp.status_code == 200, (nomor, resp.text)

    rss_awal = rss_bytes()
    selesai = klien.post(f"/unggahan/{id_unggah}/selesai")
    rss_akhir = rss_bytes()
    assert selesai.status_code == 200, selesai.text
    hasil = selesai.json()

    hash_asli, ukuran_asli = hash_berkas(BERKAS)
    assert hasil["ukuran"] == ukuran_asli
    assert hasil["sha256"] == hash_asli

    jalur_hasil = dir_unggahan / "_unggahan" / id_unggah / BERKAS.name
    assert jalur_hasil.stat().st_size == ukuran_asli
    assert filecmp.cmp(BERKAS, jalur_hasil, shallow=False)

    # Penyusunan memakai buffer 1 MB, bukan membaca 151 MB sekaligus.
    if rss_awal is not None and rss_akhir is not None:
        assert rss_akhir - rss_awal < 40 * 1024 * 1024
