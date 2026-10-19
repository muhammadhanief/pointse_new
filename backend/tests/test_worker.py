"""Tes worker Proses A/B: klaim job, batch penyimpanan, dimensi wilayah, rekap."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app import worker as modul_worker
from app.config import Settings
from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    STATUS_DIGANTIKAN,
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    RekapSubsls,
    Run,
    TitikHasil,
    Wilayah,
)
from app.worker import UKURAN_BATCH, klaim_job, kueri_klaim, mulai_worker, proses_satu_job

BARIS_A = (
    data_kecil.baris_titik_a("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_a("2", "A1", 0.3, 0.3),
    data_kecil.baris_titik_a("3", "A1", 0.5, 2.5),
)

# Masukan Proses B: satu titik apa adanya, satu digeser pindah SubSLS, satu
# digeser tapi atribut flag_repair-nya sudah diubah manual.
BARIS_B = (
    data_kecil.baris_titik_b("1", "A1", 0.2, 0.2),
    data_kecil.baris_titik_b("2", "A1", 0.3, 0.3, latitude=0.9, longitude=2.5),
    data_kecil.baris_titik_b("3", "A1", 0.4, 0.4, flag_repair_initial=1, flag_repair=0),
)


def buat_job(
    sesi: Session,
    tmp_path: Path,
    *,
    tipe: str = TIPE_A,
    kdkab: str = "3307",
    nama: str = "job",
    baris: tuple[dict[str, Any], ...] | None = None,
) -> Run:
    """Tulis berkas masukan kecil lalu buat baris ``runs`` berstatus menunggu."""
    dasar = tmp_path / nama
    if tipe == TIPE_A:
        titik = data_kecil.tulis(data_kecil.titik_a(*(baris or BARIS_A)), dasar / "titik.geojson")
    else:
        titik = data_kecil.tulis(data_kecil.titik_b(*(baris or BARIS_B)), dasar / "titik.geojson")
    peta = data_kecil.tulis(data_kecil.peta(), dasar / "peta.geojson")

    run = Run(
        tipe=tipe,
        kdkab=kdkab,
        status=STATUS_MENUNGGU,
        nama_file_input=titik.name,
        nama_file_peta=peta.name,
        berkas_input=str(titik),
        berkas_peta=str(peta),
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)
    return run


def baris_hasil(sesi: Session, run_id: int) -> list[TitikHasil]:
    """Ambil baris hasil satu job, urut sesuai keluaran proses."""
    return list(
        sesi.scalars(
            select(TitikHasil).where(TitikHasil.run_id == run_id).order_by(TitikHasil.urut)
        )
    )


def kode_wilayah(sesi: Session, wilayah_id: int | None) -> str | None:
    """Kode ``idsubsls`` dari satu id wilayah (None kalau id-nya NULL)."""
    if wilayah_id is None:
        return None
    return sesi.scalar(select(Wilayah.idsubsls).where(Wilayah.id == wilayah_id))


def rekap(
    sesi: Session, run_id: int, dasar: str
) -> dict[str | None, tuple[int, int, int, int, int]]:
    """Rekap satu dasar: ``idsubsls -> (jumlah, belum, sudah_posisi, sudah_manual, tanpa_wilayah)``.

    Kunci ``None`` = baris kategori terpisah "(tanpa wilayah)" (``wilayah_id`` NULL).
    """
    baris = sesi.execute(
        select(
            Wilayah.idsubsls,
            RekapSubsls.jumlah,
            RekapSubsls.belum,
            RekapSubsls.sudah_posisi,
            RekapSubsls.sudah_manual,
            RekapSubsls.tanpa_wilayah,
        )
        .select_from(RekapSubsls)
        .outerjoin(Wilayah, Wilayah.id == RekapSubsls.wilayah_id)
        .where(RekapSubsls.run_id == run_id, RekapSubsls.dasar == dasar)
    ).all()
    return {
        kode: (jumlah, belum, posisi, manual, tanpa)
        for kode, jumlah, belum, posisi, manual, tanpa in baris
    }


def total_rekap(sesi: Session, run_id: int, dasar: str) -> int:
    """Jumlah titik pada satu dasar rekap (termasuk baris "(tanpa wilayah)")."""
    return sum(satu[0] for satu in rekap(sesi, run_id, dasar).values())


def test_ukuran_batch_penyimpanan_sepuluh_ribu() -> None:
    """Hasil disimpan per batch 10.000 baris (PRD §8)."""
    assert UKURAN_BATCH == 10_000


def test_kueri_klaim_mysql_memakai_skip_locked() -> None:
    """Kueri klaim memakai FOR UPDATE SKIP LOCKED dan menyaring status/kdkab."""
    sql = " ".join(str(kueri_klaim().compile(dialect=mysql.dialect())).split())

    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "runs.status" in sql
    assert "NOT (EXISTS" in sql


def test_proses_a_menyimpan_hasil_dan_status_sukses(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Worker Proses A: status sukses, jumlah baris, dan isi hasil benar."""
    job = buat_job(sesi, tmp_path)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True

    sesi.refresh(job)
    assert job.status == STATUS_SUKSES, job.pesan
    assert job.jumlah_baris == 3
    assert job.jumlah_tanpa_wilayah == 0
    assert job.started_at is not None and job.finished_at is not None

    hasil = baris_hasil(sesi, job.id)
    assert [baris.assignment_id for baris in hasil] == ["1", "2", "3"]
    assert [baris.urut for baris in hasil] == [0, 1, 2]

    pertama = hasil[0]
    assert pertama.level_6_full_code == "A1"
    assert kode_wilayah(sesi, pertama.wilayah_asal_id) == "A1"
    assert pertama.flag_repair == 0 and pertama.flag_repair_initial == 0
    assert pertama.latitude_origin == 0.2 and pertama.longitude_origin == 0.2
    assert pertama.kk == 1 and pertama.btt == 1 and pertama.bku == 0
    assert pertama.usaha == 0
    # kolom khusus Proses B tetap kosong untuk job Proses A
    assert pertama.flag_position is None and pertama.latitude_edited is None
    assert pertama.wilayah_edit_id is None

    ketiga = hasil[2]
    assert kode_wilayah(sesi, ketiga.wilayah_asal_id) == "A2"
    assert ketiga.flag_repair == 1


