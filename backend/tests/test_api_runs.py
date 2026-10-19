"""Tes endpoint API: unggah/antre, status, daftar, hasil, dan rekap."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app.models import STATUS_MENUNGGU, Run
from app.worker import proses_satu_job

# Berkas titik: dua titik di SubSLS A1, satu di A2 (level_6 tetap A1) supaya ada
# titik yang "belum diperbaiki", dan satu di luar peta.
BARIS_A = (
    data_kecil.baris_titik_a("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_a("2", "A1", 0.3, 0.3),
    data_kecil.baris_titik_a("3", "A1", 0.5, 2.5),
)

PETA_TIGA_WILAYAH = {"A2": {"kddesa": "330701002", "nmdesa": "MOJOTENGAH"}}


def unggah(
    klien: TestClient,
    berkas_titik: Path,
    berkas_peta: Path,
    tipe: str = "A",
    **data: Any,
) -> Any:
    """Kirim POST /runs dengan dua berkas (multipart)."""
    with berkas_titik.open("rb") as titik, berkas_peta.open("rb") as peta:
        return klien.post(
            "/runs",
            data={"tipe": tipe, **data},
            files={
                "titik": ("titik.geojson", titik, "application/geo+json"),
                "peta": ("peta.geojson", peta, "application/geo+json"),
            },
        )


def berkas_uji(tmp_path: Path, baris: tuple[dict[str, Any], ...] = BARIS_A) -> tuple[Path, Path]:
    """Tulis berkas titik dan peta kecil untuk tes."""
    titik = data_kecil.tulis(data_kecil.titik_a(*baris), tmp_path / "masukan" / "titik.geojson")
    peta = data_kecil.tulis(data_kecil.peta(PETA_TIGA_WILAYAH), tmp_path / "masukan" / "peta.geojson")
    return titik, peta


def jalankan(sesi_pabrik: sessionmaker[Session]) -> None:
    """Jalankan worker sampai tidak ada job antre lagi."""
    while proses_satu_job(sesi_pabrik):
        pass


def test_unggah_membuat_job_menunggu(
    klien: TestClient, sesi: Session, tmp_path: Path, dir_unggahan: Path
) -> None:
    """Unggahan langsung membuat baris runs berstatus menunggu + berkas di disk."""
    titik, peta = berkas_uji(tmp_path)
    resp = unggah(klien, titik, peta, user="petugas")

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == STATUS_MENUNGGU
    assert data["tipe"] == "A"
    assert data["kdkab"] == "3307"
    assert data["user"] == "petugas"
    assert data["nama_file_input"] == "titik.geojson"
    assert data["nama_file_peta"] == "peta.geojson"
    assert data["jumlah_baris"] is None

    run = sesi.get(Run, data["id"])
    assert run is not None
    berkas_input = Path(run.berkas_input)
    assert berkas_input.exists() and Path(run.berkas_peta).exists()
    assert dir_unggahan in berkas_input.parents
    assert run.layer_input is not None and run.layer_peta is not None


def test_status_dan_daftar_job(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Status satu job memuat jumlah hasil; daftar job bisa disaring."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]

    status = klien.get(f"/runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["status"] == STATUS_MENUNGGU
    assert status.json()["jumlah_tersimpan"] == 0

    daftar = klien.get("/runs", params={"tipe": "A", "kdkab": "3307"})
    assert daftar.status_code == 200
    assert daftar.json()["total"] == 1
    assert daftar.json()["baris"][0]["id"] == run_id

    kosong = klien.get("/runs", params={"tipe": "B"})
    assert kosong.json()["total"] == 0

    # Setelah dijalankan, jumlah hasil muncul di status.
    jalankan(sesi_pabrik)
    assert klien.get(f"/runs/{run_id}").json()["jumlah_tersimpan"] == 3


def test_hasil_job_dengan_paging(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Hasil titik dibalas urut seperti keluaran Proses A, dengan paging."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    resp = klien.get(f"/runs/{run_id}/hasil", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert [baris["assignment_id"] for baris in data["baris"]] == ["1", "2"]

    halaman2 = klien.get(f"/runs/{run_id}/hasil", params={"limit": 2, "offset": 2}).json()
    assert [baris["assignment_id"] for baris in halaman2["baris"]] == ["3"]

    pertama = data["baris"][0]
    assert pertama["flag_repair"] == 0
    assert pertama["idsubsls_origin"] == "A1"
    assert pertama["kdkab"] == "3307"
    # titik nomor 3 ada di SubSLS A2, jadi wilayahnya A2 dan flag_repair = 1
    ketiga = halaman2["baris"][0]
    assert ketiga["idsubsls_origin"] == "A2"
    assert ketiga["flag_repair"] == 1
    assert ketiga["nmdesa"] == "MOJOTENGAH"


def test_rekap_progres_per_tingkat(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Rekap menjumlahkan flag_repair per wilayah pada tiap tingkat."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    kabupaten = klien.get(f"/runs/{run_id}/rekap").json()
    assert kabupaten["tingkat"] == "kabupaten"
    assert (kabupaten["total"], kabupaten["sudah"], kabupaten["belum"]) == (3, 2, 1)
    assert kabupaten["persen_belum"] == 33.33
    assert kabupaten["baris"] == [
        {
            "kode": "3307",
            "nama": "WONOSOBO",
            "jumlah": 3,
            "sudah": 2,
            "belum": 1,
            "persen_belum": 33.33,
        }
    ]

    desa = klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "desa"}).json()
    assert [baris["kode"] for baris in desa["baris"]] == ["330701001", "330701002"]
    assert [baris["jumlah"] for baris in desa["baris"]] == [2, 1]
    assert [baris["belum"] for baris in desa["baris"]] == [0, 1]
    assert desa["persen_belum"] == 33.33

    sls = klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "sls"}).json()
    assert [baris["kode"] for baris in sls["baris"]] == ["A1", "A2"]
    assert [baris["persen_belum"] for baris in sls["baris"]] == [0.0, 100.0]

    kecamatan = klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "kecamatan"}).json()
    assert kecamatan["baris"][0]["kode"] == "330701"


def test_rekap_job_belum_dijalankan(
    klien: TestClient, tmp_path: Path
) -> None:
    """Job yang belum jalan: rekap kosong, bukan galat."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]

    rekap = klien.get(f"/runs/{run_id}/rekap").json()
    assert rekap["total"] == 0 and rekap["baris"] == [] and rekap["persen_belum"] == 0.0


