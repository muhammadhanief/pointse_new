"""Tes alur baru: geotag master provinsi, Proses A otomatis, dan Proses B tanpa peta.

Data uji memakai kode SubSLS 16 angka (berawalan ``3307``) supaya validasi
kabupaten/kota dan penentuan kabupaten pada Proses B bisa diuji.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
from fastapi.testclient import TestClient
from shapely.geometry import box
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app.models import GeotagMaster, Run
from app.peran import PERAN_ADMIN_PROVINSI, PERAN_PETUGAS_KABKOT, peran_dari_org
from app.worker import proses_satu_job

KODE_A1 = "3307010001000100"
KODE_A2 = "3307010002000200"
KODE_LAIN = "3308010001000100"  # kabupaten lain (3308)


def peta_numerik() -> gpd.GeoDataFrame:
    """Peta dua SubSLS dengan kode 16 angka, sejajar dengan data_kecil."""
    baris = []
    for idsubsls, (x1, y1, x2, y2) in (
        (KODE_A1, (0.0, 0.0, 1.0, 1.0)),
        (KODE_A2, (2.0, 0.0, 3.0, 1.0)),
    ):
        baris.append(
            {
                **data_kecil.WILAYAH,
                "idsubsls": idsubsls,
                "idsls": idsubsls[:14],
                "nmsls": "SLS UJI",
                "geometry": box(x1, y1, x2, y2),
            }
        )
    return gpd.GeoDataFrame(baris, crs="EPSG:4326")


def baris_master() -> tuple[dict[str, Any], ...]:
    """Tiga titik master: dua di A1, satu di luar semua poligon."""
    return (
        data_kecil.baris_titik_a("1", KODE_A1, 0.2, 0.2),
        data_kecil.baris_titik_a("2", KODE_A1, 0.3, 0.3),
        data_kecil.baris_titik_a("3", KODE_A1, 0.5, 2.5),
    )


def baris_b() -> tuple[dict[str, Any], ...]:
    """Tiga titik hasil edit Proses A (semua di dalam A1)."""
    return (
        data_kecil.baris_titik_b("1", KODE_A1, 0.2, 0.2, idsubsls_origin=KODE_A1),
        data_kecil.baris_titik_b("2", KODE_A1, 0.3, 0.3, idsubsls_origin=KODE_A1),
        data_kecil.baris_titik_b("3", KODE_A1, 0.4, 0.4, idsubsls_origin=KODE_A1),
    )


def tulis_berkas(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Tulis geotag master, peta, dan titik B."""
    master = data_kecil.tulis(
        data_kecil.titik_a(*baris_master()), tmp_path / "masukan" / "master.geojson"
    )
    peta = data_kecil.tulis(peta_numerik(), tmp_path / "masukan" / "peta.geojson")
    titik_b = data_kecil.tulis(
        data_kecil.titik_b(*baris_b()), tmp_path / "masukan" / "titik_b.geojson"
    )
    return master, peta, titik_b


def unggah_master(
    klien: TestClient,
    berkas: Path,
    *,
    kdprov: str = "33",
    kdkab: str = "3307",
    **data: Any,
) -> Any:
    """Kirim POST /geotag-master."""
    with berkas.open("rb") as titik:
        return klien.post(
            "/geotag-master",
            data={"kdprov": kdprov, "kdkab": kdkab, **data},
            files={"titik": ("master.geojson", titik, "application/geo+json")},
        )


def unggah_peta(klien: TestClient, berkas: Path, **data: Any) -> Any:
    """Kirim POST /runs Proses A hanya dengan peta."""
    with berkas.open("rb") as peta:
        return klien.post(
            "/runs",
            data={"tipe": "A", **data},
            files={"peta": ("peta.geojson", peta, "application/geo+json")},
        )


def unggah_b(klien: TestClient, berkas: Path, **data: Any) -> Any:
    """Kirim POST /runs Proses B hanya dengan titik hasil edit."""
    with berkas.open("rb") as titik:
        return klien.post(
            "/runs",
            data={"tipe": "B", **data},
            files={"titik": ("titik_b.geojson", titik, "application/geo+json")},
        )


def jalankan(sesi_pabrik: sessionmaker[Session]) -> None:
    """Jalankan worker sampai antrean habis."""
    while proses_satu_job(sesi_pabrik):
        pass


def test_unggah_master_menyimpan_berkas_permanen(
    klien: TestClient,
    sesi: Session,
    tmp_path: Path,
    dir_master: Path,
) -> None:
    """Master valid disimpan di DIR_MASTER + baris geotag_master."""
    master, _, _ = tulis_berkas(tmp_path)
    resp = unggah_master(klien, master, tanggal_data="2026-10-01", user="prov")

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["kdprov"] == "33"
    assert data["kdkab"] == "3307"
    assert data["jumlah_baris"] == 3
    assert data["tanggal_data"] == "2026-10-01"
    assert data["user"] == "prov"

    baris = sesi.scalar(select(GeotagMaster))
    assert baris is not None
    assert baris.kdkab == "3307"
    assert Path(baris.berkas).exists()
    assert dir_master in Path(baris.berkas).parents

    daftar = klien.get("/geotag-master", params={"kdprov": "33", "kdkab": "3307"})
    assert daftar.status_code == 200
    assert daftar.json()["total"] == 1
    assert daftar.json()["baris"][0]["id"] == baris.id


