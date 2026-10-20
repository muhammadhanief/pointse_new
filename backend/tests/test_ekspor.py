"""Tes ekspor CSV/GPKG: keluaran Proses A, titik perlu tindakan, dan rekap."""

from __future__ import annotations

import csv
import io
import os
import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import ekspor
from app.config import Settings
from app.models import DASAR_POSISI, DASAR_TUGAS, Run, TitikHasil
from app.proses_a import KOLOM_HASIL, pastikan_crs4326, proses_a
from app.proses_b import KOLOM_HASIL_B, proses_b
from app.worker import proses_satu_job
from test_api_runs import (
    BARIS_A,
    BARIS_A_BENAR,
    BARIS_A_PERHATIAN,
    berkas_uji,
    berkas_uji_b,
    jalankan,
    unggah,
)


def simpan_unduhan(respons: object, tujuan: Path) -> Path:
    """Periksa balasan 200 lalu simpan isinya ke ``tujuan``."""
    assert respons.status_code == 200, respons.text  # type: ignore[attr-defined]
    tujuan.write_bytes(respons.content)  # type: ignore[attr-defined]
    return tujuan


def test_ekspor_hasil_a_sama_dengan_keluaran_proses(
    klien: TestClient,
    sesi_pabrik: sessionmaker[Session],
    setelan: Settings,
    tmp_path: Path,
) -> None:
    """GPKG ekspor A sama kolom/urutan/nilai dengan keluaran Proses A, dan di-cache."""
    titik, peta = berkas_uji(tmp_path, BARIS_A)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    respons = klien.get(f"/runs/{run_id}/ekspor/hasil-a.gpkg")
    assert respons.status_code == 200, respons.text
    assert respons.headers["content-type"] == "application/geopackage+sqlite3"
    assert (
        "3307_hasil_identifikasi_titik_ke1.gpkg"
        in respons.headers["content-disposition"]
    )

    berkas = simpan_unduhan(respons, tmp_path / "hasil_a.gpkg")
    assert pyogrio.list_layers(berkas)[0, 0] == ekspor.LAYER_HASIL_A

    hasil = gpd.read_file(berkas)
    langsung = proses_a(gpd.read_file(titik), gpd.read_file(peta))
    assert list(hasil.columns) == list(langsung.columns)
    assert hasil.crs == langsung.crs
    pd.testing.assert_frame_equal(
        hasil[list(KOLOM_HASIL)],
        langsung[list(KOLOM_HASIL)].reset_index(drop=True),
        check_dtype=False,
    )
    assert hasil.geometry.geom_equals(langsung.geometry.reset_index(drop=True)).all()

    # Unduhan kedua memakai cache (isi sama persis).
    cache = (
        Path(setelan.dir_unggahan)
        / ekspor.NAMA_FOLDER_CACHE
        / f"{ekspor.AWALAN_CACHE_HASIL_A}{run_id}.gpkg"
    )
    assert cache.is_file()
    ulang = klien.get(f"/runs/{run_id}/ekspor/hasil-a.gpkg")
    assert ulang.status_code == 200
    assert ulang.content == respons.content