def test_unggah_menolak_tipe_tidak_dikenal(klien: TestClient, tmp_path: Path) -> None:
    """Tipe selain A/B ditolak dengan 422."""
    titik, peta = berkas_uji(tmp_path)
    resp = unggah(klien, titik, peta, tipe="C")
    assert resp.status_code == 422
    assert "tipe harus" in resp.json()["detail"]


def test_unggah_menolak_kolom_wajib_hilang(
    klien: TestClient, tmp_path: Path, dir_unggahan: Path
) -> None:
    """Berkas titik tanpa kolom wajib ditolak, berkas unggahan dibersihkan."""
    baris = data_kecil.baris_titik_a("1")
    del baris["nama_usaha_bang"]
    titik, peta = berkas_uji(tmp_path, (baris,))

    resp = unggah(klien, titik, peta)
    assert resp.status_code == 422
    assert "kolom wajib" in resp.json()["detail"]
    assert list(dir_unggahan.iterdir()) == [], "folder unggahan tidak dibersihkan"


def test_unggah_menolak_peta_banyak_kabupaten(klien: TestClient, tmp_path: Path) -> None:
    """Peta dengan lebih dari satu kdkab ditolak (satu job = satu kabupaten)."""
    titik = data_kecil.tulis(data_kecil.titik_a(BARIS_A[0]), tmp_path / "titik.geojson")
    peta = data_kecil.tulis(
        data_kecil.peta({"A2": {"kdkab": "3308", "nmkab": "PURWOREJO"}}),
        tmp_path / "peta.geojson",
    )

    resp = unggah(klien, titik, peta)
    assert resp.status_code == 422
    assert "2 kabupaten/kota" in resp.json()["detail"]


def test_unggah_menolak_layer_yang_tidak_ada(klien: TestClient, tmp_path: Path) -> None:
    """Nama layer yang tidak ada di berkas ditolak dengan daftar pilihan."""
    titik, peta = berkas_uji(tmp_path)
    resp = unggah(klien, titik, peta, tipe="A", layer_titik="bukan_layer")

    assert resp.status_code == 422
    assert "tidak ada di berkas titik" in resp.json()["detail"]


def test_job_tidak_ditemukan(klien: TestClient) -> None:
    """Id job yang tidak ada menghasilkan 404 pada status, hasil, dan rekap."""
    for alamat in ("/runs/999", "/runs/999/hasil", "/runs/999/rekap"):
        assert klien.get(alamat).status_code == 404


def test_tingkat_rekap_tidak_dikenal(
    klien: TestClient, tmp_path: Path
) -> None:
    """Tingkat rekap di luar pilihan ditolak FastAPI (422)."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]
    assert klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "kelurahan"}).status_code == 422


def test_hasil_menambah_kolom_proses_b_kosong(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Hasil Proses A tetap punya kolom khusus Proses B, isinya NULL."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    baris = klien.get(f"/runs/{run_id}/hasil").json()["baris"][0]
    for nama in ("flag_position", "flag_edit_atr_repair", "idsubsls_edited", "latitude_edited"):
        assert nama in baris
        assert baris[nama] is None
