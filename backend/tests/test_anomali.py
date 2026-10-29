"""Tes deteksi anomali titik dan rekap berbasis klaim unggahan.

Rekap memakai ``flag_repair`` apa adanya dari berkas B (``flag_repair_unggah``);
menu anomali menjelaskan titik mana yang menurut hitung ulang model masih
bermasalah. Tes di sini menjaga pemisahan itu.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import anomali
from app.anomali import hitung_per_jenis, simpan_anomali
from app.models import (
    DASAR_TUGAS,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    AnomaliTitik,
    RekapTarget,
    Run,
    TitikHasil,
    Wilayah,
)
from app.rekap import simpan_rekap_target

KODE_A = "3325040013001300"
KODE_B = "3325040013000300"


def _wilayah(sesi: Session, kode: str) -> Wilayah:
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


def _run(sesi: Session, tipe: str, *, sumber_a: int | None = None) -> Run:
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
        sumber_run_a_id=sumber_a,
    )
    sesi.add(run)
    sesi.flush()
    return run


def _titik(
    sesi: Session,
    run: Run,
    urut: int,
    assignment: str,
    kode: str | None,
    *,
    flag_model: int,
    flag_unggah: int | None = None,
    unique_bang: str | None = None,
    wilayah: Wilayah | None = None,
) -> None:
    sesi.add(
        TitikHasil(
            run_id=run.id,
            urut=urut,
            assignment_id=assignment,
            unique_bang=unique_bang if unique_bang is not None else f"U{assignment}",
            level_6_full_code=kode,
            wilayah_asal_id=wilayah.id if wilayah is not None else None,
            wilayah_edit_id=wilayah.id if wilayah is not None else None,
            flag_repair_initial=flag_model,
            flag_repair=flag_model,
            flag_repair_unggah=flag_unggah,
            flag_edit_atr_repair=None if run.tipe == TIPE_A else 0,
        )
    )


def _siapkan(sesi: Session) -> tuple[Run, Run]:
    """A dengan tujuh titik + B yang memunculkan semua jenis anomali."""
    w_a = _wilayah(sesi, KODE_A)
    w_b = _wilayah(sesi, KODE_B)

    run_a = _run(sesi, TIPE_A)
    # a1: hilang total (tidak ada di B, unique_bang juga tidak ada)
    _titik(sesi, run_a, 0, "a1", KODE_A, flag_model=1, wilayah=w_a)
    # a2: id berubah di B (unique_bang sama, assignment_id lain)
    _titik(sesi, run_a, 1, "a2", KODE_A, flag_model=1, wilayah=w_a)
    # a3: posisi menyimpang (klaim 0, model 1)
    _titik(sesi, run_a, 2, "a3", KODE_A, flag_model=1, wilayah=w_a)
    # a4: di luar wilayah
    _titik(sesi, run_a, 3, "a4", KODE_A, flag_model=1, wilayah=None)
    # a5: kode SLS berubah tetapi model menganggap beres
    _titik(sesi, run_a, 4, "a5", KODE_A, flag_model=1, wilayah=w_a)
    # a6: beres (klaim 0, model 0) -> tidak masuk anomali
    _titik(sesi, run_a, 5, "a6", KODE_A, flag_model=0, wilayah=w_a)
    # a7: bukan target A, tetapi ditandai model di B (regresi)
    _titik(sesi, run_a, 6, "a7", KODE_A, flag_model=0, wilayah=w_a)
    sesi.flush()

    run_b = _run(sesi, TIPE_B, sumber_a=run_a.id)
    _titik(sesi, run_b, 0, "b2", KODE_A, flag_model=1, flag_unggah=1,
           unique_bang="Ua2", wilayah=w_a)
    _titik(sesi, run_b, 1, "a3", KODE_A, flag_model=1, flag_unggah=0, wilayah=w_a)
    _titik(sesi, run_b, 2, "a4", KODE_A, flag_model=1, flag_unggah=0, wilayah=None)
    _titik(sesi, run_b, 3, "a5", KODE_B, flag_model=0, flag_unggah=0, wilayah=w_b)
    _titik(sesi, run_b, 4, "a6", KODE_A, flag_model=0, flag_unggah=0, wilayah=w_a)
    # regresi: ada di A tetapi bukan target, lalu ditandai model di B
    _titik(sesi, run_b, 5, "a7", KODE_A, flag_model=1, flag_unggah=1, wilayah=w_a)
    # titik baru: tidak ada di A
    _titik(sesi, run_b, 6, "z1", KODE_A, flag_model=1, flag_unggah=1, wilayah=w_a)
    sesi.flush()
    return run_a, run_b


def _jenis(sesi: Session, run_b: Run) -> dict[str, list[AnomaliTitik]]:
    hasil: dict[str, list[AnomaliTitik]] = {}
    for baris in sesi.scalars(
        select(AnomaliTitik).where(AnomaliTitik.run_b_id == run_b.id)
    ):
        hasil.setdefault(baris.jenis, []).append(baris)
    return hasil


def test_simpan_anomali_mengisi_semua_jenis(sesi: Session) -> None:
    """Tiap kondisi menghasilkan kategori anomali yang tepat."""
    run_a, run_b = _siapkan(sesi)

    jumlah = simpan_anomali(sesi, run_b)
    sesi.flush()

    assert jumlah == 7
    assert run_b.anomali_versi == 1
    per_jenis = _jenis(sesi, run_b)
    assert {kode: len(baris) for kode, baris in per_jenis.items()} == {
        "hilang": 1,
        "id_berubah": 1,
        "luar_wilayah": 1,
        "posisi_menyimpang": 1,
        "kode_berubah": 1,
        "regresi": 1,
        "titik_baru": 1,
    }

    hilang = per_jenis["hilang"][0]
    assert hilang.assignment_id == "a1"
    assert hilang.assignment_id_baru is None
    assert hilang.level_6_full_code == KODE_A
    # Tidak ada di Geotag Kabkot: kolom kode Geotag Kabkot kosong.
    assert hilang.level_6_full_code_b is None

    ubah = per_jenis["id_berubah"][0]
    assert ubah.assignment_id == "a2"
    assert ubah.assignment_id_baru == "b2"
    assert ubah.unique_bang == "Ua2"

    kode = per_jenis["kode_berubah"][0]
    assert kode.assignment_id == "a5"
    assert kode.level_6_full_code == KODE_A
    assert kode.level_6_full_code_b == KODE_B

    assert per_jenis["posisi_menyimpang"][0].assignment_id == "a3"
    assert per_jenis["regresi"][0].assignment_id == "a7"
    baru = per_jenis["titik_baru"][0]
    assert baru.assignment_id == "z1"
    # Tidak ada di Master GS: kolom kode Master GS kosong, hanya kode Geotag.
    assert baru.level_6_full_code is None
    assert baru.level_6_full_code_b == KODE_A
    assert hitung_per_jenis(sesi, run_b.id)["hilang"] == 1


def test_titik_baru_memakai_id_lengkap_berkas_a(
    sesi: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Titik sehat di B tidak jadi "baru" hanya karena A sudah dipangkas."""
    w_a = _wilayah(sesi, KODE_A)
    run_a = _run(sesi, TIPE_A)
    # titik_hasil A hanya menyimpan target (flag_repair=1), seperti setelah pangkas
    _titik(sesi, run_a, 0, "a1", KODE_A, flag_model=1, wilayah=w_a)
    sesi.flush()

    run_b = _run(sesi, TIPE_B, sumber_a=run_a.id)
    _titik(sesi, run_b, 0, "a1", KODE_A, flag_model=1, flag_unggah=0, wilayah=w_a)
    _titik(sesi, run_b, 1, "a6", KODE_A, flag_model=0, flag_unggah=0, wilayah=w_a)
    _titik(sesi, run_b, 2, "z1", KODE_A, flag_model=1, flag_unggah=1, wilayah=w_a)
    sesi.flush()

    # berkas A memuat seluruh id, termasuk yang sudah tidak tersimpan di DB
    monkeypatch.setattr(anomali, "_id_a_dari_berkas", lambda run: ["a1", "a6"])
    simpan_anomali(sesi, run_b)
    sesi.flush()

    assert [baris.assignment_id for baris in _jenis(sesi, run_b)["titik_baru"]] == ["z1"]


