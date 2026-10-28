"""Rekap progres (PRD §5/§7): agregasi query dan pemangkasan ``titik_hasil``.

Modul ini sengaja tidak bergantung pada geopandas/pyogrio supaya bisa dipakai juga
oleh migrasi Alembic (0005) yang mengisi ``rekap_desa``/``rekap_kabupaten`` untuk run
yang datanya sudah ada, tanpa memproses ulang berkas masukan.

Rekap **selalu** dihitung di basis data dengan satu query GROUP BY (PRD §7: "rekap
dihitung lewat query GROUP BY di basis data"), bukan baris per baris di Python:

- :func:`kueri_rekap_desa` -- per desa (``kdprov``+``kdkab``+``kdkec``+``kddesa``);
- :func:`kueri_rekap_subsls` -- per level 6/SubSLS (satuan hitung target vs B);
- :func:`kueri_rekap_kabupaten` -- dijumlahkan per kabupaten/kota (``kdprov``+``kdkab``).

Titik yang tidak bisa dipetakan ke wilayah pada dasar itu dihitung pada baris
kode NULL, kategori terpisah "(tanpa wilayah)", supaya jumlahnya selalu utuh
(``jumlah`` tiap dasar = ``runs.jumlah_baris``).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, and_, case, delete, func, insert, inspect, literal, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    KOLOM_HITUNGAN,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    RekapDesa,
    RekapKabupaten,
    RekapSubsls,
    RekapTarget,
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

#: Kolom tujuan ``rekap_subsls`` (untuk ``insert().from_select``).
KOLOM_REKAP_SUBSLS: tuple[str, ...] = (
    "run_id",
    "dasar",
    "level_6_full_code",
    "wilayah_id",
    *KOLOM_HITUNGAN,
)

#: Kolom tujuan ``rekap_target`` (untuk ``insert().from_select``).
KOLOM_REKAP_TARGET: tuple[str, ...] = (
    "run_b_id",
    "run_a_id",
    "dasar",
    "level_6_full_code",
    "wilayah_id",
    "target",
    "belum",
    "hilang",
    "selesai",
    "regresi",
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


def kueri_rekap_subsls(run: Run, dasar: str) -> Select[tuple[object, ...]]:
    """Query snapshot satu dasar per level 6/SubSLS.

    Untuk ``dasar=tugas`` kuncinya adalah kode penugasan
    ``titik_hasil.level_6_full_code``; untuk ``dasar=posisi`` kuncinya adalah
    SubSLS hasil join peta. Kode tetap disimpan walau tidak ada di ``wilayah``
    supaya titik di luar peta tidak hilang dari total.
    """
    if dasar == DASAR_TUGAS:
        kode_level6 = TitikHasil.level_6_full_code
    elif dasar == DASAR_POSISI:
        kode_level6 = Wilayah.idsubsls
    else:
        raise ValueError(f"dasar harus '{DASAR_TUGAS}' atau '{DASAR_POSISI}', bukan '{dasar}'")

    return (
        select(
            literal(run.id),
            literal(dasar),
            kode_level6,
            Wilayah.id,
            *kolom_hitungan(),
        )
        .select_from(TitikHasil)
        .join(Wilayah, klausa_wilayah(dasar), isouter=True)
        .where(TitikHasil.run_id == run.id)
        .group_by(kode_level6, Wilayah.id)
    )


def kandidat_kdkab(kdprov: str | None, kdkab: str) -> list[str]:
    """Bentuk kode kabupaten/kota yang mungkin tersimpan di ``runs``.

    Peta wilkerstat memakai kode pendek (``07``), master/SSO memakai 4 digit
    (``3307``); pencocokan run A ke run B harus menerima keduanya.
    """
    prov = str(kdprov).strip() if kdprov is not None else ""
    kode = str(kdkab).strip()
    if prov and len(kode) == 2:
        kode = f"{prov[:2]}{kode}"
    if len(kode) == 4:
        return sorted({kode, kode[2:]})
    return [kode]


def run_a_pasangan(sesi: Session, run_b: Run) -> Run | None:
    """Run A yang menjadi sumber target untuk ``run_b`` (kalau bisa dipakai).

    Aturan pairing dashboard: B harus dibuat setelah A. Kalau ``sumber_run_a_id``
    dicatat saat unggah, A itulah yang dipakai; kalau tidak, dipakai A sukses
    terakhir sebelum B. A tanpa detail titik (``detail_tersedia`` = 0) tidak bisa
    dicocokkan per ``assignment_id`` sehingga dianggap tidak ada.
    """
    if run_b.tipe != TIPE_B:
        return None
    if run_b.sumber_run_a_id is not None:
        calon = sesi.get(Run, run_b.sumber_run_a_id)
        if (
            calon is not None
            and calon.tipe == TIPE_A
            and calon.status == STATUS_SUKSES
            and calon.detail_tersedia
        ):
            return calon
    return sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_A,
            Run.status == STATUS_SUKSES,
            Run.detail_tersedia == 1,
            Run.kdprov == run_b.kdprov,
            Run.kdkab.in_(kandidat_kdkab(run_b.kdprov, run_b.kdkab)),
            Run.id < run_b.id,
        )
        .order_by(Run.id.desc())
        .limit(1)
    ).first()


def kueri_rekap_target(
    run_a: Run, run_b: Run, dasar: str
) -> Select[tuple[object, ...]]:
    """Query capaian B terhadap target A, dicocokkan lewat ``assignment_id``.

    Target = titik A dengan ``flag_repair = 1`` (itulah yang perlu diperbaiki).
    Untuk ``dasar=tugas`` wilayahnya kode penugasan A, sehingga kode yang diubah
    operator di berkas B tidak memindahkan capaian. Untuk ``dasar=posisi``
    wilayahnya posisi titik di B (hasil join peta yang dihitung server), dan titik
    yang hilang dari B memakai posisi A.

    ``belum`` menghitung target yang tidak ada di B **atau** masih
    ``flag_repair = 1``; ``hilang`` hanya yang tidak ada di B.
    """
    if dasar not in DASAR:
        raise ValueError(f"dasar harus '{DASAR_TUGAS}' atau '{DASAR_POSISI}', bukan '{dasar}'")

    titik = aliased(TitikHasil)
    banding = aliased(TitikHasil)
    wilayah_tugas = aliased(Wilayah)
    wilayah_a = aliased(Wilayah)
    wilayah_b = aliased(Wilayah)

    belum = _jumlah_kasus(
        or_(banding.assignment_id.is_(None), func.coalesce(banding.flag_repair, 1) == 1)
    )
    hilang = _jumlah_kasus(banding.assignment_id.is_(None))
    # Klaim kabupaten: nilai flag_repair apa adanya dari berkas unggahan. Titik
    # yang tidak ada di B tetap belum (tidak dihitung selesai). Run B lama tanpa
    # kolom itu memakai flag model seperti sebelumnya.
    selesai = _jumlah_kasus(
        and_(
            banding.assignment_id.is_not(None),
            func.coalesce(banding.flag_repair_unggah, banding.flag_repair) == 0,
        )
    )

    if dasar == DASAR_TUGAS:
        kode_level6: object = titik.level_6_full_code
        kunci_wilayah: object = wilayah_tugas.id
    else:
        kode_level6 = case(
            (banding.assignment_id.is_(None), wilayah_a.idsubsls),
            else_=wilayah_b.idsubsls,
        )
        kunci_wilayah = case(
            (banding.assignment_id.is_(None), wilayah_a.id), else_=wilayah_b.id
        )

    return (
        select(
            literal(run_b.id),
            literal(run_a.id),
            literal(dasar),
            kode_level6,
            kunci_wilayah,
            func.count(),
            belum,
            hilang,
            selesai,
            literal(0),
        )
        .select_from(titik)
        .join(
            banding,
            and_(
                banding.run_id == run_b.id,
                banding.assignment_id == titik.assignment_id,
            ),
            isouter=True,
        )
        .join(
            wilayah_tugas,
            wilayah_tugas.idsubsls == titik.level_6_full_code,
            isouter=True,
        )
        .join(
            wilayah_a,
            wilayah_a.id == func.coalesce(titik.wilayah_edit_id, titik.wilayah_asal_id),
            isouter=True,
        )
        .join(
            wilayah_b,
            wilayah_b.id == func.coalesce(banding.wilayah_edit_id, banding.wilayah_asal_id),
            isouter=True,
        )
        .where(titik.run_id == run_a.id, titik.flag_repair == 1)
        .group_by(kode_level6, kunci_wilayah)
    )


def kueri_regresi_b(run_a: Run, run_b: Run, dasar: str) -> Select[tuple[object, ...]]:
    """Titik B yang ``flag_repair = 1`` dan **bukan** target A, per wilayah.

    Ini kerusakan baru: titik yang tadinya benar di A menjadi salah di B. Titik
    target tidak ikut di sini supaya tidak dihitung dua kali (sudah masuk
    ``belum``). Wilayahnya memakai posisi hasil join peta (dihitung server),
    bukan ``level_6_full_code`` dari berkas B.
    """
    banding = aliased(TitikHasil)
    sumber = aliased(TitikHasil)
    wilayah = aliased(Wilayah)
    target_a = select(sumber.assignment_id).where(
        sumber.run_id == run_a.id, sumber.flag_repair == 1
    )
    if dasar == DASAR_TUGAS:
        kode_level6: object = banding.level_6_full_code
        kunci_wilayah: object = wilayah.id
        syarat_wilayah: object = wilayah.idsubsls == banding.level_6_full_code
    else:
        kode_level6 = wilayah.idsubsls
        kunci_wilayah = wilayah.id
        syarat_wilayah = wilayah.id == func.coalesce(
            banding.wilayah_edit_id, banding.wilayah_asal_id
        )
    return (
        select(kode_level6, kunci_wilayah, func.count())
        .select_from(banding)
        .join(wilayah, syarat_wilayah, isouter=True)
        .where(
            banding.run_id == run_b.id,
            banding.flag_repair == 1,
            banding.assignment_id.not_in(target_a),
        )
        .group_by(kode_level6, kunci_wilayah)
    )


def _tambahkan_regresi(sesi: Session, run_a: Run, run_b: Run, dasar: str) -> None:
    """Tambahkan hitungan kerusakan baru ke baris ``rekap_target`` yang sesuai."""
    for kode, wilayah_id, jumlah in sesi.execute(kueri_regresi_b(run_a, run_b, dasar)):
        hasil = sesi.execute(
            update(RekapTarget)
            .where(
                RekapTarget.run_b_id == run_b.id,
                RekapTarget.dasar == dasar,
                RekapTarget.level_6_full_code == kode,
                RekapTarget.wilayah_id == wilayah_id,
            )
            .values(regresi=RekapTarget.regresi + int(jumlah))
        )
        if hasil.rowcount:
            continue
        sesi.add(
            RekapTarget(
                run_b_id=run_b.id,
                run_a_id=run_a.id,
                dasar=dasar,
                level_6_full_code=kode,
                wilayah_id=wilayah_id,
                target=0,
                belum=0,
                hilang=0,
                regresi=int(jumlah),
            )
        )


def simpan_rekap_target(sesi: Session, run: Run) -> None:
    """Isi ``rekap_target`` untuk job B (target A dicocokkan per ``assignment_id``).

    Dipanggil di akhir job sukses **sebelum** :func:`pangkas_titik_hasil`, jadi
    titik B yang sudah benar (``flag_repair = 0``) masih ada saat dicocokkan.
    Job selain Proses B, atau B tanpa A yang detailnya tersimpan, tidak membuat
    baris: dashboard memakai hitungan lama untuk run seperti itu.
    """
    sesi.execute(delete(RekapTarget).where(RekapTarget.run_b_id == run.id))
    run_a = run_a_pasangan(sesi, run)
    if run_a is None:
        return
    for dasar in DASAR:
        sesi.execute(
            insert(RekapTarget).from_select(
                KOLOM_REKAP_TARGET, kueri_rekap_target(run_a, run, dasar)
            )
        )
        _tambahkan_regresi(sesi, run_a, run, dasar)


def _rekap_subsls_level6_siap(sesi: Session) -> bool:
    """Apakah ``rekap_subsls`` sudah berbentuk baru (punya kode level 6)?

    Migrasi 0005 memanggil fungsi ini saat tabel ``rekap_subsls`` lama masih
    berbentuk 0004 (hanya ``wilayah_id``). Saat itu snapshot level 6 dilewati;
    migrasi 0012 akan membuat tabel baru untuk job berikutnya.
    """
    try:
        kolom = {
            satu["name"] for satu in inspect(sesi.get_bind()).get_columns("rekap_subsls")
        }
    except Exception:  # noqa: BLE001 - tabel bisa belum ada saat migrasi awal
        return False
    return "level_6_full_code" in kolom


def simpan_rekap(sesi: Session, run: Run) -> None:
    """Isi ``rekap_desa``, ``rekap_subsls``, dan ``rekap_kabupaten`` run ini.

    Dipanggil di akhir job sukses **sebelum** titik ``benar_awal`` dibuang: rekap
    tetap memuat semua titik, sementara ``titik_hasil`` hanya menyimpan yang perlu
    perhatian. Snapshot run yang sama dibuang dulu supaya pengulangan job tidak
    menggandakan angka; rekap run lain tidak pernah disentuh.
    """
    sesi.execute(delete(RekapDesa).where(RekapDesa.run_id == run.id))
    sesi.execute(delete(RekapKabupaten).where(RekapKabupaten.run_id == run.id))
    pakai_subsls = _rekap_subsls_level6_siap(sesi)
    if pakai_subsls:
        sesi.execute(delete(RekapSubsls).where(RekapSubsls.run_id == run.id))

    for dasar in DASAR:
        sesi.execute(
            insert(RekapDesa).from_select(KOLOM_REKAP_DESA, kueri_rekap_desa(run, dasar))
        )
        sesi.execute(
            insert(RekapKabupaten).from_select(
                KOLOM_REKAP_KABUPATEN, kueri_rekap_kabupaten(run, dasar)
            )
        )
        if pakai_subsls:
            sesi.execute(
                insert(RekapSubsls).from_select(
                    KOLOM_REKAP_SUBSLS, kueri_rekap_subsls(run, dasar)
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
