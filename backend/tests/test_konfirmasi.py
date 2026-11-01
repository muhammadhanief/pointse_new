"""Tes konfirmasi pencermatan titik anomali.

Anomali tidak wajib habis: setiap temuan cukup dijelaskan kabupaten/kota. Tes di
sini menjaga dua hal utama -- konfirmasi berstatus dua saja (dengan catatan wajib
untuk "Sesuai Kondisi Kenyataan"), dan konfirmasi tetap terbawa saat run B
berikutnya memunculkan temuan yang sama (kunci stabil antar run).
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import anomali
from app.models import (
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    AnomaliTitik,
    KonfirmasiAnomali,
    Run,
    Wilayah,
)

KODE = "3325040013001300"


def _wilayah(sesi: Session, kode: str = KODE) -> Wilayah:
    baris = Wilayah(
        idsubsls=kode,
        kdprov="33",
        kdkab="3325",
        kdkec="040",
        kddesa="013",
        nmkab="BATANG",
        nmkec="REBAN",
        nmdesa="DESA 013",
        nmsls="SLS 013",
    )
    sesi.add(baris)
    sesi.flush()
    return baris


def _run(sesi: Session, tipe: str = TIPE_B) -> Run:
    run = Run(
        tipe=tipe,
        kdprov="33",
        kdkab="3325",
        user="uji",
        status=STATUS_SUKSES,
        nama_file_input="uji.geojson",
        nama_file_peta="peta.geojson",
        berkas_input="/tmp/uji.geojson",
        berkas_peta="/tmp/peta.geojson",
        jumlah_baris=0,
        detail_tersedia=1,
        anomali_versi=1,
    )
    sesi.add(run)
    sesi.flush()
    return run


def _anomali(
    sesi: Session,
    run: Run,
    wilayah: Wilayah | None,
    *,
    jenis: str = "hilang",
    assignment: str = "a1",
    unique_bang: str = "Ua1",
    kode: str | None = KODE,
) -> AnomaliTitik:
    baris = AnomaliTitik(
        run_b_id=run.id,
        jenis=jenis,
        assignment_id=assignment,
        unique_bang=unique_bang,
        level_6_full_code=kode,
        wilayah_id=wilayah.id if wilayah is not None else None,
    )
    sesi.add(baris)
    sesi.flush()
    return baris


def _siapkan(sesi: Session, jumlah: int = 3) -> Run:
    w = _wilayah(sesi)
    _run(sesi, TIPE_A)
    run_b = _run(sesi, TIPE_B)
    for i in range(jumlah):
        _anomali(
            sesi,
            run_b,
            w,
            jenis="hilang",
            assignment=f"a{i}",
            unique_bang=f"U{i}",
        )
    sesi.commit()
    return run_b


def _ids_anomali(sesi: Session) -> list[int]:
    return [
        int(satu)
        for satu in sesi.scalars(select(AnomaliTitik.id).order_by(AnomaliTitik.id))
    ]


def test_konfirmasi_sesuai_kenyataan_wajib_catatan(
    klien: TestClient, sesi: Session
) -> None:
    """Status "Sesuai Kondisi Kenyataan" ditolak bila catatan kosong."""
    _siapkan(sesi, jumlah=1)
    ids = _ids_anomali(sesi)

    gagal = klien.post(
        "/anomali/konfirmasi",
        json={"status": "sesuai_kenyataan", "anomali_ids": ids},
    )
    assert gagal.status_code == 422
    assert sesi.scalar(select(func.count()).select_from(KonfirmasiAnomali)) == 0

    # "Akan Diperbaiki" boleh tanpa catatan.
    ok = klien.post(
        "/anomali/konfirmasi",
        json={"status": "akan_diperbaiki", "anomali_ids": ids},
    )
    assert ok.status_code == 200
    assert ok.json()["jumlah"] == 1


def test_konfirmasi_ringkasan_dan_filter(klien: TestClient, sesi: Session) -> None:
    """Ringkasan "dikonfirmasi X dari Y" dan filter status bekerja."""
    _siapkan(sesi, jumlah=3)
    ids = _ids_anomali(sesi)

    simpan = klien.post(
        "/anomali/konfirmasi",
        json={"status": "akan_diperbaiki", "anomali_ids": ids[:2]},
    )
    assert simpan.json()["jumlah"] == 2

    data = klien.get("/anomali", params={"kdkab": "3325"}).json()
    assert data["ringkasan"]["total"] == 3
    assert data["ringkasan"]["terkonfirmasi"] == 2
    assert data["ringkasan"]["belum"] == 1
    kode_status = {satu["kode"] for satu in data["status_pilihan"]}
    assert kode_status == {"belum", "akan_diperbaiki", "sesuai_kenyataan"}
    # Kategori alasan sudah dihapus: cukup status + keterangan.
    assert "kategori_alasan" not in data

    belum = klien.get("/anomali", params={"kdkab": "3325", "status": "belum"}).json()
    assert belum["total"] == 1
    assert belum["baris"][0]["konfirmasi"] is None

    akan = klien.get(
        "/anomali", params={"kdkab": "3325", "status": "akan_diperbaiki"}
    ).json()
    assert akan["total"] == 2
    assert all(
        satu["konfirmasi"]["status"] == "akan_diperbaiki" for satu in akan["baris"]
    )


def test_konfirmasi_terbawa_ke_run_berikutnya(
    klien: TestClient, sesi: Session
) -> None:
    """Kunci stabil: temuan sama di run baru memakai konfirmasi lama."""
    _siapkan(sesi, jumlah=1)
    lama = sesi.scalars(select(AnomaliTitik)).one()

    klien.post(
        "/anomali/konfirmasi",
        json={
            "status": "sesuai_kenyataan",
            "catatan": "digeser sedikit menyesuaikan lapangan",
            "anomali_ids": [lama.id],
        },
    )

    w = sesi.scalars(select(Wilayah)).first()
    run_baru = _run(sesi, TIPE_B)
    _anomali(
        sesi,
        run_baru,
        w,
        jenis=lama.jenis,
        assignment=lama.assignment_id or "",
        unique_bang=lama.unique_bang or "",
    )
    sesi.commit()

    data = klien.get("/anomali", params={"kdkab": "3325"}).json()
    assert data["run"]["run_id"] == run_baru.id
    assert data["baris"][0]["konfirmasi"] is not None
    assert data["baris"][0]["konfirmasi"]["status"] == "sesuai_kenyataan"
    assert data["ringkasan"]["terkonfirmasi"] == 1


def test_batal_konfirmasi(klien: TestClient, sesi: Session) -> None:
    """Batal konfirmasi mengembalikan baris ke "Belum dikonfirmasi"."""
    _siapkan(sesi, jumlah=2)
    ids = _ids_anomali(sesi)
    klien.post(
        "/anomali/konfirmasi",
        json={"status": "akan_diperbaiki", "anomali_ids": ids},
    )
    assert sesi.scalar(select(func.count()).select_from(KonfirmasiAnomali)) == 2

    batal = klien.post("/anomali/konfirmasi/batal", json={"anomali_ids": ids})
    assert batal.status_code == 200
    assert batal.json()["jumlah"] == 2
    assert sesi.scalar(select(func.count()).select_from(KonfirmasiAnomali)) == 0


def test_konfirmasi_semua_hasil_filter(klien: TestClient, sesi: Session) -> None:
    """Mode "pilih semua hasil filter": server yang mengambil id."""
    _siapkan(sesi, jumlah=3)
    semua = klien.post(
        "/anomali/konfirmasi",
        json={"status": "akan_diperbaiki", "semua": True, "kdkab": ["3325"]},
    )
    assert semua.status_code == 200
    assert semua.json()["jumlah"] == 3

    belum = klien.get("/anomali", params={"kdkab": "3325", "status": "belum"}).json()
    assert belum["total"] == 0


def test_minta_klarifikasi_tanpa_ubah_status(
    klien: TestClient, sesi: Session
) -> None:
    """Admin provinsi minta klarifikasi tanpa mengubah status kabupaten/kota."""
    _siapkan(sesi, jumlah=1)
    ids = _ids_anomali(sesi)
    klien.post(
        "/anomali/konfirmasi",
        json={"status": "akan_diperbaiki", "anomali_ids": ids},
    )

    kosong = klien.post(
        "/anomali/konfirmasi/klarifikasi", json={"anomali_ids": ids}
    )
    assert kosong.status_code == 422

    minta = klien.post(
        "/anomali/konfirmasi/klarifikasi",
        json={"anomali_ids": ids, "catatan": "Mohon bukti foto lapangannya"},
    )
    assert minta.status_code == 200
    assert minta.json()["jumlah"] == 1

    data = klien.get("/anomali", params={"kdkab": "3325"}).json()
    konfirmasi = data["baris"][0]["konfirmasi"]
    assert konfirmasi["status"] == "akan_diperbaiki"
    assert konfirmasi["perlu_klarifikasi"] is True
    assert konfirmasi["klarifikasi_catatan"] == "Mohon bukti foto lapangannya"

    # Konfirmasi ulang oleh kabupaten/kota menjawab klarifikasi.
    klien.post(
        "/anomali/konfirmasi",
        json={
            "status": "sesuai_kenyataan",
            "catatan": "titik digeser sesuai batas SLS",
            "anomali_ids": ids,
        },
    )
    data = klien.get("/anomali", params={"kdkab": "3325"}).json()
    konfirmasi = data["baris"][0]["konfirmasi"]
    assert konfirmasi["perlu_klarifikasi"] is False
    assert konfirmasi["klarifikasi_catatan"] is None


def test_xlsx_memuat_kolom_konfirmasi(klien: TestClient, sesi: Session) -> None:
    """Excel pencermatan memuat status/catatan/waktu konfirmasi."""
    _siapkan(sesi, jumlah=1)
    ids = _ids_anomali(sesi)
    klien.post(
        "/anomali/konfirmasi",
        json={"status": "akan_diperbaiki", "anomali_ids": ids},
    )

    from openpyxl import load_workbook

    balasan = klien.get(
        "/anomali.xlsx", params={"kdkab": "3325", "jenis": "hilang"}
    )
    assert balasan.status_code == 200
    buku = load_workbook(io.BytesIO(balasan.content))
    lembar = buku[anomali.LABEL["hilang"][:31]]
    header = [sel.value for sel in next(lembar.iter_rows(max_row=1))]
    for kolom in (
        "status_konfirmasi",
        "catatan_konfirmasi",
        "dikonfirmasi_oleh",
        "waktu_konfirmasi",
    ):
        assert kolom in header
    baris = [sel.value for sel in next(lembar.iter_rows(min_row=2, max_row=2))]
    assert baris[header.index("status_konfirmasi")] == "Akan Diperbaiki"
