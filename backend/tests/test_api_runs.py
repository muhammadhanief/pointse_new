"""Tes endpoint API: unggah/antre, status, daftar, hasil, dan rekap."""

from __future__ import annotations

from datetime import UTC, date, datetime
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

# Varian BARIS_A yang semuanya sudah benar (level_6 = SubSLS posisinya): semuanya
# masuk ``benar_awal``, jadi ``titik_hasil`` run-nya kosong.
BARIS_A_BENAR = (
    data_kecil.baris_titik_a("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_a("2", "A1", 0.3, 0.3),
    data_kecil.baris_titik_a("3", "A1", 0.5, 0.5),
)

# Varian BARIS_A yang ketiga titiknya perlu perhatian (level_6 = A2, posisinya di
# A1) supaya semuanya tersimpan di ``titik_hasil`` (untuk tes paging hasil).
BARIS_A_PERHATIAN = (
    data_kecil.baris_titik_a("1", "A2", 0.2, 0.2),
    data_kecil.baris_titik_a("2", "A2", 0.3, 0.3),
    data_kecil.baris_titik_a("3", "A1", 0.5, 2.5),
)

BARIS_B = (
    data_kecil.baris_titik_b("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_b("2", "A1", 0.3, 0.3, latitude=0.9, longitude=2.5),
    data_kecil.baris_titik_b("3", "A1", 0.4, 0.4, flag_repair_initial=1, flag_repair=0),
)


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
    peta = data_kecil.tulis(data_kecil.peta(), tmp_path / "masukan" / "peta.geojson")
    return titik, peta


def berkas_uji_b(tmp_path: Path, baris: tuple[dict[str, Any], ...] = BARIS_B) -> tuple[Path, Path]:
    """Tulis berkas titik Proses B dan peta kecil untuk tes."""
    titik = data_kecil.tulis(data_kecil.titik_b(*baris), tmp_path / "masukan" / "titik_b.geojson")
    peta = data_kecil.tulis(data_kecil.peta(), tmp_path / "masukan" / "peta.geojson")
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
    assert data["kdprov"] == "33"
    assert data["kdkab"] == "3307"
    assert data["user"] == "petugas"
    assert data["nama_file_input"] == "titik.geojson"
    assert data["nama_file_peta"] == "peta.geojson"
    assert data["jumlah_baris"] is None
    assert data["jumlah_tanpa_wilayah"] is None
    # belum ada detail tersimpan; tanggal data default tanggal unggah
    assert data["detail_tersedia"] is False
    assert data["tanggal_data"] == datetime.now(UTC).date().isoformat()

    run = sesi.get(Run, data["id"])
    assert run is not None
    berkas_input = Path(run.berkas_input)
    assert berkas_input.exists() and Path(run.berkas_peta).exists()
    assert dir_unggahan in berkas_input.parents
    assert run.layer_input is not None and run.layer_peta is not None


def test_unggah_bisa_mengisi_tanggal_data(
    klien: TestClient, sesi: Session, tmp_path: Path
) -> None:
    """``tanggal_data`` boleh diisi saat unggah; ``created_at`` tetap waktu unggah."""
    titik, peta = berkas_uji(tmp_path)
    resp = unggah(klien, titik, peta, tanggal_data="2026-01-15")

    assert resp.status_code == 201, resp.text
    assert resp.json()["tanggal_data"] == "2026-01-15"
    run = sesi.get(Run, resp.json()["id"])
    assert run is not None
    assert run.tanggal_data == date(2026, 1, 15)
    assert run.created_at is not None


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
    assert status.json()["detail_tersedia"] is False

    daftar = klien.get("/runs", params={"tipe": "A", "kdprov": "33", "kdkab": "3307"})
    assert daftar.status_code == 200
    assert daftar.json()["total"] == 1
    assert daftar.json()["baris"][0]["id"] == run_id

    assert klien.get("/runs", params={"tipe": "B"}).json()["total"] == 0
    assert klien.get("/runs", params={"kdprov": "34"}).json()["total"] == 0

    # Setelah dijalankan, yang tersimpan hanya titik yang perlu perhatian.
    jalankan(sesi_pabrik)
    status = klien.get(f"/runs/{run_id}").json()
    assert status["jumlah_tersimpan"] == 1
    assert status["jumlah_baris"] == 3
    assert status["jumlah_tanpa_wilayah"] == 0
    assert status["detail_tersedia"] is True


def test_hasil_job_dengan_paging(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Hasil titik dibalas urut seperti keluaran Proses A, dengan paging.

    Ketiga titik perlu perhatian (``level_6`` = A2, posisinya di A1) supaya
    semuanya tersimpan: titik ``benar_awal`` sudah dipangkas dari ``titik_hasil``.
    """
    titik, peta = berkas_uji(tmp_path, BARIS_A_PERHATIAN)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    resp = klien.get(f"/runs/{run_id}/hasil", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["detail_tersedia"] is True
    assert data["total"] == 3
    assert [baris["assignment_id"] for baris in data["baris"]] == ["1", "2"]
    assert [baris["urut"] for baris in data["baris"]] == [0, 1]

    halaman2 = klien.get(f"/runs/{run_id}/hasil", params={"limit": 2, "offset": 2}).json()
    assert [baris["assignment_id"] for baris in halaman2["baris"]] == ["3"]

    pertama = data["baris"][0]
    assert pertama["flag_repair"] == 1
    assert pertama["kk"] == 1 and pertama["btt"] == 1
    assert pertama["usaha"] == 0
    assert pertama["level_6_full_code"] == "A2"
    # wilayah penugasan (dari level_6_full_code) dan wilayah posisi (hasil join)
    assert pertama["wilayah_tugas"]["idsubsls"] == "A2"
    assert pertama["wilayah_tugas"]["nmdesa"] == "MOJOTENGAH"
    assert pertama["wilayah_asal"]["idsubsls"] == "A1"
    assert pertama["wilayah_asal"]["nmdesa"] == "KALIBEBER"
    assert pertama["wilayah_asal"]["kdkab"] == "3307"
    assert pertama["wilayah_asal"]["nmsls"] == "SLS 001"
    # Proses A tidak punya wilayah hasil edit
    assert pertama["wilayah_edit"] is None

    # titik nomor 3 ada di SubSLS A2, jadi wilayah posisinya A2 dan flag_repair = 1
    ketiga = halaman2["baris"][0]
    assert ketiga["wilayah_asal"]["idsubsls"] == "A2"
    assert ketiga["wilayah_asal"]["nmdesa"] == "MOJOTENGAH"
    assert ketiga["wilayah_tugas"]["idsubsls"] == "A1"
    assert ketiga["flag_repair"] == 1


def test_rekap_progres_per_tingkat(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Rekap dibaca dari snapshot per desa/kabupaten; drill-down dari ``titik_hasil``."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    # Dasar bawaan dashboard = "tugas" (wilayah penugasan titik / level_6_full_code)
    kabupaten = klien.get(f"/runs/{run_id}/rekap").json()
    assert kabupaten["tingkat"] == "kabupaten"
    assert kabupaten["dasar"] == "tugas"
    assert (kabupaten["total"], kabupaten["belum"]) == (3, 1)
    # Proses A: ``flag_edit_atr_repair`` dan ``flag_position`` kosong, jadi titik
    # ``flag_repair`` = 0 masuk ``benar_awal`` dan ``digeser`` = 0.
    assert (kabupaten["benar_awal"], kabupaten["digeser"]) == (2, 0)
    assert (kabupaten["ditindak_posisi_benar"], kabupaten["ditindak_posisi_salah"]) == (0, 0)
    assert kabupaten["tanpa_wilayah"] == 0
    # belum ada yang ditindak: 0 / (belum 1 + ditindak 0) = 0%
    assert kabupaten["persen_progres"] == 0.0
    assert kabupaten["baris"] == [
        {
            "kode": "3307",
            "nama": "WONOSOBO",
            "jumlah": 3,
            "belum": 1,
            "ditindak_posisi_benar": 0,
            "ditindak_posisi_salah": 0,
            "benar_awal": 2,
            "digeser": 0,
            "tanpa_wilayah": 0,
            "persen_progres": 0.0,
        }
    ]

    kecamatan = klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "kecamatan"}).json()
    assert kecamatan["baris"][0]["kode"] == "330701"

    # Dasar posisi: titik terbagi menurut hasil join peta (dua di A1, satu di A2)
    desa = klien.get(
        f"/runs/{run_id}/rekap", params={"tingkat": "desa", "dasar": "posisi"}
    ).json()
    assert desa["dasar"] == "posisi"
    assert [baris["kode"] for baris in desa["baris"]] == ["330701001", "330701002"]
    assert [baris["jumlah"] for baris in desa["baris"]] == [2, 1]
    assert [baris["belum"] for baris in desa["baris"]] == [0, 1]
    assert [baris["benar_awal"] for baris in desa["baris"]] == [2, 0]
    # desa pertama: belum 0 + ditindak 0 = penyebut 0 -> persentasenya kosong
    assert [baris["persen_progres"] for baris in desa["baris"]] == [None, 0.0]
    assert desa["persen_progres"] == 0.0

    # Dasar tugas: ketiga titik masuk SubSLS A1 (wilayah penugasannya). Tingkat
    # SLS/SubSLS dihitung saat diminta dari ``titik_hasil``, jadi hanya titik yang
    # perlu perhatian (titik 3) yang ikut dihitung di sini.
    subsls = klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "subsls"}).json()
    assert [baris["kode"] for baris in subsls["baris"]] == ["A1"]
    assert [(baris["belum"], baris["ditindak"]) for baris in subsls["baris"]] == [(1, 0)]
    assert (subsls["belum"], subsls["ditindak"], subsls["persen_progres"]) == (1, 0, 0.0)

    sls = klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "sls"}).json()
    assert [baris["kode"] for baris in sls["baris"]] == ["3307010010003900"]
    assert [baris["nama"] for baris in sls["baris"]] == ["SLS 001"]
    # tingkat SLS tidak punya baris "(tanpa wilayah)" pada data ini
    assert all(baris["kode"] is not None for baris in sls["baris"])

    # dasar posisi: hanya SubSLS A2 yang masih punya titik perlu perhatian
    subsls_posisi = klien.get(
        f"/runs/{run_id}/rekap", params={"tingkat": "subsls", "dasar": "posisi"}
    ).json()
    assert [baris["kode"] for baris in subsls_posisi["baris"]] == ["A2"]
    assert [(baris["belum"], baris["ditindak"]) for baris in subsls_posisi["baris"]] == [(1, 0)]


def test_rekap_persen_progres_kosong_kalau_penyebut_nol(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Persentase progres kosong (``null``) kalau belum dan tindakan sama-sama 0."""
    baris = (
        data_kecil.baris_titik_a("1", "A1", 0.2, 0.2),
        data_kecil.baris_titik_a("2", "A1", 0.3, 0.3),
    )
    titik, peta = berkas_uji(tmp_path, baris)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    rekap = klien.get(f"/runs/{run_id}/rekap").json()
    assert (rekap["belum"], rekap["benar_awal"]) == (0, 2)
    assert (rekap["ditindak_posisi_benar"], rekap["ditindak_posisi_salah"]) == (0, 0)
    assert rekap["persen_progres"] is None
    assert rekap["baris"][0]["persen_progres"] is None


def test_rekap_memuat_kategori_tanpa_wilayah(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Titik di luar peta / tak punya SubSLS tugas muncul sebagai baris "(tanpa wilayah)".

    Baris kategori itu (``kode`` None) diletakkan paling akhir, dan jumlah tiap dasar
    tetap sama dengan jumlah baris run (termasuk titik ``benar_awal`` yang hanya
    terhitung di rekap).
    """
    baris = (
        *BARIS_A,
        # di luar semua poligon: tidak punya wilayah posisi
        data_kecil.baris_titik_a("4", "A1", 5.0, 5.0),
        # SubSLS tugas tidak ada di peta: tidak punya wilayah tugas
        data_kecil.baris_titik_a("5", "A9", 0.2, 0.2),
    )
    titik, peta = berkas_uji(tmp_path, baris)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    # tingkat kabupaten: seluruh titik run (5) tetap terhitung
    kabupaten = klien.get(f"/runs/{run_id}/rekap").json()
    assert (kabupaten["total"], kabupaten["belum"], kabupaten["benar_awal"]) == (5, 3, 2)
    assert (kabupaten["tanpa_wilayah"], kabupaten["baris"][0]["tanpa_wilayah"]) == (1, 1)

    # drill-down tugas: titik 4 punya SubSLS tugas (A1) tapi posisinya di luar poligon,
    # titik 5 SubSLS tugasnya (A9) tidak ada di peta -> baris "(tanpa wilayah)"
    tugas = klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "subsls"}).json()
    assert [baris_["kode"] for baris_ in tugas["baris"]] == ["A1", None]
    assert tugas["baris"][-1]["nama"] == "(tanpa wilayah)"
    assert (tugas["belum"], tugas["baris"][-1]["belum"]) == (3, 1)

    posisi = klien.get(
        f"/runs/{run_id}/rekap", params={"tingkat": "subsls", "dasar": "posisi"}
    ).json()
    assert [baris_["kode"] for baris_ in posisi["baris"]] == ["A1", "A2", None]
    assert posisi["baris"][-1]["nama"] == "(tanpa wilayah)"
    assert (posisi["belum"], [baris_["belum"] for baris_ in posisi["baris"]]) == (3, [1, 1, 1])


def test_rekap_job_belum_dijalankan(
    klien: TestClient, tmp_path: Path
) -> None:
    """Job yang belum jalan: rekap kosong, bukan galat."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]

    rekap = klien.get(f"/runs/{run_id}/rekap").json()
    assert rekap["total"] == 0 and rekap["baris"] == []
    # belum ada hasil: penyebutnya 0, jadi persentasenya kosong (bukan 0%)
    assert rekap["persen_progres"] is None
    assert rekap["dasar"] == "tugas"


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
    """Id job yang tidak ada menghasilkan 404 pada status, hasil, rekap, dan perubahan."""
    for alamat in ("/runs/999", "/runs/999/hasil", "/runs/999/rekap"):
        assert klien.get(alamat).status_code == 404
    assert klien.get("/perubahan", params={"run_awal": 999, "run_akhir": 998}).status_code == 404


def test_rekap_detail_dipangkas_dibalas_409(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Drill-down SLS/SubSLS 409 kalau detail titik run sudah dipangkas.

    Yang disimpan hanya detail run baseline dan run sukses terakhir; run di antaranya
    masih punya baris ``runs`` dan rekapnya (tingkat kabupaten/kecamatan/desa tetap 200).
    """
    titik, peta = berkas_uji(tmp_path)
    id_pertama = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)
    id_tengah = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)
    id_terakhir = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    # run tengah: detailnya dipangkas saat run terakhir sukses
    assert klien.get(f"/runs/{id_tengah}").json()["detail_tersedia"] is False
    assert klien.get(f"/runs/{id_tengah}/hasil").json()["total"] == 0
    detail = klien.get(f"/runs/{id_tengah}/rekap", params={"tingkat": "subsls"})
    assert detail.status_code == 409
    assert "dipangkas" in detail.json()["detail"]
    # rekap per tabel tetap tersedia (angka rekap tidak ikut dipangkas)
    rekap = klien.get(f"/runs/{id_tengah}/rekap").json()
    assert (rekap["total"], rekap["belum"], rekap["benar_awal"]) == (3, 1, 2)

    # baseline dan run sukses terakhir masih bisa drill-down
    for run_id in (id_pertama, id_terakhir):
        assert klien.get(f"/runs/{run_id}").json()["detail_tersedia"] is True
        assert (
            klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "subsls"}).status_code == 200
        )

    # baris runs run tengah tidak dihapus
    assert klien.get(f"/runs/{id_tengah}").status_code == 200


def test_ringkasan_dan_tren(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Ringkasan memakai run sukses terakhir tiap tipe; tren per tanggal data.

    Dua run Proses A (tanggal data berbeda, yang kedua sudah beres semua) dan satu run
    Proses B; tren memakai run sukses terakhir pada tiap tanggal data.
    """
    titik, peta = berkas_uji(tmp_path)
    id_a1 = unggah(klien, titik, peta, tanggal_data="2026-01-01").json()["id"]
    jalankan(sesi_pabrik)

    titik, peta = berkas_uji(tmp_path, BARIS_A_BENAR)
    id_a2 = unggah(klien, titik, peta, tanggal_data="2026-01-02").json()["id"]
    jalankan(sesi_pabrik)

    titik_b, peta_b = berkas_uji_b(tmp_path)
    id_b = unggah(klien, titik_b, peta_b, tipe="B", tanggal_data="2026-01-02").json()["id"]
    jalankan(sesi_pabrik)

    ringkasan = klien.get("/ringkasan").json()
    assert len(ringkasan["baris"]) == 1
    kab = ringkasan["baris"][0]
    assert (kab["kdprov"], kab["kdkab"]) == ("33", "3307")
    assert (kab["nmprov"], kab["nmkab"]) == ("JAWA TENGAH", "WONOSOBO")
    assert kab["belum_ada_upload_tipe_b"] is False
    assert [satu["tipe"] for satu in kab["terakhir"]] == ["A", "B"]
    a, b = kab["terakhir"]
    assert (a["run_id"], a["tanggal_data"]) == (id_a2, "2026-01-02")
    assert (a["belum"], a["ditindak"], a["persen_progres"]) == (0, 0, None)
    assert b["run_id"] == id_b
    assert b["belum"] == 1 and b["ditindak"] == 1

    # kabupaten/kota tanpa unggahan Proses B ditandai
    assert klien.get("/ringkasan", params={"tipe": "A"}).json()["baris"][0][
        "belum_ada_upload_tipe_b"
    ] is False
    assert klien.get("/ringkasan", params={"kdprov": "34"}).json()["baris"] == []

    tren = klien.get("/tren", params={"tipe": "A"}).json()
    assert (tren["tingkat"], tren["dasar"], tren["tipe"]) == ("kabupaten", "tugas", "A")
    assert [
        (satu["tanggal_data"], satu["run_id"], satu["belum"], satu["persen_progres"])
        for satu in tren["baris"]
    ] == [("2026-01-01", id_a1, 1, 0.0), ("2026-01-02", id_a2, 0, None)]

    provinsi = klien.get("/tren", params={"tingkat": "provinsi", "tipe": "A"}).json()
    assert [
        (satu["tanggal_data"], satu["kdprov"], satu["kdkab"], satu["belum"])
        for satu in provinsi["baris"]
    ] == [("2026-01-01", "33", None, 1), ("2026-01-02", "33", None, 0)]


def test_progres_b_memakai_target_proses_a_pertama(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Target dari run A pertama; setiap upload B menjadi satu titik progres."""
    titik, peta = berkas_uji(tmp_path)
    id_a = unggah(klien, titik, peta, tanggal_data="2026-01-01").json()["id"]
    jalankan(sesi_pabrik)

    titik_b, peta_b = berkas_uji_b(tmp_path)
    id_b1 = unggah(klien, titik_b, peta_b, tipe="B", tanggal_data="2026-01-03").json()["id"]
    jalankan(sesi_pabrik)
    baris_b_bebas = tuple(
        data_kecil.baris_titik_b(
            str(nomor), "A1", lat, lon, flag_repair_initial=0, flag_repair=0
        )
        for nomor, (lat, lon) in enumerate(((0.2, 0.2), (0.3, 0.3), (0.4, 0.4)), 1)
    )
    titik_b2, peta_b2 = berkas_uji_b(tmp_path, baris_b_bebas)
    id_b2 = unggah(klien, titik_b2, peta_b2, tipe="B", tanggal_data="2026-01-04").json()["id"]
    jalankan(sesi_pabrik)

    data = klien.get("/progres-b", params={"kdkab": "3307"}).json()
    assert data["target"]["run_a_id"] == id_a
    assert data["target"]["flag_1"] == 1
    assert data["target"]["total"] == 3
    assert [(baris["run_id"], baris["sisa_flag_1"], baris["beres"]) for baris in data["baris"]] == [
        (id_b1, 1, 0),
        (id_b2, 0, 1),
    ]


def test_perubahan_selisih_rekap_dan_per_titik(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Perubahan: selisih rekap pasangan mana pun, per titik baseline vs terakhir."""
    titik, peta = berkas_uji(tmp_path)
    id_awal = unggah(klien, titik, peta, tanggal_data="2026-01-01").json()["id"]
    jalankan(sesi_pabrik)

    berkas_uji(tmp_path, BARIS_A_BENAR)
    id_akhir = unggah(klien, titik, peta, tanggal_data="2026-01-02").json()["id"]
    jalankan(sesi_pabrik)

    titik_b, peta_b = berkas_uji_b(tmp_path)
    id_b = unggah(klien, titik_b, peta_b, tipe="B").json()["id"]
    jalankan(sesi_pabrik)

    ubah = klien.get(
        "/perubahan", params={"run_awal": id_awal, "run_akhir": id_akhir}
    ).json()
    assert (ubah["run_awal"], ubah["run_akhir"], ubah["dasar"]) == (id_awal, id_akhir, "tugas")
    assert ubah["kabupaten"]["jumlah"] == 0
    assert (ubah["kabupaten"]["belum"], ubah["kabupaten"]["benar_awal"]) == (-1, 1)
    assert [satu["kddesa"] for satu in ubah["desa"]] == ["330701001"]
    assert ubah["desa"][0]["selisih"]["belum"] == -1
    assert ubah["catatan"] is None

    # baseline vs run sukses terakhir: titik 3 yang tadinya belum sekarang benar awal
    titik_berubah = ubah["titik"]
    assert titik_berubah["total"] == 1
    assert titik_berubah["baris"][0]["assignment_id"] == "3"
    assert titik_berubah["baris"][0]["status_awal"] == "belum"
    assert titik_berubah["baris"][0]["status_akhir"] == "benar_awal"

    # pasangan beda tipe: selisih rekap tetap dihitung, per titik tidak
    beda = klien.get("/perubahan", params={"run_awal": id_awal, "run_akhir": id_b}).json()
    assert beda["titik"] is None
    assert beda["catatan"] is not None and "kabupaten/kota atau tipe" in beda["catatan"]
    # dasar posisi: selisihnya dihitung dari rekap dasar posisi juga
    posisi = klien.get(
        "/perubahan", params={"run_awal": id_awal, "run_akhir": id_akhir, "dasar": "posisi"}
    ).json()
    assert posisi["dasar"] == "posisi"
    assert posisi["kabupaten"]["belum"] == -1


def test_perubahan_menolak_run_belum_sukses(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Run yang belum sukses tidak bisa dibandingkan (409)."""
    titik, peta = berkas_uji(tmp_path)
    id_sukses = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)
    id_antre = unggah(klien, titik, peta).json()["id"]

    resp = klien.get("/perubahan", params={"run_awal": id_sukses, "run_akhir": id_antre})
    assert resp.status_code == 409
    assert "sudah sukses" in resp.json()["detail"]


def test_tingkat_rekap_tidak_dikenal(
    klien: TestClient, tmp_path: Path
) -> None:
    """Tingkat atau dasar rekap di luar pilihan ditolak FastAPI (422)."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]
    assert klien.get(f"/runs/{run_id}/rekap", params={"tingkat": "kelurahan"}).status_code == 422
    assert klien.get(f"/runs/{run_id}/rekap", params={"dasar": "asal"}).status_code == 422


def test_hasil_menambah_kolom_proses_b_kosong(
    klien: TestClient, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Hasil Proses A tetap punya kolom khusus Proses B, isinya NULL."""
    titik, peta = berkas_uji(tmp_path)
    run_id = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    baris = klien.get(f"/runs/{run_id}/hasil").json()["baris"][0]
    for nama in ("flag_position", "flag_edit_atr_repair", "latitude_edited", "longitude_edited"):
        assert nama in baris
        assert baris[nama] is None
    assert baris["wilayah_edit"] is None


def test_proses_b_memakai_peta_run_a_tanpa_mengubah_nama_berkas(
    klien: TestClient,
    sesi: Session,
    sesi_pabrik: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    """Peta GeoJSON dari run A disalin dengan nama yang sama agar layer tetap ketemu."""
    titik, peta = berkas_uji(tmp_path)
    id_a = unggah(klien, titik, peta).json()["id"]
    jalankan(sesi_pabrik)

    run_a = sesi.get(Run, id_a)
    assert run_a is not None
    # level_6_full_code harus berawalan kode kabupaten/kota agar sumber B terbaca.
    titik_b, _ = berkas_uji_b(
        tmp_path, (data_kecil.baris_titik_b("1", "3307A1"),)
    )
    with titik_b.open("rb") as berkas:
        resp = klien.post(
            "/runs",
            data={"tipe": "B", "sumber_run_a_id": str(id_a)},
            files={"titik": ("titik_b.geojson", berkas, "application/geo+json")},
        )

    assert resp.status_code == 201, resp.text
    run_b = sesi.get(Run, resp.json()["id"])
    assert run_b is not None
    assert Path(run_b.berkas_peta).name == Path(run_a.berkas_peta).name

    jalankan(sesi_pabrik)
    sesi.refresh(run_b)
    assert run_b.status == "sukses"
