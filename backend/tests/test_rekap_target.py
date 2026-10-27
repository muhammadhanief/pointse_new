"""Tes capaian B terhadap target A yang dicocokkan per ``assignment_id``.

Latar belakang: operator di lapangan kadang mengubah ``level_6_full_code`` di
berkas B (padahal itu kode penugasan). Dengan pencocokan lama (jumlah titik per
kode) kode asal kehilangan titik, targetnya tidak pernah terpenuhi, dan rekap
menampilkan sisa walau titiknya sudah dikerjakan. Tes di sini menjaga aturan baru:
wilayah capaian mengikuti A, bukan kode di berkas B.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import layanan
from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    RekapTarget,
    Run,
    TitikHasil,
    Wilayah,
)
from app.rekap import simpan_rekap, simpan_rekap_target

KODE_A = "3325040013001300"
KODE_B = "3325040013000300"


def _wilayah(sesi: Session, kode: str, kddesa: str = "013") -> Wilayah:
    """Satu baris dimensi wilayah untuk kode SubSLS tertentu."""
    baris = Wilayah(
        idsubsls=kode,
        kdprov="33",
        kdkab="3325",
        kdkec="040",
        kddesa=kddesa,
        nmkab="BATANG",
        nmkec="REBAN",
        nmdesa=f"DESA {kddesa}",
    )
    sesi.add(baris)
    sesi.flush()
    return baris


def _run(sesi: Session, tipe: str, *, sumber_a: int | None = None) -> Run:
    """Job sukses dengan detail titik tersimpan (syarat pasangan A/B)."""
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
        jumlah_baris=3,
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
    kode: str,
    *,
    flag_repair: int,
    wilayah: Wilayah | None,
    wilayah_edit: Wilayah | None = None,
) -> None:
    """Satu baris ``titik_hasil`` ringkas untuk pengujian rekap."""
    sesi.add(
        TitikHasil(
            run_id=run.id,
            urut=urut,
            assignment_id=assignment,
            level_6_full_code=kode,
            wilayah_asal_id=wilayah.id if wilayah is not None else None,
            wilayah_edit_id=wilayah_edit.id if wilayah_edit is not None else None,
            flag_repair_initial=flag_repair,
            flag_repair=flag_repair,
            flag_edit_atr_repair=None if run.tipe == TIPE_A else 0,
        )
    )


def _target(sesi: Session, run_b: Run, dasar: str) -> dict[str, tuple[int, int, int]]:
    """Peta kode -> (target, belum, hilang) dari ``rekap_target`` run B."""
    hasil = sesi.scalars(
        select(RekapTarget).where(
            RekapTarget.run_b_id == run_b.id, RekapTarget.dasar == dasar
        )
    )
    return {satu.level_6_full_code: (satu.target, satu.belum, satu.hilang) for satu in hasil}


def _siapkan(sesi: Session) -> tuple[Run, Run, Wilayah, Wilayah]:
    """A (2 target di KODE_A) + B yang memindahkan keduanya ke KODE_B, sudah selesai."""
    w_a = _wilayah(sesi, KODE_A)
    w_b = _wilayah(sesi, KODE_B, kddesa="003")

    run_a = _run(sesi, TIPE_A)
    _titik(sesi, run_a, 0, "a1", KODE_A, flag_repair=1, wilayah=w_a)
    _titik(sesi, run_a, 1, "a2", KODE_A, flag_repair=1, wilayah=w_a)
    _titik(sesi, run_a, 2, "a3", KODE_B, flag_repair=0, wilayah=w_b)
    sesi.flush()

    run_b = _run(sesi, TIPE_B, sumber_a=run_a.id)
    # Kedua titik target dipindah kodenya ke KODE_B oleh operator, flag sudah 0.
    _titik(sesi, run_b, 0, "a1", KODE_B, flag_repair=0, wilayah=w_b)
    _titik(sesi, run_b, 1, "a2", KODE_B, flag_repair=0, wilayah=w_b)
    _titik(sesi, run_b, 2, "a3", KODE_B, flag_repair=0, wilayah=w_b)
    sesi.flush()

    simpan_rekap(sesi, run_a)
    simpan_rekap(sesi, run_b)
    simpan_rekap_target(sesi, run_b)
    return run_a, run_b, w_a, w_b


def test_kode_diubah_tetap_selesai_di_kode_a(sesi: Session) -> None:
    """Titik yang kodenya dipindah di B tetap menutup target kode A."""
    run_a, run_b, w_a, _ = _siapkan(sesi)

    assert _target(sesi, run_b, DASAR_TUGAS) == {KODE_A: (2, 0, 0)}

    progres = layanan._progres_level6(sesi, run_a, run_b, DASAR_TUGAS)
    unit = progres[(KODE_A, w_a.id)]
    assert unit["target"] == 2
    assert unit["selesai"] == 2
    assert unit["sisa"] == 0
    assert unit["lengkap"] is True


def test_assignment_hilang_di_b_dihitung_belum(sesi: Session) -> None:
    """Titik target yang tidak ada di berkas B: belum, dan tercatat hilang."""
    run_a, run_b, w_a, _ = _siapkan(sesi)
    sesi.query(TitikHasil).filter(
        TitikHasil.run_id == run_b.id, TitikHasil.assignment_id == "a2"
    ).delete()
    sesi.flush()

    simpan_rekap_target(sesi, run_b)
    assert _target(sesi, run_b, DASAR_TUGAS) == {KODE_A: (2, 1, 1)}

    unit = layanan._progres_level6(sesi, run_a, run_b, DASAR_TUGAS)[(KODE_A, w_a.id)]
    assert unit["selesai"] == 1
    assert unit["sisa"] == 1
    assert unit["lengkap"] is False


def test_flag_repair_masih_1_tetap_belum(sesi: Session) -> None:
    """Titik yang masih ``flag_repair = 1`` dihitung belum, tapi tidak hilang."""
    run_a, run_b, w_a, _ = _siapkan(sesi)
    satu = sesi.scalars(
        select(TitikHasil).where(
            TitikHasil.run_id == run_b.id, TitikHasil.assignment_id == "a1"
        )
    ).one()
    satu.flag_repair = 1
    sesi.flush()

    simpan_rekap_target(sesi, run_b)
    assert _target(sesi, run_b, DASAR_TUGAS) == {KODE_A: (2, 1, 0)}

    unit = layanan._progres_level6(sesi, run_a, run_b, DASAR_TUGAS)[(KODE_A, w_a.id)]
    assert unit["sisa"] == 1
    assert unit["lengkap"] is True


def test_dasar_posisi_mengikuti_posisi_b(sesi: Session) -> None:
    """Dasar posisi: target mengikuti SubSLS tempat titik berada menurut join B."""
    run_a, run_b, _, w_b = _siapkan(sesi)

    assert _target(sesi, run_b, DASAR_POSISI) == {KODE_B: (2, 0, 0)}
    progres = layanan._progres_level6(sesi, run_a, run_b, DASAR_POSISI)
    unit = progres[(KODE_B, w_b.id)]
    assert unit["target"] == 2
    assert unit["selesai"] == 2
    assert unit["sisa"] == 0


def test_tanpa_rekap_target_pakai_hitungan_lama(sesi: Session) -> None:
    """Run B lama tanpa baris ``rekap_target`` tetap memakai cara lama."""
    run_a, run_b, w_a, _ = _siapkan(sesi)
    sesi.query(RekapTarget).delete()
    sesi.flush()

    assert _target(sesi, run_b, DASAR_TUGAS) == {}
    unit = layanan._progres_level6(sesi, run_a, run_b, DASAR_TUGAS)[(KODE_A, w_a.id)]
    # Cara lama membandingkan jumlah per kode: KODE_A hilang 2 titik di B,
    # jadi capaian di kode itu 0 walau titiknya sudah selesai di tempat lain.
    assert unit["target"] == 2
    assert unit["selesai"] == 0


def test_pasangan_a_dicari_kalau_sumber_tidak_dicatat(sesi: Session) -> None:
    """B tanpa ``sumber_run_a_id`` memakai A sukses terakhir sebelum B."""
    w_a = _wilayah(sesi, KODE_A)
    run_a = _run(sesi, TIPE_A)
    _titik(sesi, run_a, 0, "a1", KODE_A, flag_repair=1, wilayah=w_a)
    sesi.flush()
    simpan_rekap(sesi, run_a)

    run_b = _run(sesi, TIPE_B)
    _titik(sesi, run_b, 0, "a1", KODE_A, flag_repair=0, wilayah=w_a)
    sesi.flush()
    simpan_rekap(sesi, run_b)
    simpan_rekap_target(sesi, run_b)

    assert _target(sesi, run_b, DASAR_TUGAS) == {KODE_A: (1, 0, 0)}


def test_titik_bukan_target_yang_rusak_menurunkan_capaian(sesi: Session) -> None:
    """Titik yang tadinya benar tapi jadi ``flag_repair = 1`` di B = regresi."""
    run_a, run_b, w_a, _ = _siapkan(sesi)
    # a3 bukan target A (flag 0). Di B titik itu jadi bermasalah.
    satu = sesi.scalars(
        select(TitikHasil).where(
            TitikHasil.run_id == run_b.id, TitikHasil.assignment_id == "a3"
        )
    ).one()
    satu.flag_repair = 1
    satu.level_6_full_code = KODE_A
    sesi.flush()

    simpan_rekap_target(sesi, run_b)
    baris = sesi.scalars(
        select(RekapTarget).where(
            RekapTarget.run_b_id == run_b.id,
            RekapTarget.dasar == DASAR_TUGAS,
            RekapTarget.level_6_full_code == KODE_A,
        )
    ).one()
    assert (baris.target, baris.belum, baris.hilang, baris.regresi) == (2, 0, 0, 1)

    unit = layanan._progres_level6(sesi, run_a, run_b, DASAR_TUGAS)[(KODE_A, w_a.id)]
    assert (unit["selesai"], unit["sisa"]) == (1, 1)


def test_run_a_tanpa_baris_target(sesi: Session) -> None:
    """B yang seluruh targetnya hilang tetap punya baris target 2/belum 2."""
    run_a, run_b, _, _ = _siapkan(sesi)
    sesi.query(TitikHasil).filter(TitikHasil.run_id == run_b.id).delete()
    sesi.flush()

    simpan_rekap_target(sesi, run_b)
    assert _target(sesi, run_b, DASAR_TUGAS) == {KODE_A: (2, 2, 2)}
