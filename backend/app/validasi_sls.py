"""Validasi peta SLS/SubSLS 2026 Semester 1 (tipe run V, PRD §11).

Tiga blok, tanpa geometri (pengganti langkah poligon ``Cek_Master_PetaSLS``):

1. **Skema atribut**: peta wajib punya 17 field sesuai dokumen "Validasi
   Atribut" (``kdprov``..``posisi``) dengan panjang data sesuai tabel.
   ``tingkat`` bertipe integer, sisanya string.
2. **ID duplikat**: ``idsls`` tidak boleh ganda di dalam berkas.
3. **Matching dua arah lawan master Excel**: ``idsls`` peta vs master
   (``msubsls`` derivasi ``idsubsls[:14]`` == ``hirarki_sls.idsls_26_1``;
   terbukti identik sebagai himpunan pada data 3302: 11.439 unik).
   ``peta vs master`` = ada di peta tapi tidak di master (``unmatch_peta``);
   ``master vs peta`` = ada di master tapi tidak di peta (``unmatch_master``).

Modul ini **ringan saat startup**: ``pyogrio``/``openpyxl`` hanya diimpor di
dalam fungsi (dipakai worker), supaya proses API tetap ringan (PRD §8).

Steril dari SE2026: tidak menyentuh ``wilayah``/``titik_hasil``/rekap, tidak
ikut hitung nomor job A/B, dan tidak menjadi sumber peta Proses B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


#: Semester yang divalidasi run V (kolom ``runs.semester``).
SEMESTER_DEFAULT = "2026_1"

#: 17 kolom atribut peta 2026 S1 (PRD §11.1).
KOLOM_PETA_V: tuple[str, ...] = (
    "kdprov",
    "kdkab",
    "kdkec",
    "kddesa",
    "kdsls",
    "kdsubsls",
    "idsls",
    "idsubsls",
    "nmprov",
    "nmkab",
    "nmkec",
    "nmdesa",
    "nmsls",
    "rw_dki",
    "tingkat",
    "nm_gedung",
    "posisi",
)

#: Panjang data maksimum per kolom (dokumen "Validasi Atribut").
PANJANG_MAKS_V: dict[str, int] = {
    "kdprov": 2,
    "kdkab": 2,
    "kdkec": 3,
    "kddesa": 3,
    "kdsls": 4,
    "kdsubsls": 2,
    "idsls": 14,
    "idsubsls": 16,
    "nmprov": 50,
    "nmkab": 50,
    "nmkec": 50,
    "nmdesa": 50,
    "nmsls": 100,
    "rw_dki": 3,
    "tingkat": 1,
    "nm_gedung": 50,
    "posisi": 50,
}

#: Alasan baris ``validasi_sls_unmatch``.
ALASAN_DUPLIKAT = "duplikat_di_peta"
ALASAN_TIDAK_DI_MASTER = "tidak_di_master"
ALASAN_TIDAK_DI_PETA = "tidak_di_peta"

#: Contoh idsls yang ditampilkan di pesan (tanpa rahasia).
CONTOH_N = 5


@dataclass
class TemuanSkema:
    """Satu pelanggaran skema (kolom + contoh nilai)."""

    kolom: str
    masalah: str
    contoh: list[str] = field(default_factory=list)


@dataclass
class HasilSkema:
    """Hasil blok skema."""

    lolos: bool
    kolom_hilang: list[str] = field(default_factory=list)
    temuan: list[TemuanSkema] = field(default_factory=list)
    jumlah_baris: int = 0


@dataclass
class HasilDuplikat:
    """Hasil blok duplikat ``idsls`` (14 digit) dan ``idsubsls`` (16 digit)."""

    lolos: bool
    jumlah_ganda: int = 0
    contoh: list[str] = field(default_factory=list)
    #: Duplikat di level SubSLS (aturan yang sama, kunci 16 digit).
    jumlah_ganda_sub: int = 0
    contoh_sub: list[str] = field(default_factory=list)


@dataclass
class BarisUnmatch:
    """Satu kode bermasalah untuk tabel/CSV (``idsls`` 14 digit atau ``idsubsls`` 16 digit)."""

    arah: str
    idsls: str
    nmsls: str | None
    alasan: str


@dataclass
class HasilMatching:
    """Hasil blok matching dua arah, di dua level (SLS dan SubSLS)."""

    lolos: bool
    unmatch_peta: list[BarisUnmatch] = field(default_factory=list)
    unmatch_master: list[BarisUnmatch] = field(default_factory=list)
    #: Selisih komposisi SubSLS di dalam SLS yang level SLS-nya cocok.
    unmatch_sub_peta: list[BarisUnmatch] = field(default_factory=list)
    unmatch_sub_master: list[BarisUnmatch] = field(default_factory=list)


@dataclass
class HasilValidasi:
    """Gabungan tiga blok + pesan ringkas untuk ``runs.pesan``."""

    lolos: bool
    skema: HasilSkema
    duplikat: HasilDuplikat
    matching: HasilMatching
    pesan: str


def normalisasi_idsls(nilai: Any) -> str | None:
    """Bersihkan ``idsls``: strip, buang ``.0`` ala Excel, kosong -> None."""
    if nilai is None:
        return None
    teks = str(nilai).strip()
    if not teks or teks.lower() in ("nan", "none", "nat"):
        return None
    if teks.endswith(".0") and teks[:-2].isdigit():
        teks = teks[:-2]
    return teks or None


def periksa_skema(
    kolom_ada: Mapping[str, Any] | Any,
    contoh_nilai: Mapping[str, list[Any]] | None = None,
) -> HasilSkema:
    """Cek kolom wajib + panjang data (murni, tanpa I/O).

    ``kolom_ada`` = daftar nama kolom (atau mapping nama->apa pun).
    ``contoh_nilai`` = mapping kolom -> daftar nilai untuk cek panjang/tipe.
    """
    names = list(kolom_ada.keys()) if isinstance(kolom_ada, Mapping) else list(kolom_ada)
    ada = {str(nama) for nama in names}
    hilang = [kolom for kolom in KOLOM_PETA_V if kolom not in ada]
    temuan: list[TemuanSkema] = []
    if contoh_nilai:
        for kolom in KOLOM_PETA_V:
            if kolom in hilang:
                continue
            maks = PANJANG_MAKS_V[kolom]
            buruk: list[str] = []
            for nilai in contoh_nilai.get(kolom, [])[:2000]:
                if nilai is None:
                    continue
                teks = str(nilai).strip()
                if not teks or teks.lower() in ("nan", "none", "nat"):
                    continue
                if kolom == "tingkat":
                    # Integer satu digit.
                    try:
                        angka = int(float(teks)) if "." in teks else int(teks)
                    except ValueError:
                        buruk.append(teks[:40])
                        continue
                    if len(str(abs(angka))) > maks:
                        buruk.append(teks[:40])
                elif len(teks) > maks:
                    buruk.append(teks[:60])
                if len(buruk) >= CONTOH_N:
                    break
            if buruk:
                temuan.append(
                    TemuanSkema(
                        kolom=kolom,
                        masalah=f"melebihi panjang {maks}",
                        contoh=buruk[:CONTOH_N],
                    )
                )
    lolos = not hilang and not temuan
    return HasilSkema(lolos=lolos, kolom_hilang=hilang, temuan=temuan)


def periksa_duplikat(idsls: list[str | None]) -> HasilDuplikat:
    """Cek ``idsls`` ganda (murni). Nilai kosong diabaikan di sini."""
    hitung: dict[str, int] = {}
    for nilai in idsls:
        if not nilai:
            continue
        hitung[nilai] = hitung.get(nilai, 0) + 1
    ganda = sorted(kode for kode, jumlah in hitung.items() if jumlah > 1)
    return HasilDuplikat(
        lolos=not ganda, jumlah_ganda=len(ganda), contoh=ganda[:CONTOH_N]
    )


def cocokkan(
    peta: Mapping[str, str | None],
    master: Mapping[str, str | None],
    duplikat_peta: set[str] | None = None,
) -> HasilMatching:
    """Matching dua arah peta vs master (murni, tanpa I/O).

    ``peta``/``master`` = mapping kode -> ``nmsls``; generik untuk dua level:
    ``idsls`` (14 digit) maupun ``idsubsls`` (16 digit).
    """
    ganda = duplikat_peta or set()
    himpunan_peta = set(peta)
    himpunan_master = set(master)
    hanya_peta = sorted(himpunan_peta - himpunan_master)
    hanya_master = sorted(himpunan_master - himpunan_peta)
    unmatch_peta = [
        BarisUnmatch(
            arah="peta",
            idsls=kode,
            nmsls=peta.get(kode),
            alasan=ALASAN_DUPLIKAT if kode in ganda else ALASAN_TIDAK_DI_MASTER,
        )
        for kode in hanya_peta
    ]
    # idsls ganda di peta walau ada di master tetap wajib diperbaiki
    # (aturan "idsls_count != 1"): tandai juga sebagai unmatch arah peta.
    for kode in sorted(ganda):
        if kode in himpunan_master and kode not in {satu.idsls for satu in unmatch_peta}:
            unmatch_peta.append(
                BarisUnmatch(
                    arah="peta",
                    idsls=kode,
                    nmsls=peta.get(kode),
                    alasan=ALASAN_DUPLIKAT,
                )
            )
    unmatch_peta.sort(key=lambda satu: satu.idsls)
    unmatch_master = [
        BarisUnmatch(
            arah="master",
            idsls=kode,
            nmsls=master.get(kode),
            alasan=ALASAN_TIDAK_DI_PETA,
        )
        for kode in hanya_master
    ]
    return HasilMatching(
        lolos=not unmatch_peta and not unmatch_master,
        unmatch_peta=unmatch_peta,
        unmatch_master=unmatch_master,
    )


def rangkum_pesan(
    skema: HasilSkema, duplikat: HasilDuplikat, matching: HasilMatching
) -> tuple[bool, str]:
    """Susun ringkasan 3 blok untuk ``runs.pesan`` (tanpa rahasia)."""
    bagian: list[str] = []
    if skema.lolos:
        bagian.append("skema: OK (17 kolom sesuai)")
    else:
        if skema.kolom_hilang:
            bagian.append(f"skema: GAGAL (kolom hilang: {', '.join(skema.kolom_hilang)})")
        else:
            rincian = "; ".join(
                f"{satu.kolom} {satu.masalah} (contoh: {', '.join(satu.contoh)})"
                for satu in skema.temuan
            )
            bagian.append(f"skema: GAGAL ({rincian})")
    if duplikat.lolos:
        bagian.append("duplikat: OK (idsls/idsubsls unik)")
    else:
        contoh = ", ".join(duplikat.contoh)
        bagian.append(
            f"duplikat: GAGAL ({duplikat.jumlah_ganda} idsls ganda; contoh: {contoh})"
            + (
                f"; {duplikat.jumlah_ganda_sub} idsubsls ganda; "
                f"contoh: {', '.join(duplikat.contoh_sub)}"
                if duplikat.jumlah_ganda_sub
                else ""
            )
        )
    if matching.lolos:
        bagian.append("matching: OK (peta <-> master cocok)")
    else:
        contoh_peta = ", ".join(satu.idsls for satu in matching.unmatch_peta[:CONTOH_N])
        contoh_master = ", ".join(
            satu.idsls for satu in matching.unmatch_master[:CONTOH_N]
        )
        bagian.append(
            "matching: GAGAL "
            f"(unmatch_peta={len(matching.unmatch_peta)}"
            + (f" contoh: {contoh_peta}" if contoh_peta else "")
            + f"; unmatch_master={len(matching.unmatch_master)}"
            + (f" contoh: {contoh_master}" if contoh_master else "")
            + (
                f"; unmatch_sub_peta={len(matching.unmatch_sub_peta)}"
                f"; unmatch_sub_master={len(matching.unmatch_sub_master)}"
                if matching.unmatch_sub_peta or matching.unmatch_sub_master
                else ""
            )
            + ")"
        )
    lolos = skema.lolos and duplikat.lolos and matching.lolos
    judul = "Validasi SLS 2026 S1: LOLOS" if lolos else "Validasi SLS 2026 S1: GAGAL"
    return lolos, f"{judul} — " + " | ".join(bagian)


def gabungkan_hasil(
    skema: HasilSkema, duplikat: HasilDuplikat, matching: HasilMatching
) -> HasilValidasi:
    """Gabungkan tiga blok + pesan."""
    lolos, pesan = rangkum_pesan(skema, duplikat, matching)
    return HasilValidasi(
        lolos=lolos, skema=skema, duplikat=duplikat, matching=matching, pesan=pesan
    )


# ---------------------------------------------------------------------------
# I/O (dipanggil worker; import berat di dalam fungsi)


def jalur_master(
    akar_master_sls: str | Path, kode_kab: str
) -> tuple[Path, Path]:
    """Jalur dua berkas Excel master untuk satu kabupaten (4 digit).

    Mendukung dua tata letak: langsung di ``<kdkab>/`` atau di subfolder
    ``<kdkab>/Master/`` + ``<kdkab>/Hirarki/`` (seperti folder lokal per kab).
    """
    akar = Path(akar_master_sls) / str(kode_kab).strip()
    langsung = (
        akar / f"msubsls_26_1_{kode_kab}.xlsx",
        akar / f"hirarki_sls_26_1_{kode_kab}.xlsx",
    )
    if langsung[0].exists():
        return langsung
    return (
        akar / "Master" / f"msubsls_26_1_{kode_kab}.xlsx",
        akar / "Hirarki" / f"hirarki_sls_26_1_{kode_kab}.xlsx",
    )


def baca_master(
    akar_master_sls: str | Path, kode_kab: str
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Baca master: mapping ``idsls`` -> ``nmsls`` + mapping ``idsubsls`` -> ``nmsls``.

    ``idsls`` diderivasi ``idsubsls[:14]``. Memakai ``msubsls`` (11-12 ribu
    baris) lewat ``openpyxl`` mode read-only supaya memori tetap kecil.
    ``hirarki_sls`` hanya dipakai sebagai pembanding bila berkasnya ada
    (himpunannya terbukti identik pada data 3302).
    """
    from openpyxl import load_workbook

    kode = str(kode_kab).strip()
    jalur_msubsls, _ = jalur_master(akar_master_sls, kode)
    if not jalur_msubsls.exists():
        raise FileNotFoundError(
            f"master msubsls untuk kabupaten/kota {kode} tidak ditemukan: {jalur_msubsls}"
        )
    wb = load_workbook(str(jalur_msubsls), read_only=True, data_only=True)
    try:
        ws = wb.active
        assert ws is not None
        baris = ws.iter_rows(values_only=True)
        kepala = [str(kolom).strip() if kolom is not None else "" for kolom in next(baris)]
        if "idsubsls" not in kepala:
            raise ValueError(
                f"kolom 'idsubsls' tidak ada di {jalur_msubsls.name} "
                f"(kolom: {', '.join(kepala[:12])}...)"
            )
        indeks = kepala.index("idsubsls")
        indeks_nama = kepala.index("nmsls") if "nmsls" in kepala else None
        master: dict[str, str | None] = {}
        master_sub: dict[str, str | None] = {}
        for satu in baris:
            if satu is None or indeks >= len(satu):
                continue
            subsls = normalisasi_idsls(satu[indeks])
            if not subsls:
                continue
            nama = None
            if indeks_nama is not None and indeks_nama < len(satu):
                mentah = satu[indeks_nama]
                nama = str(mentah).strip() if mentah is not None else None
            if len(subsls) == 16 and subsls.isdigit():
                master_sub.setdefault(subsls, nama or None)
            idsls = subsls[:14]
            if len(idsls) != 14 or not idsls.isdigit():
                continue
            master.setdefault(idsls, nama or None)
    finally:
        wb.close()
    if not master:
        raise ValueError(f"master {jalur_msubsls.name} tidak memuat idsls apa pun")
    return master, master_sub