def test_ekspor_hasil_b_penuh_sama_dengan_keluaran_proses(
    klien: TestClient,
    sesi_pabrik: sessionmaker[Session],
    setelan: Settings,
    tmp_path: Path,
) -> None:
    """GPKG ekspor B memakai layer dan 35 field yang sama dengan QGIS."""
    titik, peta = berkas_uji_b(tmp_path)
    run_id = unggah(klien, titik, peta, tipe="B").json()["id"]
    jalankan(sesi_pabrik)

    respons = klien.get(f"/runs/{run_id}/ekspor/hasil-b.gpkg")
    assert respons.status_code == 200, respons.text
    assert respons.headers["content-type"] == "application/geopackage+sqlite3"
    assert (
        "3307_hasil_pengecekan_titik_ke1.gpkg"
        in respons.headers["content-disposition"]
    )

    berkas = simpan_unduhan(respons, tmp_path / "hasil_b.gpkg")
    assert pyogrio.list_layers(berkas)[0, 0] == ekspor.LAYER_HASIL_B
    hasil = gpd.read_file(berkas)
    langsung = proses_b(
        pastikan_crs4326(gpd.read_file(titik), "titik"),
        pastikan_crs4326(gpd.read_file(peta), "peta"),
    )
    assert list(hasil.columns) == list(KOLOM_HASIL_B) + ["geometry"]
    kanan = langsung[list(KOLOM_HASIL_B)].reset_index(drop=True).copy()
    for kolom in ekspor._KOLOM_TEKS_B:  # noqa: SLF001 - uji tipe skema QGIS
        kanan[kolom] = kanan[kolom].astype("string").fillna("")
        hasil[kolom] = hasil[kolom].astype("string").fillna("")
    pd.testing.assert_frame_equal(
        hasil[list(KOLOM_HASIL_B)],
        kanan,
        check_dtype=False,
    )
    assert hasil.geometry.geom_equals(langsung.geometry.reset_index(drop=True)).all()
    assert (
        Path(setelan.dir_unggahan)
        / ekspor.NAMA_FOLDER_CACHE
        / f"{ekspor.AWALAN_CACHE_HASIL_B}{run_id}.gpkg"
    ).is_file()


def test_cache_hasil_a_dibatasi(tmp_path: Path, setelan: Settings) -> None:
    """Cache GPKG keluaran A hanya menyimpan beberapa berkas terbaru (LRU)."""
    folder = Path(setelan.dir_unggahan) / ekspor.NAMA_FOLDER_CACHE
    folder.mkdir(parents=True)
    berkas = [folder / f"{ekspor.AWALAN_CACHE_HASIL_A}{nomor}.gpkg" for nomor in range(4)]
    for nomor, satu in enumerate(berkas):
        satu.write_bytes(b"x")
        os.utime(satu, (1_700_000_000 + nomor, 1_700_000_000 + nomor))

    ekspor._rapikan_cache(setelan, berkas[-1])  # noqa: SLF001 - uji perilaku LRU

    tersisa = sorted(satu.name for satu in folder.glob("*.gpkg"))
    assert tersisa == [berkas[2].name, berkas[3].name]


