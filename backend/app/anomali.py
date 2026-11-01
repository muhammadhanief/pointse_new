"""Deteksi anomali titik pada job Proses B (menu "Anomali titik").

Rekap memakai **klaim kabupaten**: ``titik_hasil.flag_repair_unggah`` apa adanya
dari berkas yang diunggah. Modul ini melengkapinya dengan pandangan sistem:
titik mana yang menurut hitung ulang model masih bermasalah, atau yang tidak
bisa dicocokkan sama sekali.

Kategori (saling lepas, satu titik hanya masuk satu kategori):

``hilang``
    Titik target A tidak ada di berkas B dan identitas bangunannya
    (``unique_bang``) juga tidak ditemukan.
``id_berubah``
    Titik target A tidak ada, tetapi ada tepat satu baris B dengan
    ``unique_bang`` yang sama (``assignment_id`` diganti operator).
``luar_wilayah``
    Titik ada di B, tetapi posisinya tidak masuk poligon wilkerstat mana pun.
``posisi_menyimpang``
    Titik ada di B, kabupaten mengklaim ``flag_repair = 0``, tetapi model
    menandainya 1 (posisi masuk SLS lain dan flag tidak diedit).
``kode_berubah``
    Titik ada di B dan model menganggapnya beres, tetapi ``level_6_full_code``
    di B berbeda dari kode penugasan A.
``regresi``
    Titik di B yang bukan target A tetapi ``flag_repair = 1`` (kerusakan baru).
``titik_baru``
    ``assignment_id`` di B yang tidak ada di A sama sekali.

Baris dihitung di akhir job B **sebelum** ``titik_hasil`` dipangkas, dan disimpan
untuk **setiap** run B sukses per kabupaten/kota supaya riwayat/tren pencermatan
terbaca. Totalnya juga disimpan di ``runs.jumlah_anomali`` (0 = bersih). Blok
lama yang menghapus anomali run B lain sekabupaten masih ada di
:func:`simpan_anomali` tetapi dinonaktifkan (dikomentari).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import (
    String,
    and_,
    column,
    delete,
    func,
    insert,
    literal,
    or_,
    select,
    table,
    text,
)
from sqlalchemy.orm import Session, aliased

from app import konfirmasi as modul_konfirmasi
from app import rekap as modul_rekap
from app.models import (
    DASAR_TUGAS,
    STATUS_SUKSES,
    TIPE_B,
    AnomaliTitik,
    KonfirmasiAnomali,
    RekapTarget,
    Run,
    TitikHasil,
    Wilayah,
)

#: (kode, label) kategori anomali, urutan tampil di dropdown.
JENIS: tuple[tuple[str, str], ...] = (
    ("hilang", "Titik hilang"),
    ("id_berubah", "Assignment ID berubah"),
    ("luar_wilayah", "Di luar wilayah"),
    ("posisi_menyimpang", "Posisi menyimpang"),
    ("kode_berubah", "Kode SLS berubah"),
    ("regresi", "Bermasalah lagi (regresi)"),
    ("titik_baru", "Titik baru"),
)

LABEL: dict[str, str] = dict(JENIS)

logger = logging.getLogger(__name__)

#: Tabel sementara daftar ``assignment_id`` berkas A (lihat :func:`_siapkan_id_a`).
TABEL_ID_A = "_anomali_id_a"

#: Kolom tujuan ``anomali_titik`` (untuk ``insert().from_select``).
KOLOM: tuple[str, ...] = (
    "run_b_id",
    "run_a_id",
    "jenis",
    "assignment_id",
    "assignment_id_baru",
    "unique_bang",
    "level_6_full_code",
    "level_6_full_code_b",
    "wilayah_id",
    "latitude",
    "longitude",
    "flag_unggah",
    "flag_model",
)


def _wilayah_b(b: Any) -> Any:
    """Wilayah titik di B: posisi hasil join peta (fallback wilayah asal)."""
    return func.coalesce(b.wilayah_edit_id, b.wilayah_asal_id)


def _klaim(b: Any) -> Any:
    """``flag_repair`` menurut unggahan; run lama tanpa kolom itu pakai model."""
    return func.coalesce(b.flag_repair_unggah, b.flag_repair)


def _kueri_pasangan(
    run_a: Run, run_b: Run, jenis: str, syarat: Callable[[Any, Any], Any]
) -> Any:
    """Query titik target A yang ada di B dan memenuhi ``syarat(a, b)``."""
    a = aliased(TitikHasil)
    b = aliased(TitikHasil)
    return (
        select(
            literal(run_b.id),
            literal(run_a.id),
            literal(jenis),
            a.assignment_id,
            literal(None, String(64)),
            a.unique_bang,
            a.level_6_full_code,
            b.level_6_full_code,
            _wilayah_b(b),
            b.latitude_edited,
            b.longitude_edited,
            b.flag_repair_unggah,
            b.flag_repair,
        )
        .select_from(a)
        .join(b, and_(b.run_id == run_b.id, b.assignment_id == a.assignment_id))
        .where(a.run_id == run_a.id, a.flag_repair == 1, syarat(a, b))
    )


def _kueri_titik_b(
    run_a: Run, run_b: Run, jenis: str, syarat: Callable[[Any, Any], Any]
) -> Any:
    """Query titik B yang tidak berpasangan dengan target A."""
    a = aliased(TitikHasil)
    b = aliased(TitikHasil)
    return select(
        literal(run_b.id),
        literal(run_a.id),
        literal(jenis),
        b.assignment_id,
        literal(None, String(64)),
        b.unique_bang,
        # Titik ini tidak punya pasangan di Master GS, jadi kolom kode Master GS
        # dikosongkan; hanya kode Geotag Kabkot yang bermakna.
        literal(None, String(16)),
        b.level_6_full_code,
        _wilayah_b(b),
        b.latitude_edited,
        b.longitude_edited,
        b.flag_repair_unggah,
        b.flag_repair,
    ).where(b.run_id == run_b.id, syarat(a, b))


def _sisip(sesi: Session, kueri: Any) -> int:
    hasil = sesi.execute(insert(AnomaliTitik).from_select(list(KOLOM), kueri))
    return int(hasil.rowcount or 0)


def _titik_hilang(sesi: Session, run_a: Run, run_b: Run) -> list[Any]:
    """Target A yang ``assignment_id``-nya tidak ada di B."""
    a = aliased(TitikHasil)
    b = aliased(TitikHasil)
    ada_di_b = (
        select(literal(1))
        .where(b.run_id == run_b.id, b.assignment_id == a.assignment_id)
        .exists()
    )
    return list(
        sesi.execute(
            select(
                a.assignment_id,
                a.unique_bang,
                a.level_6_full_code,
                func.coalesce(a.wilayah_edit_id, a.wilayah_asal_id),
                a.latitude_edited,
                a.longitude_edited,
            ).where(
                a.run_id == run_a.id,
                a.flag_repair == 1,
                ~ada_di_b,
            )
        )
    )


def _kandidat_bangunan(
    sesi: Session, run_b: Run, unique_bang: set[str]
) -> dict[str, list[Any]]:
    """Baris B dikelompokkan per ``unique_bang`` (untuk mengenali id berubah)."""
    if not unique_bang:
        return {}
    b = aliased(TitikHasil)
    keluaran: dict[str, list[Any]] = defaultdict(list)
    for baris in sesi.execute(
        select(
            b.unique_bang,
            b.assignment_id,
            b.level_6_full_code,
            _wilayah_b(b),
            b.latitude_edited,
            b.longitude_edited,
            b.flag_repair_unggah,
            b.flag_repair,
        ).where(b.run_id == run_b.id, b.unique_bang.in_(unique_bang))
    ):
        keluaran[str(baris[0])].append(tuple(baris[1:]))
    return keluaran


def _simpan_hilang(
    sesi: Session, run_a: Run, run_b: Run
) -> tuple[int, int, set[str]]:
    """Simpan ``hilang``/``id_berubah``.

    Kembalikan (jumlah hilang, jumlah id berubah, id pengganti yang dipakai),
    supaya id pengganti itu tidak dihitung lagi sebagai ``titik_baru``.
    """
    hilang = _titik_hilang(sesi, run_a, run_b)
    if not hilang:
        return 0, 0, set()
    ub = {str(satu[1]) for satu in hilang if satu[1]}
    kandidat = _kandidat_bangunan(sesi, run_b, ub)

    baris: list[dict[str, Any]] = []
    jumlah_hilang = 0
    jumlah_ubah = 0
    id_baru: set[str] = set()
    for assignment_id, unique_bang, kode, wilayah_id, lat, lon in hilang:
        calon = kandidat.get(str(unique_bang), []) if unique_bang else []
        # Ambigu (lebih dari satu bangunan dengan id sama) diperlakukan hilang.
        baru = calon[0] if len(calon) == 1 else None
        if baru is None:
            jumlah_hilang += 1
            jenis = "hilang"
        else:
            jumlah_ubah += 1
            jenis = "id_berubah"
            id_baru.add(str(baru[0]))
        # Titik tidak ada di Geotag Kabkot: kolom kode Geotag Kabkot dikosongkan,
        # hanya kode Master GS (penugasan) yang diisi.
        isi = baru or (None, None, wilayah_id, lat, lon, None, None)
        baris.append(
            {
                "run_b_id": run_b.id,
                "run_a_id": run_a.id,
                "jenis": jenis,
                "assignment_id": assignment_id,
                "assignment_id_baru": isi[0] if baru is not None else None,
                "unique_bang": unique_bang,
                "level_6_full_code": kode,
                "level_6_full_code_b": isi[1],
                "wilayah_id": isi[2],
                "latitude": isi[3],
                "longitude": isi[4],
                "flag_unggah": isi[5],
                "flag_model": isi[6],
            }
        )
    if baris:
        sesi.execute(insert(AnomaliTitik), baris)
    return jumlah_hilang, jumlah_ubah, id_baru


def _id_a_dari_berkas(run_a: Run) -> list[str] | None:
    """Seluruh ``assignment_id`` berkas A, atau ``None`` bila tidak terbaca.

    ``titik_hasil`` run A sudah dipangkas (hanya titik yang perlu perhatian),
    sehingga daftar id lengkap hanya bisa diambil dari berkas mentah yang masih
    disimpan. Tanpa ini setiap titik B yang sehat terlihat sebagai "titik baru".
    """
    jalur = getattr(run_a, "berkas_input", None)
    if not jalur or not os.path.exists(jalur):
        return None
    try:
        import pyogrio  # impor berat: hanya dipakai worker

        tabel = pyogrio.read_dataframe(
            jalur,
            layer=run_a.layer_input,
            columns=["assignment_id"],
            read_geometry=False,
        )
    except Exception:  # noqa: BLE001 - berkas hilang/rusak: pakai sisa titik_hasil
        logger.warning(
            "berkas A run %s tidak terbaca; daftar id memakai titik_hasil",
            run_a.id,
            exc_info=True,
        )
        return None
    if "assignment_id" not in tabel.columns:
        return None
    seri = tabel["assignment_id"].dropna().astype(str).str.strip()
    return [satu for satu in seri.unique().tolist() if satu]


def _siapkan_id_a(sesi: Session, run_a: Run) -> Any:
    """Isi tabel sementara daftar ``assignment_id`` A; kembalikan subquery-nya.

    Dipakai ``regresi`` (titik B yang ada di A tetapi bukan target) dan
    ``titik_baru`` (id yang benar-benar tidak ada di A). Tabel sementara dipilih
    supaya ``IN`` tidak membawa ratusan ribu parameter.
    """
    sesi.execute(text(f"DROP TABLE IF EXISTS {TABEL_ID_A}"))
    sesi.execute(
        text(
            f"CREATE TEMPORARY TABLE {TABEL_ID_A} "
            "(assignment_id VARCHAR(64) NOT NULL PRIMARY KEY)"
        )
    )
    ids = _id_a_dari_berkas(run_a)
    if ids is None:
        ids = [
            str(satu)
            for satu in sesi.scalars(
                select(TitikHasil.assignment_id).where(
                    TitikHasil.run_id == run_a.id,
                    TitikHasil.assignment_id.is_not(None),
                )
            )
        ]
    abaikan = (
        "INSERT OR IGNORE"
        if sesi.get_bind().dialect.name == "sqlite"
        else "INSERT IGNORE"
    )
    for mulai in range(0, len(ids), 5000):
        potong = ids[mulai : mulai + 5000]
        sesi.execute(
            text(f"{abaikan} INTO {TABEL_ID_A} (assignment_id) VALUES (:id)"),
            [{"id": satu} for satu in potong],
        )
    return select(table(TABEL_ID_A, column("assignment_id")).c.assignment_id)


def simpan_anomali(sesi: Session, run: Run) -> int:
    """Hitung dan simpan anomali job B; kembalikan jumlah baris.

    Dipanggil di akhir job sukses **sebelum** ``titik_hasil`` dirampingkan oleh
    :mod:`app.pemeliharaan` (butuh seluruh titik B, termasuk yang sudah benar).
    Job selain Proses B atau B tanpa A yang detailnya tersimpan tidak
    menghasilkan baris.
    """
    if run.tipe != TIPE_B:
        return 0
    run_a = modul_rekap.run_a_pasangan(sesi, run)
    if run_a is None:
        run.anomali_versi = 0
        return 0

    # DINONAKTIFKAN 2026-11-01: dulu hanya run B terakhir yang disimpan, jadi
    # anomali run B lain sekabupaten dibuang di sini. Sekarang riwayat/tren
    # pencermatan per kabupaten/kota per waktu dibutuhkan, jadi detail SEMUA run
    # B dipertahankan. Kode lama dikomentari (bukan dihapus) -- mungkin dipakai
    # lagi kalau tabel perlu dirapikan lewat :mod:`app.pemeliharaan`.
    #
    # lain = list(
    #     sesi.scalars(
    #         select(Run.id).where(
    #             Run.tipe == TIPE_B,
    #             Run.kdprov == run.kdprov,
    #             Run.kdkab == run.kdkab,
    #             Run.id != run.id,
    #         )
    #     )
    # )
    # if lain:
    #     sesi.execute(delete(AnomaliTitik).where(AnomaliTitik.run_b_id.in_(lain)))
    #
    # Catatan lama: id run lain diambil dengan SELECT biasa lebih dulu, BUKAN
    # subquery di dalam DELETE, karena MariaDB mengunci setiap baris ``runs`` yang
    # dibaca subquery DML sehingga worker kedua bisa menunggu sampai "Lock wait
    # timeout exceeded" (job 80, 2026-10-28). SELECT biasa = consistent read.
    #
    # DELETE pada rentang kosong pun mengambil gap lock di MariaDB; lewati bila
    # memang tidak ada sisa anomali run ini.
    ada = sesi.scalar(
        select(AnomaliTitik.id).where(AnomaliTitik.run_b_id == run.id).limit(1)
    )
    if ada is not None:
        sesi.execute(delete(AnomaliTitik).where(AnomaliTitik.run_b_id == run.id))

    a = aliased(TitikHasil)
    target_a = select(a.assignment_id).where(
        a.run_id == run_a.id, a.flag_repair == 1
    )
    semua_a = _siapkan_id_a(sesi, run_a)

    jumlah = 0
    jumlah_hilang, jumlah_ubah, id_baru = _simpan_hilang(sesi, run_a, run)
    jumlah += jumlah_hilang + jumlah_ubah

    # Titik target yang ada di B: kategori saling lepas menurut prioritas.
    jumlah += _sisip(
        sesi,
        _kueri_pasangan(
            run_a,
            run,
            "luar_wilayah",
            lambda a, b: and_(
                b.wilayah_edit_id.is_(None),
                b.wilayah_asal_id.is_(None),
            ),
        ),
    )
    jumlah += _sisip(
        sesi,
        _kueri_pasangan(
            run_a,
            run,
            "posisi_menyimpang",
            lambda a, b: and_(
                _wilayah_b(b).is_not(None),
                b.flag_repair == 1,
                _klaim(b) == 0,
            ),
        ),
    )
    jumlah += _sisip(
        sesi,
        _kueri_pasangan(
            run_a,
            run,
            "kode_berubah",
            lambda a, b: and_(
                _wilayah_b(b).is_not(None),
                func.coalesce(b.flag_repair, 0) == 0,
                b.level_6_full_code != a.level_6_full_code,
            ),
        ),
    )
    # Titik B yang tidak termasuk target A.
    jumlah += _sisip(
        sesi,
        _kueri_titik_b(
            run_a,
            run,
            "regresi",
            lambda a, b: and_(
                b.flag_repair == 1,
                b.assignment_id.in_(semua_a),
                ~b.assignment_id.in_(target_a),
            ),
        ),
    )
    def _bukan_titik_baru(a: Any, b: Any) -> Any:
        """Id yang tidak ada di A dan bukan pengganti hasil ``id_berubah``."""
        syarat = [~b.assignment_id.in_(semua_a)]
        if id_baru:
            syarat.append(~b.assignment_id.in_(id_baru))
        return and_(*syarat)

    jumlah += _sisip(
        sesi,
        _kueri_titik_b(run_a, run, "titik_baru", _bukan_titik_baru),
    )

    run.anomali_versi = 1
    # Total per run disimpan permanen (0 = bersih) supaya tren tetap terbaca
    # walau detail ``anomali_titik`` run ini tidak lagi lengkap.
    run.jumlah_anomali = jumlah
    return jumlah


def hitung_per_jenis(sesi: Session, run_b_id: int | list[int]) -> dict[str, int]:
    """Jumlah anomali per jenis untuk satu atau beberapa run B."""
    ids = [run_b_id] if isinstance(run_b_id, int) else list(run_b_id)
    if not ids:
        return {}
    return {
        str(jenis): int(jumlah)
        for jenis, jumlah in sesi.execute(
            select(AnomaliTitik.jenis, func.count())
            .where(AnomaliTitik.run_b_id.in_(ids))
            .group_by(AnomaliTitik.jenis)
        )
    }


def _saring_run_b(kdprov: str | None, kdkab: str) -> list[Any]:
    """Syarat SQL run Proses B **sukses** satu kabupaten/kota."""
    return [
        Run.tipe == TIPE_B,
        Run.status == STATUS_SUKSES,
        Run.kdprov == kdprov if kdprov else Run.kdprov.is_not(None),
        Run.kdkab.in_(modul_rekap.kandidat_kdkab(kdprov, kdkab)),
    ]


def run_b_terakhir_banyak(
    sesi: Session, kdprov: str | None, daftar_kdkab: list[str]
) -> list[Run]:
    """Run B sukses terakhir untuk tiap kabupaten/kota (urutan masukan)."""
    hasil: list[Run] = []
    terpakai: set[int] = set()
    for kdkab in daftar_kdkab:
        run = run_b_terakhir(sesi, kdprov, kdkab)
        if run is not None and run.id not in terpakai:
            terpakai.add(run.id)
            hasil.append(run)
    return hasil


def run_b_terakhir(sesi: Session, kdprov: str | None, kdkab: str) -> Run | None:
    """Run Proses B sukses terakhir satu kabupaten/kota (sumber menu anomali)."""
    return sesi.scalars(
        select(Run)
        .where(*_saring_run_b(kdprov, kdkab))
        .order_by(Run.id.desc())
        .limit(1)
    ).first()


def riwayat_runs(
    sesi: Session, kdprov: str | None, kdkab: str
) -> list[tuple[Run, int, int]]:
    """Riwayat run Proses B sukses satu kabupaten/kota, terbaru dulu.

    Kembalikan ``(run, target, selesai)``. ``target``/``selesai`` dijumlahkan
    dari ``rekap_target`` dasar tugas dengan **satu** query (bukan per run) agar
    dropdown riwayat tetap ringan walau run-nya banyak.
    """
    runs = list(
        sesi.scalars(
            select(Run).where(*_saring_run_b(kdprov, kdkab)).order_by(Run.id.desc())
        )
    )
    if not runs:
        return []
    ids = [satu.id for satu in runs]
    jumlah = {
        int(run_id): (int(target), int(selesai))
        for run_id, target, selesai in sesi.execute(
            select(
                RekapTarget.run_b_id,
                func.coalesce(func.sum(RekapTarget.target), 0),
                func.coalesce(func.sum(RekapTarget.selesai), 0),
            )
            .where(RekapTarget.run_b_id.in_(ids), RekapTarget.dasar == DASAR_TUGAS)
            .group_by(RekapTarget.run_b_id)
        )
    }
    return [(satu, *jumlah.get(satu.id, (0, 0))) for satu in runs]


def run_terpilih(
    sesi: Session, kdprov: str | None, daftar_kdkab: list[str], run_b_id: int | None
) -> list[Run]:
    """Run B untuk menu anomali: ``run_b_id`` bila sah, jika tidak run terakhir.

    Riwayat run hanya bermakna saat tepat satu kabupaten/kota dipilih.
    ``run_b_id`` yang bukan Proses B sukses milik wilayah itu diabaikan supaya
    tautan lama tidak menampilkan wilayah lain atau run yang tidak relevan.
    """
    if run_b_id is not None and len(daftar_kdkab) == 1:
        run = sesi.get(Run, run_b_id)
        if (
            run is not None
            and run.tipe == TIPE_B
            and run.status == STATUS_SUKSES
            and (run.kdprov == kdprov if kdprov else True)
            and run.kdkab in modul_rekap.kandidat_kdkab(kdprov, daftar_kdkab[0])
        ):
            return [run]
    return run_b_terakhir_banyak(sesi, kdprov, daftar_kdkab)



def _saring_anomali(
    kueri: Any,
    jenis: str | list[str] | None,
    cari: str | None,
) -> Any:
    """Terapkan filter jenis + pencarian pada query baris anomali."""
    if jenis:
        daftar = [jenis] if isinstance(jenis, str) else list(jenis)
        if daftar:
            kueri = kueri.where(AnomaliTitik.jenis.in_(daftar))
    if cari:
        pola = f"%{cari}%"
        kueri = kueri.where(
            or_(
                AnomaliTitik.assignment_id.like(pola),
                AnomaliTitik.assignment_id_baru.like(pola),
                AnomaliTitik.unique_bang.like(pola),
                AnomaliTitik.level_6_full_code.like(pola),
                AnomaliTitik.level_6_full_code_b.like(pola),
                Wilayah.nmsls.like(pola),
                Wilayah.nmdesa.like(pola),
            )
        )
    return kueri


def _saring_status(kueri: Any, status: str | None) -> Any:
    """Terapkan filter status konfirmasi (``belum`` = tanpa konfirmasi)."""
    if status == modul_konfirmasi.BELUM:
        return kueri.where(KonfirmasiAnomali.id.is_(None))
    if status:
        return kueri.where(KonfirmasiAnomali.status == status)
    return kueri


def kueri_baris(
    run_b_id: int | list[int],
    jenis: str | list[str] | None = None,
    cari: str | None = None,
    status: str | None = None,
) -> Any:
    """Query baris anomali + nama wilayah + konfirmasi untuk satu/beberapa run B.

    Kembaliannya
    ``(AnomaliTitik, nmsls, nmdesa, kdkab, KonfirmasiAnomali | None)`` supaya
    tabel dan Excel bisa menandai asal kabupaten/kota sekaligus status
    konfirmasinya. ``status``: ``"belum"`` (tanpa konfirmasi),
    ``"akan_diperbaiki"``, ``"sesuai_kenyataan"``, atau ``None`` (semua).
    """
    ids = [run_b_id] if isinstance(run_b_id, int) else list(run_b_id)
    kueri = (
        select(
            AnomaliTitik,
            Wilayah.nmsls,
            Wilayah.nmdesa,
            Run.kdkab,
            KonfirmasiAnomali,
        )
        .join(Wilayah, Wilayah.id == AnomaliTitik.wilayah_id, isouter=True)
        .join(Run, Run.id == AnomaliTitik.run_b_id)
        .join(
            KonfirmasiAnomali,
            modul_konfirmasi.syarat_cocok(),
            isouter=True,
        )
        .where(AnomaliTitik.run_b_id.in_(ids))
    )
    kueri = _saring_status(_saring_anomali(kueri, jenis, cari), status)
    return kueri.order_by(
        Run.kdkab,
        AnomaliTitik.level_6_full_code,
        AnomaliTitik.assignment_id,
    )


def kueri_konfirmasi(
    run_b_id: int | list[int],
    jenis: str | list[str] | None = None,
    cari: str | None = None,
    status: str | None = None,
) -> Any:
    """Query baris untuk aksi konfirmasi massal: ``(AnomaliTitik, kdkab, kdprov)``.

    Lebih ringan dari :func:`kueri_baris` karena tidak perlu nama wilayah, tetapi
    tetap memakai filter dan join konfirmasi yang sama supaya mode "pilih semua
    hasil filter" memakai himpunan baris yang persis sama dengan tabel.
    """
    ids = [run_b_id] if isinstance(run_b_id, int) else list(run_b_id)
    kueri = (
        select(AnomaliTitik, Run.kdkab, Run.kdprov)
        .join(Wilayah, Wilayah.id == AnomaliTitik.wilayah_id, isouter=True)
        .join(Run, Run.id == AnomaliTitik.run_b_id)
        .join(
            KonfirmasiAnomali,
            modul_konfirmasi.syarat_cocok(),
            isouter=True,
        )
        .where(AnomaliTitik.run_b_id.in_(ids))
    )
    kueri = _saring_status(_saring_anomali(kueri, jenis, cari), status)
    return kueri.order_by(Run.kdkab, AnomaliTitik.id)


def hitung_status_konfirmasi(
    sesi: Session,
    run_b_id: int | list[int],
    jenis: str | list[str] | None = None,
    cari: str | None = None,
) -> dict[str | None, int]:
    """Jumlah baris per status konfirmasi (``None`` = belum) untuk ringkasan.

    Filter status **tidak** diterapkan di sini supaya progres "dikonfirmasi X
    dari Y" tetap utuh walau tabel sedang difilter ke satu status.
    """
    ids = [run_b_id] if isinstance(run_b_id, int) else list(run_b_id)
    if not ids:
        return {None: 0}
    kueri = (
        select(KonfirmasiAnomali.status, func.count())
        .select_from(AnomaliTitik)
        .join(Wilayah, Wilayah.id == AnomaliTitik.wilayah_id, isouter=True)
        .join(Run, Run.id == AnomaliTitik.run_b_id)
        .join(
            KonfirmasiAnomali,
            modul_konfirmasi.syarat_cocok(),
            isouter=True,
        )
        .where(AnomaliTitik.run_b_id.in_(ids))
    )
    kueri = _saring_anomali(kueri, jenis, cari).group_by(KonfirmasiAnomali.status)
    hasil: dict[str | None, int] = {None: 0}
    for status, jumlah in sesi.execute(kueri):
        hasil[None if status is None else str(status)] = int(jumlah)
    return hasil


def keterangan(baris: AnomaliTitik, wilayah: str | None = None) -> str:
    """Kalimat pendek penjelas satu baris anomali (untuk tabel & Excel)."""
    if baris.jenis == "hilang":
        return "tidak ada di Geotag Kabkot"
    if baris.jenis == "id_berubah":
        return f"id baru {baris.assignment_id_baru or '-'}"
    if baris.jenis == "luar_wilayah":
        return "posisi di luar poligon wilkerstat"
    if baris.jenis == "posisi_menyimpang":
        return f"posisi masuk {wilayah or 'wilayah lain'}"
    if baris.jenis == "kode_berubah":
        return f"kode Geotag Kabkot {baris.level_6_full_code_b or '-'}"
    if baris.jenis == "regresi":
        return "di Master GS sudah beres, ditandai bermasalah lagi di Geotag Kabkot"
    return "tidak ada di Master GS"