def kolom_berkas_peta(berkas: str | Path, layer: str | None) -> list[str]:
    """Daftar kolom berkas peta (hanya metadata, tanpa baca baris)."""
    import pyogrio

    info = pyogrio.read_info(str(berkas), layer=layer)
    return [str(nama) for nama in info["fields"]]


def baca_peta(
    berkas: str | Path, layer: str | None
) -> tuple[
    dict[str, str | None],
    list[str | None],
    dict[str, list[Any]],
    list[str],
    str,
    str,
    dict[str, str | None],
    list[str | None],
]:
    """Baca atribut peta (tanpa geometri): mapping idsls->nmsls + daftar mentah.

    Kembalikan ``(peta, daftar_idsls, contoh_nilai, kolom, kdprov, kdkab,
    peta_sub, daftar_subsls)``. Dua terakhir untuk matching level SubSLS
    (16 digit). ``kolom`` = daftar nama kolom berkas; ``contoh_nilai`` =
    nilai per kolom untuk cek panjang (maks 2000 baris pertama sudah cukup).
    """
    import pyogrio

    jalur = Path(berkas)
    kolom = kolom_berkas_peta(jalur, layer)
    butuh = ["idsls", "idsubsls", "nmsls", "kdprov", "kdkab", *KOLOM_PETA_V]
    kolom_baca = [nama for nama in dict.fromkeys(butuh) if nama in kolom]
    data = pyogrio.read_dataframe(
        str(jalur), layer=layer, columns=kolom_baca, read_geometry=False
    )
    contoh: dict[str, list[Any]] = {
        nama: list(data[nama].head(2000)) if nama in data.columns else []
        for nama in KOLOM_PETA_V
        if nama in data.columns
    }
    mentah = list(data["idsls"]) if "idsls" in data.columns else []
    daftar = [normalisasi_idsls(nilai) for nilai in mentah]
    peta: dict[str, str | None] = {}
    nama_sls = (
        list(data["nmsls"]) if "nmsls" in data.columns else [None] * len(daftar)
    )
    for kode, nama in zip(daftar, nama_sls):
        if not kode:
            continue
        teks_nama = str(nama).strip() if nama is not None else None
        peta.setdefault(kode, teks_nama or None)
    mentah_sub = list(data["idsubsls"]) if "idsubsls" in data.columns else []
    daftar_sub = [normalisasi_idsls(nilai) for nilai in mentah_sub]
    peta_sub: dict[str, str | None] = {}
    nama_sub = (
        list(data["nmsls"]) if "nmsls" in data.columns else [None] * len(daftar_sub)
    )
    for kode, nama in zip(daftar_sub, nama_sub):
        if not kode:
            continue
        teks_nama = str(nama).strip() if nama is not None else None
        peta_sub.setdefault(kode, teks_nama or None)

    def _tunggal(nama: str) -> str:
        if nama not in data.columns:
            return ""
        unik = sorted(
            {str(nilai).strip() for nilai in data[nama].dropna() if str(nilai).strip()}
        )
        return unik[0] if len(unik) == 1 else (unik[0] if unik else "")

    kdprov = _tunggal("kdprov")
    kdkab = _tunggal("kdkab")
    return peta, daftar, contoh, kolom, kdprov, kdkab, peta_sub, daftar_sub


