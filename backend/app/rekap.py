"""Rekap progres (PRD §5/§7): agregasi query dan pemangkasan ``titik_hasil``.

Modul ini sengaja tidak bergantung pada geopandas/pyogrio supaya bisa dipakai juga
oleh migrasi Alembic (0005) yang mengisi ``rekap_desa``/``rekap_kabupaten`` untuk run
yang datanya sudah ada, tanpa memproses ulang berkas masukan.

Rekap **selalu** dihitung di basis data dengan satu query GROUP BY (PRD §7: "rekap
dihitung lewat query GROUP BY di basis data"), bukan baris per baris di Python:

- :func:`kueri_rekap_desa` -- per desa (``kdprov``+``kdkab``+``kdkec``+``kddesa``);
- :func:`kueri_rekap_kabupaten` -- dijumlahkan per kabupaten/kota (``kdprov``+``kdkab``).

Titik yang tidak bisa dipetakan ke wilayah pada dasar itu dihitung pada baris
kode NULL, kategori terpisah "(tanpa wilayah)", supaya jumlahnya selalu utuh
(``jumlah`` tiap dasar = ``runs.jumlah_baris``).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, and_, case, delete, func, insert, literal, or_, select, update
from sqlalchemy.orm import Session

from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    KOLOM_HITUNGAN,
    STATUS_SUKSES,
    RekapDesa,
    RekapKabupaten,
    Run,
    TitikHasil,
    Wilayah,
)

#: Dua dasar rekap yang selalu diisi bersama (PRD §5).
DASAR: tuple[str, ...] = (DASAR_TUGAS, DASAR_POSISI)

#: Kolom tujuan ``rekap_desa`` (untuk ``insert().from_select``).
KOLOM_REKAP_DESA: tuple[str, ...] = (
    "run_id",
    "dasar",
    "kdprov",
    "kdkab",
    "kdkec",
    "kddesa",
    *KOLOM_HITUNGAN,
)

#: Kolom tujuan ``rekap_kabupaten`` (untuk ``insert().from_select``).
KOLOM_REKAP_KABUPATEN: tuple[str, ...] = (
    "run_id",
    "dasar",
    "kdprov",
    "kdkab",
    *KOLOM_HITUNGAN,
)


def _kasus(syarat: object) -> object:
    """``CASE WHEN syarat THEN 1 ELSE 0 END`` portabel (MySQL & SQLite)."""
    return case((syarat, 1), else_=0)


def _jumlah_kasus(syarat: object) -> object:
    """``SUM(CASE WHEN syarat THEN 1 ELSE 0 END)``, 0 kalau tidak ada baris."""
    return func.coalesce(func.sum(_kasus(syarat)), 0)


def kolom_ringkas() -> tuple[object, object, object]:
    """Kolom drill-down: (``belum``, ``ditindak_posisi_benar``, ``ditindak_posisi_salah``).

    Dipakai rekap dari ``titik_hasil`` (tingkat SLS/SubSLS) yang hanya membaca titik
    yang perlu perhatian, jadi kolom ``benar_awal``/``digeser``/``tanpa_wilayah``
    tidak ikut dihitung.
    """
    ditindak = and_(TitikHasil.flag_repair == 0, TitikHasil.flag_edit_atr_repair == 1)
    return (
        _jumlah_kasus(TitikHasil.flag_repair == 1),
        _jumlah_kasus(and_(ditindak, TitikHasil.flag_repair_initial == 0)),
        _jumlah_kasus(and_(ditindak, TitikHasil.flag_repair_initial == 1)),
    )


def kolom_hitungan() -> tuple[object, ...]:
    """Kolom hitungan rekap (indikator progres PRD §5), urut seperti ``KOLOM_HITUNGAN``.

    ``flag_edit_atr_repair`` NULL (Proses A tidak punya kolom itu) dianggap 0, jadi
    titik ``flag_repair`` = 0 pada Proses A masuk ``benar_awal``.
    """
    tanpa_tindakan = or_(
        TitikHasil.flag_edit_atr_repair.is_(None), TitikHasil.flag_edit_atr_repair == 0
    )
    tak_masuk_poligon = and_(
        TitikHasil.wilayah_asal_id.is_(None), TitikHasil.wilayah_edit_id.is_(None)
    )
    belum, ditindak_benar, ditindak_salah = kolom_ringkas()
    return (
        func.count(),
        belum,
        _jumlah_kasus(and_(TitikHasil.flag_repair == 0, tanpa_tindakan)),
        ditindak_benar,
        ditindak_salah,
        _jumlah_kasus(TitikHasil.flag_position == 1),
        _jumlah_kasus(tak_masuk_poligon),
    )


def perlu_perhatian() -> object:
    """Syarat titik yang masih disimpan di ``titik_hasil``.

    Titik ``benar_awal`` (``flag_repair`` = 0, ``flag_edit_atr_repair`` = 0, dan
    masuk poligon) tidak disimpan karena sudah terhitung di rekap.
    """
    return or_(
        func.coalesce(TitikHasil.flag_repair, 0) == 1,
        func.coalesce(TitikHasil.flag_edit_atr_repair, 0) == 1,
        and_(TitikHasil.wilayah_asal_id.is_(None), TitikHasil.wilayah_edit_id.is_(None)),
    )


def klausa_wilayah(dasar: str) -> object:
    """Syarat join ``titik_hasil`` ke ``wilayah`` untuk satu dasar.

    Dasar ``tugas`` memakai ``level_6_full_code`` titik (wilayah penugasan), dasar
    ``posisi`` memakai wilayah hasil join peta (``wilayah_edit_id`` bila ada, kalau
    tidak ``wilayah_asal_id``).
    """
    if dasar == DASAR_TUGAS:
        return Wilayah.idsubsls == TitikHasil.level_6_full_code
    if dasar == DASAR_POSISI:
        return Wilayah.id == func.coalesce(TitikHasil.wilayah_edit_id, TitikHasil.wilayah_asal_id)
    raise ValueError(f"dasar harus '{DASAR_TUGAS}' atau '{DASAR_POSISI}', bukan '{dasar}'")


def kueri_rekap_desa(run: Run, dasar: str) -> Select[tuple[object, ...]]:
    """Query rekap satu dasar per desa (termasuk baris "(tanpa wilayah)")."""
    return (
        select(
            literal(run.id),
            literal(dasar),
            Wilayah.kdprov,
            Wilayah.kdkab,
            Wilayah.kdkec,
            Wilayah.kddesa,
            *kolom_hitungan(),
        )
        .select_from(TitikHasil)
        # LEFT JOIN: titik yang tidak cocok tetap terhitung pada baris kode NULL.
        .join(Wilayah, klausa_wilayah(dasar), isouter=True)
        .where(TitikHasil.run_id == run.id)
        .group_by(Wilayah.kdprov, Wilayah.kdkab, Wilayah.kdkec, Wilayah.kddesa)
    )


def kueri_rekap_kabupaten(run: Run, dasar: str) -> Select[tuple[object, ...]]:
    """Query rekap satu dasar untuk satu kabupaten/kota (satu baris)."""
    return (
        select(
            literal(run.id),
            literal(dasar),
            literal(run.kdprov),
            literal(run.kdkab),
            *kolom_hitungan(),
        )
        .select_from(TitikHasil)
        .where(TitikHasil.run_id == run.id)
    )


def simpan_rekap(sesi: Session, run: Run) -> None:
    """Isi ``rekap_desa`` dan ``rekap_kabupaten`` run ini dari ``titik_hasil``.

    Dipanggil di akhir job sukses **sebelum** titik ``benar_awal`` dibuang: rekap
    tetap memuat semua titik, sementara ``titik_hasil`` hanya menyimpan yang perlu
    perhatian. Snapshot run yang sama dibuang dulu supaya pengulangan job tidak
    menggandakan angka; rekap run lain tidak pernah disentuh.
    """
    sesi.execute(delete(RekapDesa).where(RekapDesa.run_id == run.id))
    sesi.execute(delete(RekapKabupaten).where(RekapKabupaten.run_id == run.id))

    for dasar in DASAR:
        sesi.execute(
            insert(RekapDesa).from_select(KOLOM_REKAP_DESA, kueri_rekap_desa(run, dasar))
        )
        sesi.execute(
            insert(RekapKabupaten).from_select(
                KOLOM_REKAP_KABUPATEN, kueri_rekap_kabupaten(run, dasar)
            )
        )


def _syarat_sekelompok(run: Run) -> tuple[object, ...]:
    """Syarat run lain yang sama kabupaten/kota dan tipenya."""
    return (Run.kdprov == run.kdprov, Run.kdkab == run.kdkab, Run.tipe == run.tipe)


def run_sekelompok(sesi: Session, run: Run) -> list[int]:
    """Id run **sukses** sekabupaten/kota+tipe, urut dari yang paling awal."""
    return list(
        sesi.scalars(
            select(Run.id)
            .where(*_syarat_sekelompok(run), Run.status == STATUS_SUKSES)
            .order_by(Run.id)
        )
    )


def run_disimpan(sesi: Session, run: Run) -> set[int]:
    """Id run yang ``titik_hasil``-nya disimpan: baseline + sukses terakhir.

    Baseline = run sukses pertama untuk kabupaten/kota+tipe yang sama (pembanding
    perubahan per titik), sukses terakhir = run yang datanya tersimpan paling baru.
    """
    ids = run_sekelompok(sesi, run)
    return {ids[0], ids[-1]} if ids else set()


def pangkas_titik_hasil(sesi: Session, run: Run) -> list[int]:
    """Rampingkan ``titik_hasil``: buang titik tidak perlu perhatian & run lama.

    Urutannya sengaja rekap dulu (dipanggil pemanggil sebelum fungsi ini) supaya
    angka rekap tidak terpengaruh. Kembaliannya: id run yang ``titik_hasil``-nya
    dipangkas (berkas mentahnya ikut dihapus oleh worker).
    """
    # 1. Run ini sendiri: hanya titik yang perlu perhatian (PRD §7).
    sesi.execute(delete(TitikHasil).where(TitikHasil.run_id == run.id, ~perlu_perhatian()))

    # 2. Run lain sekabupaten/kota+tipe: simpan dua (baseline + sukses terakhir),
    #    baris ``runs`` dan seluruh rekapnya tidak pernah dihapus.
    ids = run_sekelompok(sesi, run)
    if not ids:
        return []
    disimpan = {ids[0], ids[-1]}
    buang = [satu for satu in ids if satu not in disimpan]
    if buang:
        sesi.execute(delete(TitikHasil).where(TitikHasil.run_id.in_(buang)))
    sesi.execute(update(Run).where(Run.id.in_(sorted(disimpan))).values(detail_tersedia=1))
    if buang:
        sesi.execute(update(Run).where(Run.id.in_(buang)).values(detail_tersedia=0))
    return buang