def test_unggah_master_menolak_titik_kabupaten_lain(
    klien: TestClient, sesi: Session, tmp_path: Path
) -> None:
    """Semua level_6_full_code harus berawalan kode kabupaten yang dipilih."""
    salah = data_kecil.tulis(
        data_kecil.titik_a(
            data_kecil.baris_titik_a("1", KODE_LAIN, 0.2, 0.2)
        ),
        tmp_path / "masukan" / "salah.geojson",
    )
    resp = unggah_master(klien, salah)

    assert resp.status_code == 422
    assert "di luar kabupaten/kota 3307" in resp.json()["detail"]
    assert sesi.scalar(select(func.count()).select_from(GeotagMaster)) == 0


def test_unggah_master_bukan_file_gs_ditolak(
    klien: TestClient, tmp_path: Path
) -> None:
    """File hasil Proses 1/2 ditolak dengan petunjuk memakai file asli GS."""
    gdf = data_kecil.titik_a(
        data_kecil.baris_titik_a("1", KODE_A1, 0.2, 0.2)
    ).drop(columns=["geotag_latitude", "geotag_longitude", "count_usaha"])
    berkas = data_kecil.tulis(gdf, tmp_path / "masukan" / "bukan_gs.geojson")

    resp = unggah_master(klien, berkas)

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "asli dari GS" in detail
    assert "geotag_latitude" in detail
    assert "geotag_longitude" in detail
    assert "count_usaha" in detail


def test_unggah_peta_tanpa_master_ditolak(klien: TestClient, tmp_path: Path) -> None:
    """Peta Proses A ditolak 409 kalau master kabupaten belum ada."""
    _, peta, _ = tulis_berkas(tmp_path)
    resp = unggah_peta(klien, peta)

    assert resp.status_code == 409
    assert "geotag master" in resp.json()["detail"]


def test_peta_dengan_master_otomatis_jalan_a(
    klien: TestClient,
    sesi: Session,
    sesi_pabrik: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    """Upload peta langsung membuat job A memakai master; worker memprosesnya."""
    master, peta, _ = tulis_berkas(tmp_path)
    assert unggah_master(klien, master).status_code == 201

    resp = unggah_peta(klien, peta)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    run = sesi.get(Run, data["id"])
    master_row = sesi.scalar(select(GeotagMaster))
    assert run is not None and master_row is not None
    assert run.geotag_master_id == master_row.id
    assert Path(run.berkas_input) == Path(master_row.berkas)
    assert run.status == "menunggu"
    assert run.tanggal_data == master_row.tanggal_data

    jalankan(sesi_pabrik)
    sesi.refresh(run)
    assert run.status == "sukses"
    assert run.jumlah_baris == 3
    # Master tidak ikut terhapus oleh pemangkasan/akhir job.
    assert Path(run.berkas_input).exists()


def test_b_tanpa_a_ditolak(klien: TestClient, tmp_path: Path) -> None:
    """Proses B menolak kalau belum ada run A sukses untuk kabupaten itu."""
    _, _, titik_b = tulis_berkas(tmp_path)
    resp = unggah_b(klien, titik_b)

    assert resp.status_code == 409
    assert "belum ada Proses A" in resp.json()["detail"]


def test_b_memakai_peta_dari_run_a_terakhir(
    klien: TestClient,
    sesi: Session,
    sesi_pabrik: sessionmaker[Session],
    tmp_path: Path,
    dir_unggahan: Path,
) -> None:
    """B hanya upload titik; peta disalin dari run A terakhir."""
    master, peta, titik_b = tulis_berkas(tmp_path)
    assert unggah_master(klien, master).status_code == 201
    id_a = unggah_peta(klien, peta).json()["id"]
    jalankan(sesi_pabrik)

    run_a = sesi.get(Run, id_a)
    assert run_a is not None and run_a.status == "sukses"

    resp = unggah_b(klien, titik_b)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    run_b = sesi.get(Run, data["id"])
    assert run_b is not None
    assert run_b.sumber_run_a_id == run_a.id
    assert Path(run_b.berkas_peta) != Path(run_a.berkas_peta)
    assert Path(run_b.berkas_peta).exists()
    assert dir_unggahan in Path(run_b.berkas_peta).parents
    assert run_b.layer_peta == run_a.layer_peta
    assert run_b.kdprov == run_a.kdprov
    assert run_b.kdkab == run_a.kdkab

    jalankan(sesi_pabrik)
    sesi.refresh(run_b)
    assert run_b.status == "sukses"
    assert run_b.jumlah_baris == 3


def test_peran_dari_org_4_dan_5_digit() -> None:
    """SSO BPS mengirim org 5 digit; asumsi 4 digit tetap diterima."""
    for org in ("3300", "33000"):
        provinsi = peran_dari_org(org)
        assert provinsi.nama == PERAN_ADMIN_PROVINSI
        assert provinsi.kdprov == "33"
        assert provinsi.kdkab is None

    for org in ("3307", "33070", "33071"):
        kabkot = peran_dari_org(org)
        assert kabkot.nama == PERAN_PETUGAS_KABKOT
        assert kabkot.kdprov == "33"
        assert kabkot.kdkab == "3307"

    for salah in ("330", "3307x", "", "123456"):
        try:
            peran_dari_org(salah)
        except ValueError:
            pass
        else:  # pragma: no cover - pesan kegagalan
            raise AssertionError(f"'{salah}' seharusnya ditolak")