def validasi_berkas(
    berkas: str | Path,
    layer: str | None,
    akar_master_sls: str | Path,
    kode_kab: str | None = None,
) -> HasilValidasi:
    """Jalankan tiga blok validasi untuk satu berkas peta (dipakai worker)."""
    peta, daftar, contoh, kolom, kdprov, kdkab, peta_sub, daftar_sub = baca_peta(
        berkas, layer
    )
    skema = periksa_skema(kolom, contoh)
    skema.jumlah_baris = len(daftar)
    # Satu job hanya satu kabupaten/kota.
    if kdprov and kdkab:
        kode_aktual = f"{kdprov[:2]}{kdkab}" if len(str(kdkab)) == 2 else str(kdkab)
        if kode_kab and kode_aktual != str(kode_kab):
            skema.lolos = False
            skema.temuan.append(
                TemuanSkema(
                    kolom="kdkab",
                    masalah=f"campur kabupaten ({kode_aktual} != {kode_kab})",
                    contoh=[kode_aktual],
                )
            )
    duplikat = periksa_duplikat(daftar)
    duplikat_sub = periksa_duplikat(daftar_sub)
    duplikat = HasilDuplikat(
        lolos=duplikat.lolos and duplikat_sub.lolos,
        jumlah_ganda=duplikat.jumlah_ganda,
        contoh=duplikat.contoh,
        jumlah_ganda_sub=duplikat_sub.jumlah_ganda,
        contoh_sub=duplikat_sub.contoh,
    )
    kode_master = str(kode_kab or "").strip()
    if not kode_master and kdkab:
        kode_master = f"{kdprov[:2]}{kdkab}" if kdprov and len(str(kdkab)) == 2 else str(kdkab)
    if kode_master:
        master, master_sub = baca_master(akar_master_sls, kode_master)
    else:
        master, master_sub = {}, {}
    ganda_sls = set(duplikat.contoh) | {
        kode
        for kode in peta
        if sum(1 for nilai in daftar if nilai == kode) > 1
    }
    ganda_sub = set(duplikat.contoh_sub) | {
        kode
        for kode in peta_sub
        if sum(1 for nilai in daftar_sub if nilai == kode) > 1
    }
    cocok_sls = cocokkan(peta, master, ganda_sls)
    cocok_sub = cocokkan(peta_sub, master_sub, ganda_sub)
    matching = HasilMatching(
        lolos=cocok_sls.lolos and cocok_sub.lolos,
        unmatch_peta=cocok_sls.unmatch_peta,
        unmatch_master=cocok_sls.unmatch_master,
        unmatch_sub_peta=cocok_sub.unmatch_peta,
        unmatch_sub_master=cocok_sub.unmatch_master,
    )
    return gabungkan_hasil(skema, duplikat, matching)