def test_dimensi_wilayah_diisi_dari_peta(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Peta yang diproses mengisi tabel ``wilayah`` (kode + nama, tanpa duplikat)."""
    job = buat_job(sesi, tmp_path)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    wilayah = {
        satu.idsubsls: satu for satu in sesi.scalars(select(Wilayah).order_by(Wilayah.idsubsls))
    }
    assert set(wilayah) == {"A1", "A2"}
    assert wilayah["A1"].nmsls == "SLS 001"
    assert wilayah["A1"].nmdesa == "KALIBEBER"
    assert wilayah["A2"].nmdesa == "KALIBEBER"
    assert wilayah["A2"].kdkab == "3307"


def test_rekap_subsls_diisi_dua_dasar(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Rekap per SubSLS disimpan untuk dasar ``tugas`` dan ``posisi``.

    Dasar ``tugas`` memakai ``level_6_full_code`` (ketiga titik ditugaskan di A1),
    dasar ``posisi`` memakai hasil join peta (dua titik di A1, satu di A2). Proses A
    tidak punya ``flag_edit_atr_repair``, jadi titik yang sudah diperbaiki masuk
    ``sudah_posisi`` (NULL dianggap 0).
    """
    job = buat_job(sesi, tmp_path)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    assert rekap(sesi, job.id, DASAR_TUGAS) == {"A1": (3, 1, 2, 0, 0)}
    assert rekap(sesi, job.id, DASAR_POSISI) == {
        "A1": (2, 0, 2, 0, 0),
        "A2": (1, 1, 0, 0, 0),
    }
    # jumlah tiap dasar harus utuh (PRD §5: indikator progres per wilayah).
    assert total_rekap(sesi, job.id, DASAR_TUGAS) == job.jumlah_baris == 3
    assert total_rekap(sesi, job.id, DASAR_POSISI) == job.jumlah_baris == 3


def test_rekap_basis_posisi_memakai_wilayah_hasil_edit(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Proses B: dasar ``posisi`` mengikuti wilayah hasil edit, ``tugas`` tetap awal.

    Tiga titik: satu apa adanya (``sudah_posisi``), satu digeser pindah SubSLS
    (``belum``), satu ``flag_repair``-nya diubah manual (``sudah_manual``).
    """
    job = buat_job(sesi, tmp_path, tipe=TIPE_B)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    assert rekap(sesi, job.id, DASAR_TUGAS) == {"A1": (3, 1, 1, 1, 0)}
    assert rekap(sesi, job.id, DASAR_POSISI) == {
        "A1": (2, 0, 1, 1, 0),
        "A2": (1, 1, 0, 0, 0),
    }
    assert total_rekap(sesi, job.id, DASAR_POSISI) == job.jumlah_baris == 3


def test_rekap_memisahkan_sudah_posisi_dan_sudah_manual(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Kolom ``sudah_posisi`` dan ``sudah_manual`` dihitung terpisah (PRD §5)."""
    job = buat_job(sesi, tmp_path, tipe=TIPE_B)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    jumlah, belum, sudah_posisi, sudah_manual, tanpa = rekap(
        sesi, job.id, DASAR_TUGAS
    )["A1"]
    assert (jumlah, belum) == (3, 1)
    # titik 1: flag_repair 0 & flag_edit_atr_repair 0; titik 3: flag_repair 0 &
    # flag_edit_atr_repair 1 (atribut diperbaiki manual).
    assert (sudah_posisi, sudah_manual) == (1, 1)
    assert tanpa == 0


def test_titik_di_luar_peta_dihitung_tanpa_wilayah(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Titik di luar semua poligon: wilayah NULL, masuk kategori "(tanpa wilayah)".

    Titik itu tetap punya wilayah **tugas** (``level_6_full_code`` = A1), jadi pada
    dasar ``tugas`` ia ikut baris A1 dan tercatat di kolom ``tanpa_wilayah``; pada
    dasar ``posisi`` ia tidak punya wilayah sama sekali, jadi dihitung pada baris
    kategori ``wilayah_id`` NULL. Jumlah tiap dasar tetap sama dengan jumlah baris.
    """
    baris = (*BARIS_A, data_kecil.baris_titik_a("4", "A1", 5.0, 5.0))
    job = buat_job(sesi, tmp_path, baris=baris)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    assert job.jumlah_baris == 4
    assert job.jumlah_tanpa_wilayah == 1
    hasil = {satu.assignment_id: satu for satu in baris_hasil(sesi, job.id)}
    assert hasil["4"].wilayah_asal_id is None

    # dasar tugas: titik 4 ada di A1 (penugasan), tetapi tanpa wilayah posisi
    assert rekap(sesi, job.id, DASAR_TUGAS) == {"A1": (4, 2, 2, 0, 1)}
    # dasar posisi: baris kategori "(tanpa wilayah)" (kunci None)
    assert rekap(sesi, job.id, DASAR_POSISI) == {
        "A1": (2, 0, 2, 0, 0),
        "A2": (1, 1, 0, 0, 0),
        None: (1, 1, 0, 0, 1),
    }
    assert total_rekap(sesi, job.id, DASAR_TUGAS) == job.jumlah_baris == 4
    assert total_rekap(sesi, job.id, DASAR_POSISI) == job.jumlah_baris == 4


def test_kode_subsls_tak_ada_di_peta_masuk_kategori_tanpa_wilayah(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``level_6_full_code`` di luar peta: tidak ada baris ``wilayah`` baru, FK aman.

    SubSLS tugas yang tidak ada di peta tidak dibuatkan baris dimensi seadanya,
    jadi titiknya dihitung pada kategori "(tanpa wilayah)" dasar ``tugas``
    (``wilayah_id`` NULL) dan tidak menggagalkan penyimpanan.
    """
    baris = (
        data_kecil.baris_titik_a("1", "A9", 0.2, 0.2),
        data_kecil.baris_titik_a("2", None, 0.3, 0.3),
    )
    job = buat_job(sesi, tmp_path, baris=baris)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.refresh(job)
    assert job.status == STATUS_SUKSES, job.pesan

    wilayah = {satu.idsubsls for satu in sesi.scalars(select(Wilayah))}
    assert wilayah == {"A1", "A2"}, "kode di luar peta tidak boleh dibuatkan baris"

    # titik 1: level_6 "A9" (tak ada di peta), titik 2: level_6 kosong; keduanya
    # jatuh di A1 dan flag_repair-nya 1 (A1 != level_6)
    assert rekap(sesi, job.id, DASAR_TUGAS) == {None: (2, 2, 0, 0, 0)}
    # dasar posisi: keduanya masuk poligon A1
    assert rekap(sesi, job.id, DASAR_POSISI) == {"A1": (2, 2, 0, 0, 0)}
    assert total_rekap(sesi, job.id, DASAR_TUGAS) == job.jumlah_baris == 2


def test_proses_b_menghitung_flag_penggeseran(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Worker Proses B: flag_position, flag_edit_atr_repair, dan SubSLS hasil edit."""
    job = buat_job(sesi, tmp_path, tipe=TIPE_B)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.refresh(job)
    assert job.status == STATUS_SUKSES, job.pesan

    hasil = {baris.assignment_id: baris for baris in baris_hasil(sesi, job.id)}
    assert set(hasil) == {"1", "2", "3"}

    apa_adanya = hasil["1"]
    assert apa_adanya.flag_position == 0
    assert apa_adanya.flag_edit_atr_repair == 0
    assert apa_adanya.flag_repair_initial == 0
    assert apa_adanya.flag_repair == 0
    assert kode_wilayah(sesi, apa_adanya.wilayah_edit_id) == "A1"

    digeser = hasil["2"]
    assert digeser.flag_position == 1
    assert digeser.latitude_edited == 0.9
    assert digeser.longitude_edited == 2.5
    assert kode_wilayah(sesi, digeser.wilayah_edit_id) == "A2"
    assert digeser.flag_repair_initial == 1
    assert digeser.flag_repair == 1
    assert digeser.flag_edit_atr_repair == 0

    diedit_manual = hasil["3"]
    assert diedit_manual.flag_edit_atr_repair == 1
    assert diedit_manual.flag_position == 0
    assert diedit_manual.flag_repair == 0


def test_job_gagal_kalau_berkas_hilang(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Berkas masukan hilang: status gagal, pesan dicatat, hasil & rekap dibersihkan."""
    job = buat_job(sesi, tmp_path)
    Path(job.berkas_input).unlink()
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True

    sesi.refresh(job)
    assert job.status == STATUS_GAGAL
    assert job.pesan, "pesan galat harus dicatat di runs.pesan"
    assert job.finished_at is not None
    assert baris_hasil(sesi, job.id) == []
    assert sesi.scalars(select(RekapSubsls).where(RekapSubsls.run_id == job.id)).all() == []


def test_penyimpanan_memakai_batch(
    sesi: Session,
    sesi_pabrik: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Hasil yang lebih banyak dari ukuran batch tetap tersimpan lengkap."""
    baris = tuple(
        data_kecil.baris_titik_a(str(nomor), "A1", 0.1 + nomor / 100, 0.5)
        for nomor in range(1, 6)
    )
    monkeypatch.setattr(modul_worker, "UKURAN_BATCH", 2)
    job = buat_job(sesi, tmp_path, baris=baris)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True

    sesi.refresh(job)
    assert job.jumlah_baris == 5
    hasil = baris_hasil(sesi, job.id)
    assert len(hasil) == 5
    assert [satu.urut for satu in hasil] == [0, 1, 2, 3, 4]


def test_job_antre_lama_digantikan_saat_klaim(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Job terbaru untuk (kdkab, tipe) yang dikerjakan; job antre lama dibatalkan."""
    lama = buat_job(sesi, tmp_path, nama="lama")
    id_lama, id_baru = lama.id, buat_job(sesi, tmp_path, nama="baru").id
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    # job terbaru (id lebih besar) yang jalan dan hasilnya tersimpan
    assert sesi.get(Run, id_baru).status == STATUS_SUKSES
    assert len(baris_hasil(sesi, id_baru)) == 3
    # job antre yang lama ditandai digantikan, tanpa hasil
    assert sesi.get(Run, id_lama).status == STATUS_DIGANTIKAN
    assert baris_hasil(sesi, id_lama) == []
    # tidak ada job menunggu lagi
    assert proses_satu_job(sesi_pabrik) is False


def test_hasil_job_lama_digantikan_oleh_job_baru(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Job baru untuk kabupaten/tipe sama menggantikan hasil titik job lama.

    Yang dihapus hanya isi ``titik_hasil``: baris ``runs`` dan snapshot
    ``rekap_subsls`` job lama tetap ada supaya riwayat rekap tidak hilang.
    """
    lama = buat_job(sesi, tmp_path, nama="lama")
    sesi.rollback()
    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()
    rekap_lama = rekap(sesi, lama.id, DASAR_TUGAS)
    assert rekap_lama == {"A1": (3, 1, 2, 0, 0)}

    baru = buat_job(sesi, tmp_path, nama="baru")
    sesi.rollback()
    assert proses_satu_job(sesi_pabrik) is True

    sesi.expire_all()
    assert sesi.get(Run, baru.id).status == STATUS_SUKSES
    assert sesi.get(Run, lama.id) is not None, "baris runs job lama harus tetap ada"
    assert sesi.get(Run, lama.id).status == STATUS_DIGANTIKAN
    assert baris_hasil(sesi, lama.id) == []
    assert len(baris_hasil(sesi, baru.id)) == 3
    assert rekap(sesi, lama.id, DASAR_TUGAS) == rekap_lama, "snapshot rekap job lama tetap ada"
    assert rekap(sesi, baru.id, DASAR_TUGAS) == {"A1": (3, 1, 2, 0, 0)}


def test_klaim_melewati_job_yang_sedang_jalan(sesi: Session, tmp_path: Path) -> None:
    """Job dengan (kdkab, tipe) yang sedang jalan tidak diambil lagi."""
    sedang = buat_job(sesi, tmp_path, nama="sedang", kdkab="3307")
    sedang.status = STATUS_JALAN
    lain_kabupaten = buat_job(sesi, tmp_path, nama="lain", kdkab="3308")
    sesi.commit()

    diambil = klaim_job(sesi)
    assert diambil is not None and diambil.id == lain_kabupaten.id
    assert diambil.status == STATUS_JALAN


def test_klaim_tidak_ada_job(
    sesi: Session, sesi_pabrik: sessionmaker[Session]
) -> None:
    """Tanpa job antre, klaim mengembalikan None dan ``proses_satu_job`` False."""
    assert klaim_job(sesi) is None
    assert proses_satu_job(sesi_pabrik) is False


def test_mulai_worker_membuat_thread_sesuai_max_workers(
    sesi_pabrik: sessionmaker[Session], setelan: Settings, monkeypatch: Any
) -> None:
    """MAX_WORKERS menentukan jumlah thread worker yang dinyalakan."""
    monkeypatch.setattr(modul_worker, "get_sessionmaker", lambda: sesi_pabrik)
    setelan = setelan.model_copy(update={"max_workers": 2, "interval_polling": 0.05})

    benang, penghenti = mulai_worker(setelan)
    try:
        assert len(benang) == 2
        assert all(satu.is_alive() for satu in benang)
    finally:
        penghenti.set()
        for satu in benang:
            satu.join(timeout=5)

    assert not any(satu.is_alive() for satu in benang)
