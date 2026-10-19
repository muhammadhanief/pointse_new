"""Tes worker Proses A/B: klaim job, batch penyimpanan, dimensi wilayah, rekap."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session, sessionmaker

import data_kecil
from app import worker as modul_worker
from app.config import Settings
from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    KOLOM_HITUNGAN,
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    RekapDesa,
    RekapKabupaten,
    Run,
    TitikHasil,
    Wilayah,
)
from app.worker import UKURAN_BATCH, klaim_job, kueri_klaim, mulai_worker, proses_satu_job

# Kode desa tiap SubSLS pada data uji (lihat ``data_kecil.DESA``).
DESA_A1 = data_kecil.DESA["A1"]["kddesa"]
DESA_A2 = data_kecil.DESA["A2"]["kddesa"]

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


class Hitungan(NamedTuple):
    """Hitungan satu baris rekap (PRD §5); kolom yang tidak disebut bernilai 0."""

    jumlah: int = 0
    belum: int = 0
    ditindak_benar: int = 0
    ditindak_salah: int = 0
    benar_awal: int = 0
    digeser: int = 0
    tanpa_wilayah: int = 0


# Nama kolom rekap -> nama field :class:`Hitungan`.
KOLOM_KE_FIELD: dict[str, str] = {
    "jumlah": "jumlah",
    "belum": "belum",
    "benar_awal": "benar_awal",
    "ditindak_posisi_benar": "ditindak_benar",
    "ditindak_posisi_salah": "ditindak_salah",
    "digeser": "digeser",
    "tanpa_wilayah": "tanpa_wilayah",
}


def buat_job(
    sesi: Session,
    tmp_path: Path,
    *,
    tipe: str = TIPE_A,
    kdprov: str = "33",
    kdkab: str = "3307",
    nama: str = "job",
    baris: tuple[dict[str, Any], ...] | None = None,
    akar: Path | None = None,
) -> Run:
    """Tulis berkas masukan kecil lalu buat baris ``runs`` berstatus menunggu."""
    dasar = (akar or tmp_path) / nama
    if tipe == TIPE_A:
        titik = data_kecil.tulis(data_kecil.titik_a(*(baris or BARIS_A)), dasar / "titik.geojson")
    else:
        titik = data_kecil.tulis(data_kecil.titik_b(*(baris or BARIS_B)), dasar / "titik.geojson")
    peta = data_kecil.tulis(data_kecil.peta(), dasar / "peta.geojson")

    run = Run(
        tipe=tipe,
        kdprov=kdprov,
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


def ids_job(sesi: Session, tmp_path: Path, jumlah: int, *, akar: Path | None = None) -> list[int]:
    """Buat beberapa job berurutan (id menanjak) dan kembalikan id-nya."""
    return [
        buat_job(sesi, tmp_path, nama=f"job{nomor}", akar=akar).id for nomor in range(jumlah)
    ]


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


def _hitungan(baris: Mapping[str, Any]) -> Hitungan:
    """Ubah satu baris rekap jadi :class:`Hitungan`."""
    return Hitungan(
        jumlah=int(baris["jumlah"]),
        belum=int(baris["belum"]),
        benar_awal=int(baris["benar_awal"]),
        ditindak_benar=int(baris["ditindak_posisi_benar"]),
        ditindak_salah=int(baris["ditindak_posisi_salah"]),
        digeser=int(baris["digeser"]),
        tanpa_wilayah=int(baris["tanpa_wilayah"]),
    )


def rekap_desa(sesi: Session, run_id: int, dasar: str) -> dict[str | None, Hitungan]:
    """Rekap satu dasar dari ``rekap_desa``: ``kddesa -> Hitungan``.

    Kunci ``None`` = baris kategori terpisah "(tanpa wilayah)" (kode desa NULL).
    """
    baris = sesi.execute(
        select(RekapDesa.kddesa, *[getattr(RekapDesa, nama) for nama in KOLOM_HITUNGAN]).where(
            RekapDesa.run_id == run_id, RekapDesa.dasar == dasar
        )
    ).mappings()
    return {
        (None if satu["kddesa"] is None else str(satu["kddesa"])): _hitungan(satu)
        for satu in baris
    }


def rekap_kabupaten(sesi: Session, run_id: int, dasar: str) -> Hitungan:
    """Rekap kabupaten/kota satu dasar (satu baris)."""
    baris = (
        sesi.execute(
            select(*[getattr(RekapKabupaten, nama) for nama in KOLOM_HITUNGAN]).where(
                RekapKabupaten.run_id == run_id, RekapKabupaten.dasar == dasar
            )
        )
        .mappings()
        .one()
    )
    return _hitungan(baris)


def total_rekap(sesi: Session, run_id: int, dasar: str) -> int:
    """Jumlah titik pada satu dasar rekap (termasuk baris "(tanpa wilayah)")."""
    return sum(satu.jumlah for satu in rekap_desa(sesi, run_id, dasar).values())


def test_ukuran_batch_penyimpanan_sepuluh_ribu() -> None:
    """Hasil disimpan per batch 10.000 baris (PRD §8)."""
    assert UKURAN_BATCH == 10_000


def test_kueri_klaim_mysql_memakai_skip_locked() -> None:
    """Kueri klaim: FOR UPDATE SKIP LOCKED, saring status/kabupaten, urut FIFO."""
    sql = " ".join(str(kueri_klaim().compile(dialect=mysql.dialect())).split())

    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "runs.status" in sql
    assert "NOT (EXISTS" in sql
    # job antre lama dikerjakan lebih dulu (bukan digantikan job terbaru)
    assert "ORDER BY runs.id LIMIT" in sql


def test_proses_a_menyimpan_hasil_dan_status_sukses(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Worker Proses A: status sukses, jumlah baris, dan isi hasil benar.

    Yang tersimpan hanya titik yang perlu perhatian (titik 3: ``flag_repair`` = 1);
    titik ``benar_awal`` (1 dan 2) hanya terhitung di rekap.
    """
    job = buat_job(sesi, tmp_path)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True

    sesi.refresh(job)
    assert job.status == STATUS_SUKSES, job.pesan
    assert job.jumlah_baris == 3
    assert job.jumlah_tanpa_wilayah == 0
    assert job.detail_tersedia == 1
    assert job.started_at is not None and job.finished_at is not None

    hasil = baris_hasil(sesi, job.id)
    assert [baris.assignment_id for baris in hasil] == ["3"]
    assert [baris.urut for baris in hasil] == [2]

    tersimpan = hasil[0]
    assert tersimpan.level_6_full_code == "A1"
    assert kode_wilayah(sesi, tersimpan.wilayah_asal_id) == "A2"
    assert tersimpan.flag_repair == 1 and tersimpan.flag_repair_initial == 1
    assert tersimpan.latitude_origin == 0.5 and tersimpan.longitude_origin == 2.5
    assert tersimpan.kk == 1 and tersimpan.btt == 1 and tersimpan.bku == 0
    assert tersimpan.usaha == 0
    # kolom khusus Proses B tetap kosong untuk job Proses A
    assert tersimpan.flag_position is None and tersimpan.latitude_edited is None
    assert tersimpan.wilayah_edit_id is None


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
    assert wilayah["A2"].nmdesa == "MOJOTENGAH"
    assert wilayah["A2"].kdkab == "3307"