def test_ekspor_hasil_a_409_kalau_berkas_mentah_dipangkas(
    klien: TestClient, sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Berkas mentah yang sudah dipangkas tidak bisa diproses ulang untuk ekspor."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    run = sesi.get(Run, run_id)
    assert run is not None
    shutil.rmtree(Path(run.berkas_input).parent)

    respons = klien.get(f"/runs/{run_id}/ekspor/hasil-a.gpkg")
    assert respons.status_code == 409
    assert "dipangkas" in respons.json()["detail"]


def test_ekspor_hasil_a_409_untuk_run_proses_b(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Keluaran Proses A hanya bisa diekspor dari run tipe A."""
    titik, peta = berkas_uji_b(tmp_path)
    run_id = unggah(klien, titik, peta, tipe="B").json()["id"]
    jalankan(sesi_pabrik)

    respons = klien.get(f"/runs/{run_id}/ekspor/hasil-a.gpkg")
    assert respons.status_code == 409
    assert "tipe A" in respons.json()["detail"]


def jalankan_penuh(sesi_pabrik: sessionmaker[Session], setelan: Settings) -> None:
    """Jalankan worker dengan setelan tes (folder unggahan ikut dipangkas)."""
    while proses_satu_job(sesi_pabrik, setelan):
        pass


def test_run_tengah_yang_dipangkas_tidak_bisa_diekspor(
    klien: TestClient,
    sesi: Session,
    sesi_pabrik: sessionmaker[Session],
    setelan: Settings,
    tmp_path: Path,
) -> None:
    """Hanya baseline dan sukses terakhir yang punya berkas + detail titik."""
    id_run: list[int] = []
    for nomor in range(3):
        titik, peta = berkas_uji(tmp_path / f"r{nomor}", BARIS_A_PERHATIAN)
        id_run.append(unggah(klien, titik, peta).json()["id"])
    jalankan_penuh(sesi_pabrik, setelan)

    tengah = id_run[1]
    sesi.expire_all()
    run = sesi.get(Run, tengah)
    assert run is not None and not run.detail_tersedia

    assert klien.get(f"/runs/{tengah}/ekspor/hasil-a.gpkg").status_code == 409
    assert klien.get(f"/runs/{tengah}/ekspor/titik.csv").status_code == 409
    assert klien.get(f"/runs/{tengah}/ekspor/titik.gpkg").status_code == 409

    # Baseline dan sukses terakhir tetap bisa diekspor.
    for run_id in (id_run[0], id_run[2]):
        assert klien.get(f"/runs/{run_id}/ekspor/hasil-a.gpkg").status_code == 200
        assert klien.get(f"/runs/{run_id}/ekspor/titik.csv").status_code == 200


def test_ekspor_titik_csv_dan_gpkg(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Titik perlu tindakan diekspor dengan kolom, urutan, dan geometri yang benar."""
    titik, peta = berkas_uji(tmp_path, BARIS_A_PERHATIAN)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    respons = klien.get(f"/runs/{run_id}/ekspor/titik.csv")
    assert respons.status_code == 200, respons.text
    assert respons.headers["content-type"].startswith("text/csv")
    baris = list(csv.DictReader(io.StringIO(respons.text)))

    assert list(baris[0]) == list(ekspor.KOLOM_TITIK)
    assert [satu["assignment_id"] for satu in baris] == ["1", "2", "3"]
    assert baris[0]["level_6_full_code"] == "A2"
    assert baris[0]["idsubsls_tugas"] == "A2"
    assert baris[0]["idsubsls_asal"] == "A1"
    assert baris[0]["flag_repair"] == "1"
    assert float(baris[0]["latitude_origin"]) == pytest.approx(0.2)
    assert float(baris[2]["longitude_origin"]) == pytest.approx(2.5)

    respons = klien.get(f"/runs/{run_id}/ekspor/titik.gpkg")
    berkas = simpan_unduhan(respons, tmp_path / "titik.gpkg")
    assert pyogrio.list_layers(berkas)[0, 0] == ekspor.LAYER_TITIK
    gdf = gpd.read_file(berkas)
    assert list(gdf.columns)[: len(ekspor.KOLOM_TITIK)] == list(ekspor.KOLOM_TITIK)
    assert len(gdf) == 3
    assert gdf.crs == "EPSG:4326"
    assert gdf.geometry.iloc[0].x == pytest.approx(0.2)
    assert gdf.geometry.iloc[2].x == pytest.approx(2.5)
    assert [int(satu) for satu in gdf["urut"]] == [0, 1, 2]


def test_ekspor_titik_kosong_tetap_berheader(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Run tanpa titik perlu perhatian menghasilkan CSV/GPKG kosong (bukan 409)."""
    titik, peta = berkas_uji(tmp_path, BARIS_A_BENAR)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    respons = klien.get(f"/runs/{run_id}/ekspor/titik.csv")
    assert respons.status_code == 200
    assert respons.text.strip() == ",".join(ekspor.KOLOM_TITIK)

    respons = klien.get(f"/runs/{run_id}/ekspor/titik.gpkg")
    berkas = simpan_unduhan(respons, tmp_path / "kosong.gpkg")
    gdf = gpd.read_file(berkas)
    assert gdf.empty
    assert list(gdf.columns)[: len(ekspor.KOLOM_TITIK)] == list(ekspor.KOLOM_TITIK)


def test_ekspor_rekap_csv_dengan_saringan(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Rekap diekspor per run per wilayah dan bisa disaring rentang tanggal data."""
    titik1, peta1 = berkas_uji(tmp_path / "r1", BARIS_A_PERHATIAN)
    id_jan = unggah(klien, titik1, peta1, tanggal_data="2026-01-10").json()["id"]
    titik2, peta2 = berkas_uji(tmp_path / "r2", BARIS_A_PERHATIAN)
    id_feb = unggah(klien, titik2, peta2, tanggal_data="2026-02-10").json()["id"]
    jalankan(sesi_pabrik)

    respons = klien.get(
        "/ekspor/rekap.csv",
        params={"tingkat": "desa", "tanggal_awal": "2026-02-01", "tanggal_akhir": "2026-02-28"},
    )
    assert respons.status_code == 200, respons.text
    baris = list(csv.DictReader(io.StringIO(respons.text)))
    assert list(baris[0]) == list(ekspor.KOLOM_REKAP_DESA)
    assert {satu["run_id"] for satu in baris} == {str(id_feb)}
    assert {satu["tanggal_data"] for satu in baris} == {"2026-02-10"}
    assert {satu["nmdesa"] for satu in baris} == {"KALIBEBER", "MOJOTENGAH"}
    # Proses A: semua titik perlu perhatian belum ditindak → progres 0%.
    assert {satu["persen_progres"] for satu in baris} == {"0.0"}

    respons = klien.get("/ekspor/rekap.csv", params={"tingkat": "kabupaten", "tipe": "A"})
    assert respons.status_code == 200, respons.text
    baris = list(csv.DictReader(io.StringIO(respons.text)))
    assert list(baris[0]) == list(ekspor.KOLOM_REKAP_KABUPATEN)
    assert {satu["run_id"] for satu in baris} == {str(id_jan), str(id_feb)}
    assert {satu["nmkab"] for satu in baris} == {"WONOSOBO"}

    assert klien.get("/ekspor/rekap.csv", params={"tingkat": "kecamatan"}).status_code == 422
    assert (
        klien.get(
            "/ekspor/rekap.csv",
            params={"tingkat": "desa", "tanggal_awal": "2026-03-01", "tanggal_akhir": "2026-01-01"},
        ).status_code
        == 422
    )
    assert klien.get("/ekspor/rekap.csv", params={"tipe": "C"}).status_code == 422


def test_ekspor_a_menjadi_masukan_b_tanpa_edit(
    klien: TestClient, sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Tes pulang-pergi: keluaran A yang diekspor bisa dipakai sebagai masukan B.

    Tanpa editan, titik tidak bergeser dan atribut tidak berubah, jadi rekap B harus
    sama dengan rekap A.
    """
    titik, peta = berkas_uji(tmp_path, BARIS_A)
    id_a = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    hasil_a = simpan_unduhan(
        klien.get(f"/runs/{id_a}/ekspor/hasil-a.gpkg"), tmp_path / "hasil_a.gpkg"
    )
    with hasil_a.open("rb") as berkas_titik, peta.open("rb") as berkas_peta:
        respons = klien.post(
            "/runs",
            data={"tipe": "B"},
            files={
                "titik": ("hasil_a.gpkg", berkas_titik, "application/geopackage+sqlite3"),
                "peta": ("peta.geojson", berkas_peta, "application/geo+json"),
            },
        )
    assert respons.status_code == 201, respons.text
    id_b = respons.json()["id"]
    jalankan(sesi_pabrik)

    sesi.expire_all()
    run_a = sesi.get(Run, id_a)
    run_b = sesi.get(Run, id_b)
    assert run_a is not None and run_b is not None
    assert run_b.status == "sukses"
    assert run_b.jumlah_baris == run_a.jumlah_baris

    # Tanpa editan: tidak ada titik yang tergeser atau atributnya diubah.
    titik_b = list(sesi.scalars(select(TitikHasil).where(TitikHasil.run_id == id_b)))
    assert titik_b
    assert all(satu.flag_position == 0 for satu in titik_b)
    assert all(satu.flag_edit_atr_repair == 0 for satu in titik_b)

    for dasar in (DASAR_TUGAS, DASAR_POSISI):
        rekap_a = klien.get(
            f"/runs/{id_a}/rekap", params={"tingkat": "kabupaten", "dasar": dasar}
        ).json()
        rekap_b = klien.get(
            f"/runs/{id_b}/rekap", params={"tingkat": "kabupaten", "dasar": dasar}
        ).json()
        for kolom in (
            "total",
            "belum",
            "benar_awal",
            "ditindak_posisi_benar",
            "ditindak_posisi_salah",
            "digeser",
            "tanpa_wilayah",
        ):
            assert rekap_b[kolom] == rekap_a[kolom], (dasar, kolom)