def test_simpan_anomali_mengganti_anomali_run_b_lama(sesi: Session) -> None:
    """Anomali hanya disimpan untuk run B terakhir per kabupaten/kota."""
    run_a, run_b = _siapkan(sesi)
    simpan_anomali(sesi, run_b)
    sesi.flush()
    lama = sesi.scalar(select(AnomaliTitik).limit(1))
    assert lama is not None
    w_a = sesi.scalar(select(Wilayah).where(Wilayah.idsubsls == KODE_A))

    run_baru = _run(sesi, TIPE_B, sumber_a=run_a.id)
    _titik(sesi, run_baru, 0, "a6", KODE_A, flag_model=0, flag_unggah=0, wilayah=w_a)
    sesi.flush()
    simpan_anomali(sesi, run_baru)
    sesi.flush()

    assert sesi.scalars(
        select(AnomaliTitik).where(AnomaliTitik.run_b_id == run_b.id)
    ).all() == []
    assert sesi.scalars(
        select(AnomaliTitik).where(AnomaliTitik.run_b_id == run_baru.id)
    ).all() != []


def test_rekap_selesai_memakai_klaim_unggahan(sesi: Session) -> None:
    """``selesai`` mengikuti flag unggahan walau model masih menandai titik itu."""
    w_a = _wilayah(sesi, KODE_A)
    run_a = _run(sesi, TIPE_A)
    _titik(sesi, run_a, 0, "a1", KODE_A, flag_model=1, wilayah=w_a)
    _titik(sesi, run_a, 1, "a2", KODE_A, flag_model=1, wilayah=w_a)
    sesi.flush()

    run_b = _run(sesi, TIPE_B, sumber_a=run_a.id)
    # a1 diklaim selesai walau model menandainya; a2 tidak ada di B.
    _titik(sesi, run_b, 0, "a1", KODE_A, flag_model=1, flag_unggah=0, wilayah=w_a)
    sesi.flush()

    simpan_rekap_target(sesi, run_b)
    sesi.flush()

    baris = sesi.scalar(
        select(RekapTarget).where(
            RekapTarget.run_b_id == run_b.id,
            RekapTarget.dasar == DASAR_TUGAS,
        )
    )
    assert baris is not None
    assert baris.target == 2
    assert baris.selesai == 1
    assert baris.hilang == 1