def test_rekap_desa_diisi_dua_dasar(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Rekap per desa disimpan untuk dasar ``tugas`` dan ``posisi``.

    Dasar ``tugas`` memakai ``level_6_full_code`` (ketiga titik ditugaskan di A1,
    jadi semua masuk desa A1), dasar ``posisi`` memakai hasil join peta (dua titik di
    A1, satu di A2). Proses A tidak punya ``flag_edit_atr_repair`` dan
    ``flag_position``, jadi titik ``flag_repair`` = 0 masuk ``benar_awal`` dan
    ``digeser`` tetap 0.
    """
    job = buat_job(sesi, tmp_path)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    assert rekap_desa(sesi, job.id, DASAR_TUGAS) == {
        DESA_A1: Hitungan(jumlah=3, belum=1, benar_awal=2)
    }
    assert rekap_desa(sesi, job.id, DASAR_POSISI) == {
        DESA_A1: Hitungan(jumlah=2, benar_awal=2),
        DESA_A2: Hitungan(jumlah=1, belum=1),
    }
    # jumlah tiap dasar harus utuh (PRD §5: indikator progres per wilayah).
    assert total_rekap(sesi, job.id, DASAR_TUGAS) == job.jumlah_baris == 3
    assert total_rekap(sesi, job.id, DASAR_POSISI) == job.jumlah_baris == 3


def test_rekap_kabupaten_jumlah_rekap_desa(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``rekap_kabupaten`` = jumlah ``rekap_desa`` untuk kedua dasar (PRD §7)."""
    job = buat_job(sesi, tmp_path, tipe=TIPE_B)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    for dasar in (DASAR_TUGAS, DASAR_POSISI):
        kabupaten = rekap_kabupaten(sesi, job.id, dasar)
        desa = rekap_desa(sesi, job.id, dasar)
        for kolom in KOLOM_HITUNGAN:
            field = KOLOM_KE_FIELD[kolom]
            assert getattr(kabupaten, field) == sum(
                getattr(satu, field) for satu in desa.values()
            ), f"kolom {kolom} dasar {dasar} tidak cocok"


def test_rekap_basis_posisi_memakai_wilayah_hasil_edit(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Proses B: dasar ``posisi`` mengikuti wilayah hasil edit, ``tugas`` tetap awal.

    Tiga titik: satu apa adanya (``benar_awal``), satu digeser pindah SubSLS
    (``belum`` + ``digeser``), satu ``flag_repair``-nya diubah manual sehingga
    posisinya benar (``ditindak_posisi_benar``).
    """
    job = buat_job(sesi, tmp_path, tipe=TIPE_B)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    assert rekap_desa(sesi, job.id, DASAR_TUGAS) == {
        DESA_A1: Hitungan(jumlah=3, belum=1, ditindak_benar=1, benar_awal=1, digeser=1)
    }
    assert rekap_desa(sesi, job.id, DASAR_POSISI) == {
        DESA_A1: Hitungan(jumlah=2, ditindak_benar=1, benar_awal=1),
        DESA_A2: Hitungan(jumlah=1, belum=1, digeser=1),
    }
    assert total_rekap(sesi, job.id, DASAR_POSISI) == job.jumlah_baris == 3


def test_rekap_memisahkan_benar_awal_dan_tindakan(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``benar_awal`` dan ``ditindak_posisi_benar`` dihitung terpisah (PRD §5)."""
    job = buat_job(sesi, tmp_path, tipe=TIPE_B)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    hasil = rekap_desa(sesi, job.id, DASAR_TUGAS)[DESA_A1]
    # titik 1: flag_repair 0 & flag_edit_atr_repair 0 (tanpa tindakan manual);
    # titik 3: flag_repair 0, flag_edit_atr_repair 1, flag_repair_initial 0
    # (ditindak manual dan posisinya sudah di SubSLS tugasnya).
    assert hasil == Hitungan(jumlah=3, belum=1, ditindak_benar=1, benar_awal=1, digeser=1)


def test_rekap_ditindak_tapi_posisi_masih_salah(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``ditindak_posisi_salah``: atribut ditindak manual tetapi posisi masih salah.

    Titik 2 digeser ke A2 dengan ``flag_repair`` sudah diubah manual (0), jadi
    ``flag_edit_atr_repair`` = 1 sementara ``flag_repair_initial`` hasil join baru
    tetap 1 (SubSLS hasil join != SubSLS tugas).
    """
    baris = (
        data_kecil.baris_titik_b("1", "A1", 0.2, 0.2),
        data_kecil.baris_titik_b(
            "2", "A1", 0.3, 0.3, latitude=0.4, longitude=2.4,
            flag_repair_initial=1, flag_repair=0,
        ),
    )
    job = buat_job(sesi, tmp_path, tipe=TIPE_B, baris=baris)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    hasil = {satu.assignment_id: satu for satu in baris_hasil(sesi, job.id)}["2"]
    assert hasil.flag_edit_atr_repair == 1
    assert hasil.flag_repair_initial == 1
    assert hasil.flag_repair == 0
    assert hasil.flag_position == 1

    assert rekap_desa(sesi, job.id, DASAR_TUGAS) == {
        DESA_A1: Hitungan(jumlah=2, ditindak_salah=1, benar_awal=1, digeser=1)
    }
    # dasar posisi: titik 1 di A1, titik 2 (digeser) di A2
    assert rekap_desa(sesi, job.id, DASAR_POSISI) == {
        DESA_A1: Hitungan(jumlah=1, benar_awal=1),
        DESA_A2: Hitungan(jumlah=1, ditindak_salah=1, digeser=1),
    }


def test_titik_di_luar_peta_dihitung_tanpa_wilayah(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Titik di luar semua poligon: wilayah NULL, masuk kategori "(tanpa wilayah)".

    Titik itu tetap punya wilayah **tugas** (``level_6_full_code`` = A1), jadi pada
    dasar ``tugas`` ia ikut baris desa A1 dan tercatat di kolom ``tanpa_wilayah``;
    pada dasar ``posisi`` ia tidak punya wilayah sama sekali, jadi dihitung pada baris
    kategori berkode NULL. Jumlah tiap dasar tetap sama dengan jumlah baris.
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
    assert rekap_desa(sesi, job.id, DASAR_TUGAS) == {
        DESA_A1: Hitungan(jumlah=4, belum=2, benar_awal=2, tanpa_wilayah=1)
    }
    # dasar posisi: baris kategori "(tanpa wilayah)" (kunci None)
    assert rekap_desa(sesi, job.id, DASAR_POSISI) == {
        DESA_A1: Hitungan(jumlah=2, benar_awal=2),
        DESA_A2: Hitungan(jumlah=1, belum=1),
        None: Hitungan(jumlah=1, belum=1, tanpa_wilayah=1),
    }
    assert total_rekap(sesi, job.id, DASAR_TUGAS) == job.jumlah_baris == 4
    assert total_rekap(sesi, job.id, DASAR_POSISI) == job.jumlah_baris == 4


def test_kode_subsls_tak_ada_di_peta_masuk_kategori_tanpa_wilayah(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``level_6_full_code`` di luar peta: tidak ada baris ``wilayah`` baru, FK aman.

    SubSLS tugas yang tidak ada di peta tidak dibuatkan baris dimensi seadanya,
    jadi titiknya dihitung pada kategori "(tanpa wilayah)" dasar ``tugas`` (kode
    NULL) dan tidak menggagalkan penyimpanan.
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
    assert rekap_desa(sesi, job.id, DASAR_TUGAS) == {None: Hitungan(jumlah=2, belum=2)}
    # dasar posisi: keduanya masuk poligon A1 (desa A1)
    assert rekap_desa(sesi, job.id, DASAR_POSISI) == {DESA_A1: Hitungan(jumlah=2, belum=2)}
    assert total_rekap(sesi, job.id, DASAR_TUGAS) == job.jumlah_baris == 2


def test_titik_hasil_hanya_menyimpan_yang_perlu_perhatian(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """``titik_hasil`` hanya memuat titik perlu perhatian; rekap tetap utuh."""
    job = buat_job(sesi, tmp_path)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    assert [satu.assignment_id for satu in baris_hasil(sesi, job.id)] == ["3"]
    assert sesi.get(Run, job.id).detail_tersedia == 1
    # titik benar_awal (1 dan 2) tetap terhitung di rekap
    assert rekap_kabupaten(sesi, job.id, DASAR_TUGAS) == Hitungan(
        jumlah=3, belum=1, benar_awal=2
    )


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
    # titik 1 sudah benar tanpa tindakan manual, jadi tidak disimpan (benar_awal)
    assert set(hasil) == {"2", "3"}

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
    assert diedit_manual.flag_repair_initial == 0
    assert kode_wilayah(sesi, diedit_manual.wilayah_edit_id) == "A1"


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
    assert job.detail_tersedia == 0
    assert baris_hasil(sesi, job.id) == []
    assert sesi.scalars(select(RekapDesa).where(RekapDesa.run_id == job.id)).all() == []
    assert (
        sesi.scalars(select(RekapKabupaten).where(RekapKabupaten.run_id == job.id)).all() == []
    )


def test_penyimpanan_memakai_batch(
    sesi: Session,
    sesi_pabrik: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Hasil yang lebih banyak dari ukuran batch tetap tersimpan lengkap."""
    # level_6 = A2 pada titik di dalam A1: semua titik perlu perhatian, jadi
    # semuanya tersimpan (bukan dipangkas).
    baris = tuple(
        data_kecil.baris_titik_a(str(nomor), "A2", 0.1 + nomor / 100, 0.5)
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


def test_job_antre_lama_tetap_dikerjakan_berurutan(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Job antre lama tidak dibatalkan: dikerjakan berurutan (yang paling lama dulu)."""
    lama, baru = ids_job(sesi, tmp_path, 2)
    sesi.rollback()

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()
    assert sesi.get(Run, lama).status == STATUS_SUKSES
    assert sesi.get(Run, baru).status == STATUS_MENUNGGU, "job antre tidak ditandai batal"

    assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()
    assert sesi.get(Run, baru).status == STATUS_SUKSES

    # kedua run menyimpan baris runs + rekapnya sendiri
    assert rekap_kabupaten(sesi, lama, DASAR_TUGAS) == Hitungan(jumlah=3, belum=1, benar_awal=2)
    assert rekap_kabupaten(sesi, baru, DASAR_TUGAS) == Hitungan(jumlah=3, belum=1, benar_awal=2)
    assert proses_satu_job(sesi_pabrik) is False


def test_pemangkasan_menyimpan_baseline_dan_run_terbaru(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Detail titik hanya disimpan untuk baseline + sukses terakhir (PRD §7).

    Baris ``runs`` dan seluruh snapshot rekap tidak pernah dihapus; yang dipangkas
    hanya ``titik_hasil`` run yang bukan keduanya.
    """
    pertama, tengah, terakhir = ids_job(sesi, tmp_path, 3)
    sesi.rollback()

    for _ in range(3):
        assert proses_satu_job(sesi_pabrik) is True
    sesi.expire_all()

    # rekap & baris runs utuh untuk ketiga run
    for run_id in (pertama, tengah, terakhir):
        assert sesi.get(Run, run_id).status == STATUS_SUKSES
        assert rekap_kabupaten(sesi, run_id, DASAR_TUGAS) == Hitungan(
            jumlah=3, belum=1, benar_awal=2
        )
        assert rekap_kabupaten(sesi, run_id, DASAR_POSISI).jumlah == 3

    assert [sesi.get(Run, satu).detail_tersedia for satu in (pertama, tengah, terakhir)] == [
        1,
        0,
        1,
    ]
    assert baris_hasil(sesi, pertama) != []
    assert baris_hasil(sesi, tengah) == []
    assert baris_hasil(sesi, terakhir) != []


def test_berkas_mentah_hanya_baseline_dan_terbaru(
    sesi: Session, sesi_pabrik: sessionmaker[Session], tmp_path: Path
) -> None:
    """Berkas mentah di folder unggahan hanya disimpan untuk baseline + terbaru."""
    akar = tmp_path / "unggahan"
    akar.mkdir()
    setelan = Settings(worker_enabled=False, dir_unggahan=str(akar))
    ids = ids_job(sesi, tmp_path, 3, akar=akar)
    sesi.rollback()

    for _ in range(3):
        assert proses_satu_job(sesi_pabrik, setelan) is True
    sesi.expire_all()

    assert {jalur.name for jalur in akar.iterdir()} == {"job0", "job2"}
    # nama berkas tetap tersimpan di baris runs sebagai riwayat
    assert {sesi.get(Run, satu).nama_file_input for satu in ids} == {"titik.geojson"}


def test_pangkas_berkas_tidak_menyentuh_luar_folder_unggahan(
    sesi: Session, tmp_path: Path
) -> None:
    """``pangkas_berkas`` hanya menghapus folder di dalam folder unggahan."""
    luar = tmp_path / "luar"
    berkas = data_kecil.tulis(data_kecil.titik_a(*BARIS_A), luar / "titik.geojson")
    run = Run(
        tipe=TIPE_A,
        kdprov="33",
        kdkab="3307",
        status=STATUS_MENUNGGU,
        nama_file_input=berkas.name,
        nama_file_peta=berkas.name,
        berkas_input=str(berkas),
        berkas_peta=str(berkas),
    )
    sesi.add(run)
    sesi.commit()

    assert modul_worker.pangkas_berkas(sesi, [], tmp_path / "unggahan") == []
    assert modul_worker.pangkas_berkas(sesi, [run.id], tmp_path / "unggahan") == []
    assert berkas.exists()


def test_klaim_melewati_job_yang_sedang_jalan(sesi: Session, tmp_path: Path) -> None:
    """Job dengan (kdprov, kdkab, tipe) yang sedang jalan tidak diambil lagi."""
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