def test_api_anomali_menampilkan_jenis_dan_baris(klien, sesi: Session) -> None:
    """Endpoint ``/anomali`` mengirim ringkasan run, jumlah per jenis, dan baris."""
    run_a, run_b = _siapkan(sesi)
    simpan_anomali(sesi, run_b)
    simpan_rekap_target(sesi, run_b)
    sesi.commit()

    jawab = klien.get("/anomali", params={"kdprov": "33", "kdkab": "3325"})
    assert jawab.status_code == 200
    isi = jawab.json()
    assert isi["run"]["run_id"] == run_b.id
    assert isi["run"]["anomali_versi"] == 1
    jumlah = {satu["kode"]: satu["jumlah"] for satu in isi["jenis"]}
    assert jumlah["hilang"] == 1
    assert jumlah["id_berubah"] == 1
    assert isi["total"] == 7

    jawab = klien.get(
        "/anomali", params={"kdprov": "33", "kdkab": "3325", "jenis": "hilang"}
    )
    assert jawab.status_code == 200
    isi = jawab.json()
    assert isi["total"] == 1
    assert isi["baris"][0]["assignment_id"] == "a1"
    assert "tidak ada" in isi["baris"][0]["keterangan"]


def test_api_anomali_kabupaten_tanpa_run_b(klien) -> None:
    """Wilayah yang belum pernah sukses Proses B mengembalikan daftar kosong."""
    jawab = klien.get("/anomali", params={"kdprov": "33", "kdkab": "3399"})
    assert jawab.status_code == 200
    isi = jawab.json()
    assert isi["run"] is None
    assert isi["runs"] == []
    assert isi["total"] == 0
    assert isi["baris"] == []
    assert len(isi["jenis"]) == 7
    assert all(satu["jumlah"] == 0 for satu in isi["jenis"])


def test_api_anomali_banyak_kabupaten_dan_jenis(klien, sesi: Session) -> None:
    """Filter boleh memilih banyak kabupaten/kota dan banyak jenis sekaligus."""
    _, run_b = _siapkan(sesi)
    simpan_anomali(sesi, run_b)

    # Kabupaten lain dengan satu anomali "hilang" saja.
    run_lain = Run(
        tipe=TIPE_B,
        kdprov="33",
        kdkab="3326",
        user="uji",
        status=STATUS_SUKSES,
        nama_file_input="lain.geojson",
        nama_file_peta="peta.geojson",
        berkas_input="/tmp/lain.geojson",
        berkas_peta="/tmp/peta.geojson",
        jumlah_baris=0,
        detail_tersedia=1,
    )
    sesi.add(run_lain)
    sesi.flush()
    sesi.add(
        AnomaliTitik(
            run_b_id=run_lain.id,
            jenis="hilang",
            assignment_id="z1",
            level_6_full_code="3326010001000100",
        )
    )
    sesi.commit()

    jawab = klien.get(
        "/anomali",
        params=[
            ("kdprov", "33"),
            ("kdkab", "3325"),
            ("kdkab", "3326"),
            ("jenis", "hilang"),
        ],
    )
    assert jawab.status_code == 200
    isi = jawab.json()
    assert isi["run"] is None
    assert {satu["kdkab"] for satu in isi["runs"]} == {"3325", "3326"}
    assert isi["total"] == 2
    assert {baris["kdkab"] for baris in isi["baris"]} == {"3325", "3326"}
    assert all(baris["jenis"] == "hilang" for baris in isi["baris"])
    jumlah = {satu["kode"]: satu["jumlah"] for satu in isi["jenis"]}
    assert jumlah["hilang"] == 2
    assert jumlah["titik_baru"] == 1


def test_ekspor_anomali_xlsx_satu_jenis(klien, sesi: Session) -> None:
    """Excel anomali memuat jenis yang dipilih; tanpa jenis memuat semua lembar."""
    run_a, run_b = _siapkan(sesi)
    simpan_anomali(sesi, run_b)
    sesi.commit()

    jawab = klien.get(
        "/anomali.xlsx",
        params={"kdprov": "33", "kdkab": "3325", "jenis": "hilang"},
    )
    assert jawab.status_code == 200
    assert jawab.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert jawab.content[:2] == b"PK"
    assert "anomali_hilang" in jawab.headers["content-disposition"]

    tanpa_jenis = klien.get(
        "/anomali.xlsx", params={"kdprov": "33", "kdkab": "3325"}
    )
    assert tanpa_jenis.status_code == 200
    assert "anomali_semua" in tanpa_jenis.headers["content-disposition"]


def test_bersihkan_hasil_membuang_anomali_dan_penanda(sesi: Session) -> None:
    """Run yang diproses ulang tidak menyisakan anomali lama (versi direset)."""
    from app.worker import bersihkan_hasil

    run_a, run_b = _siapkan(sesi)
    simpan_anomali(sesi, run_b)
    sesi.flush()
    assert run_b.anomali_versi == 1

    bersihkan_hasil(sesi, run_b.id)
    sesi.flush()
    sesi.refresh(run_b)

    assert run_b.anomali_versi == 0
    assert (
        sesi.scalars(
            select(AnomaliTitik).where(AnomaliTitik.run_b_id == run_b.id)
        ).all()
        == []
    )
