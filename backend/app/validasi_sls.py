"""Validasi peta SLS/SubSLS 2026 Semester 1 (tipe run V, PRD §11).

Empat blok, tanpa geometri (pengganti langkah poligon ``Cek_Master_PetaSLS``):

1. **Skema atribut**: peta wajib punya 17 field sesuai dokumen "Validasi
   Atribut" (``kdprov``..``posisi``) dengan panjang data sesuai tabel.
   ``tingkat`` bertipe integer, sisanya string.
2. **Pasangan ganda**: pasangan ``(idsls, idsubsls)`` yang sama persis tidak
   boleh muncul lebih dari sekali (satu ``idsls`` boleh di banyak baris
   selama ``idsubsls``-nya beda).
3. **Konsistensi susunan kode**: ``idsls`` harus sama dengan gabungan
   ``kdprov+kdkab+kdkec+kddesa+kdsls``, dan ``idsubsls`` harus sama dengan
   ``idsls+kdsubsls``. Baris yang tidak cocok dicatat ``tidak_konsisten``
   dan tidak ikut matching (kodenya sendiri kontradiktif, percuma
   dicocokkan ke master).
4. **Matching pasangan lawan master**: pasangan ``(idsls, idsubsls)``
   peta vs master. Pasangan yang sama persis = cocok; yang
   ``idsubsls``-nya dikenal di bawah ``idsls`` berbeda = kolom ``idsls``
   salah; selebihnya = tidak ada di master / tidak ada di peta.

Modul ini **ringan saat startup**: ``pyogrio``/``openpyxl`` hanya diimpor di
dalam fungsi (dipakai worker), supaya proses API tetap ringan (PRD §8).

Steril dari SE2026: tidak menyentuh ``wilayah``/``titik_hasil``/rekap, tidak
ikut hitung nomor job A/B, dan tidak menjadi sumber peta Proses B.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
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

#: Contoh kode yang ditampilkan di pesan (tanpa rahasia).
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
    """Hasil blok duplikat pasangan ``idsls``+``idsubsls``.

    Satu SLS boleh muncul di banyak baris selama tiap baris punya ``idsubsls``
    berbeda; yang dilarang adalah pasangan yang sama persis muncul lebih dari
    sekali. ``contoh`` memakai kunci gabungan ``"idsls|idsubsls"``.
    """

    lolos: bool
    jumlah_ganda: int = 0
    contoh: list[str] = field(default_factory=list)


#: Jenis temuan unmatch (satu baris = satu sheet di unduhan Excel).
JENIS_TIDAK_DI_PETA = "tidak_di_peta"
JENIS_TIDAK_DI_MASTER = "tidak_di_master"
JENIS_GANDA = "ganda"
JENIS_NAMA_BEDA = "nama_beda"
JENIS_TIDAK_KONSISTEN = "tidak_konsisten"
JENIS_GEOM_INVALID = "geom_invalid"
JENIS_GEOM_DUPLIKAT = "geom_duplikat"
JENIS_GEOM_OVERLAP = "geom_overlap"
JENIS_GEOM_GAP = "geom_gap"


@dataclass
class BarisUnmatch:
    """Satu temuan untuk tabel/unduhan: pasangan sisi peta vs sisi master.

    Sisi yang kosong berarti tidak ada di sisi itu. ``jenis`` menentukan sheet:
    ``tidak_di_peta`` (tambah di QGIS), ``tidak_di_master`` (kode asing),
    ``ganda`` (baris rangkap), ``nama_beda`` (ejaan nama), ``tidak_konsisten``
    (``idsls``/``idsubsls`` tidak cocok susunan ``kdprov``..``kdsubsls``).
    """

    jenis: str
    idsls_peta: str | None
    idsubsls_peta: str | None
    idsls_master: str | None
    idsubsls_master: str | None
    nmsls: str | None
    catatan: str | None = None


@dataclass
class HasilMatching:
    """Hasil blok matching: daftar temuan siap simpan/ekspor."""

    lolos: bool
    temuan: list[BarisUnmatch] = field(default_factory=list)


@dataclass
class HasilTopologi:
    """Hasil blok Topology Checker (4 aturan QGIS)."""

    lolos: bool = True
    jumlah_invalid: int = 0
    jumlah_duplikat: int = 0
    jumlah_overlap: int = 0
    jumlah_gap: int = 0
    temuan: list[BarisUnmatch] = field(default_factory=list)


@dataclass
class HasilValidasi:
    """Gabungan lima blok + pesan ringkas untuk ``runs.pesan``."""

    lolos: bool
    skema: HasilSkema
    duplikat: HasilDuplikat
    konsistensi: HasilKonsistensi
    matching: HasilMatching
    pesan: str
    topologi: HasilTopologi = field(default_factory=HasilTopologi)


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
            baris_pertama: int | None = None
            for urut, nilai in enumerate(contoh_nilai.get(kolom, []), start=1):
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
                    else:
                        if len(str(abs(angka))) > maks:
                            buruk.append(teks[:40])
                elif kolom in ("idsls", "idsubsls"):
                    # Kode wilayah panjangnya pasti (14 digit SLS, 16 digit
                    # SubSLS); buang ".0" ala Excel seperti normalisasi_idsls.
                    bersih = teks
                    if bersih.endswith(".0") and bersih[:-2].isdigit():
                        bersih = bersih[:-2]
                    if len(bersih) != maks or not bersih.isdigit():
                        buruk.append(teks[:60])
                elif len(teks) > maks:
                    buruk.append(teks[:60])
                if buruk and baris_pertama is None:
                    baris_pertama = urut
                if len(buruk) >= CONTOH_N:
                    break
            if buruk:
                if kolom in ("idsls", "idsubsls"):
                    masalah = (
                        f"harus tepat {maks} digit "
                        f"(pertama di baris {baris_pertama})"
                    )
                else:
                    masalah = (
                        f"melebihi panjang {maks} "
                        f"(pertama di baris {baris_pertama})"
                    )
                temuan.append(
                    TemuanSkema(
                        kolom=kolom,
                        masalah=masalah,
                        contoh=buruk[:CONTOH_N],
                    )
                )
    lolos = not hilang and not temuan
    return HasilSkema(lolos=lolos, kolom_hilang=hilang, temuan=temuan)


def periksa_duplikat(idsls: list[str | None]) -> HasilDuplikat:
    """Cek kunci ganda (murni). Nilai kosong diabaikan di sini."""
    hitung: dict[str, int] = {}
    for nilai in idsls:
        if not nilai:
            continue
        hitung[nilai] = hitung.get(nilai, 0) + 1
    ganda = sorted(kode for kode, jumlah in hitung.items() if jumlah > 1)
    return HasilDuplikat(
        lolos=not ganda, jumlah_ganda=len(ganda), contoh=ganda[:CONTOH_N]
    )


def kunci_pasangan(idsls: str | None, idsubsls: str | None) -> str:
    """Kunci gabungan pasangan untuk blok duplikat (``"idsls|idsubsls"``)."""
    return f"{idsls or ''}|{idsubsls or ''}"


@dataclass
class HasilKonsistensi:
    """Hasil blok konsistensi susunan kode + pasangan yang dikecualikan.

    ``pasangan_buruk`` = pasangan ``(idsls, idsubsls)`` yang kodenya
    kontradiktif; tidak ikut matching supaya tidak mengotori hitungan
    ``tidak_di_master``/``tidak_di_peta`` dengan kode yang memang salah ketik.
    """

    lolos: bool
    temuan: list[BarisUnmatch] = field(default_factory=list)
    pasangan_buruk: set[tuple[str, str]] = field(default_factory=set)


#: Panjang digit tiap potongan kode penyusun ``idsls``/``idsubsls``.
PANJANG_SUSUNAN_V: dict[str, int] = {
    "kdprov": 2,
    "kdkab": 2,
    "kdkec": 3,
    "kddesa": 3,
    "kdsls": 4,
    "kdsubsls": 2,
}


def periksa_konsistensi(atribut: list[dict[str, str]]) -> HasilKonsistensi:
    """Cek susunan kode per baris peta (murni, tanpa I/O).

    ``atribut`` = daftar baris ``{"kode", "sub", "kdprov", ..., "nama"}``
    (lihat :func:`baca_peta`). Syarat dinilai: semua potongan terisi dengan
    panjang digit yang tepat (``kdkab`` boleh 2/4 digit, dipakai 2 digit
    terakhir) serta ``idsls`` 14 digit dan ``idsubsls`` 16 digit. Baris yang
    tidak memenuhi syarat dilewati di sini karena sudah gagal di blok skema;
    baris kosong tidak masuk daftar ini.
    """
    temuan: list[BarisUnmatch] = []
    buruk: set[tuple[str, str]] = set()
    for baris in atribut:
        kode = baris.get("kode", "")
        sub = baris.get("sub", "")
        if not kode and not sub:
            continue
        potong = {nama: baris.get(nama, "") for nama in PANJANG_SUSUNAN_V}
        kdkab = potong["kdkab"]
        ekor_kab = kdkab[-2:] if len(kdkab) in (2, 4) else ""
        if not (
            len(potong["kdprov"]) == 2
            and potong["kdprov"].isdigit()
            and ekor_kab
            and ekor_kab.isdigit()
            and len(potong["kdkec"]) == 3
            and potong["kdkec"].isdigit()
            and len(potong["kddesa"]) == 3
            and potong["kddesa"].isdigit()
            and len(potong["kdsls"]) == 4
            and potong["kdsls"].isdigit()
            and len(potong["kdsubsls"]) == 2
            and potong["kdsubsls"].isdigit()
            and len(kode) == 14
            and kode.isdigit()
            and len(sub) == 16
            and sub.isdigit()
        ):
            continue
        harapan_sls = (
            potong["kdprov"] + ekor_kab + potong["kdkec"] + potong["kddesa"] + potong["kdsls"]
        )
        harapan_sub = harapan_sls + potong["kdsubsls"]
        nama = baris.get("nama") or None
        if kode != harapan_sls:
            temuan.append(
                BarisUnmatch(
                    jenis=JENIS_TIDAK_KONSISTEN,
                    idsls_peta=kode,
                    idsubsls_peta=sub,
                    idsls_master=None,
                    idsubsls_master=None,
                    nmsls=nama,
                    catatan=f"idsls tidak cocok susunan kode (harusnya {harapan_sls})",
                )
            )
            buruk.add((kode, sub))
        if sub != harapan_sub:
            temuan.append(
                BarisUnmatch(
                    jenis=JENIS_TIDAK_KONSISTEN,
                    idsls_peta=kode,
                    idsubsls_peta=sub,
                    idsls_master=None,
                    idsubsls_master=None,
                    nmsls=nama,
                    catatan=f"idsubsls tidak cocok susunan kode (harusnya {harapan_sub})",
                )
            )
            buruk.add((kode, sub))
    return HasilKonsistensi(lolos=not temuan, temuan=temuan, pasangan_buruk=buruk)


def rapikan_nama(nilai: str | None) -> str:
    """Normalisasi ringan nama untuk perbandingan: tanpa spasi berlebih.

    Perbandingan huruf besar/kecil tetap sensitif: nama peta harus persis
    sama ejaannya dengan nama di master.
    """
    return " ".join(str(nilai or "").split())


def bandingkan(
    peta: Mapping[tuple[str, str], str | None],
    master: Mapping[tuple[str, str], str | None],
    hitung_peta: Mapping[tuple[str, str], int] | None = None,
) -> HasilMatching:
    """Bandingkan pasangan ``(idsls, idsubsls)`` peta vs master (murni).

    Tiap pasangan berbeda dilaporkan tepat sekali: pasangan peta yang sama
    persis di master = cocok; selebihnya = ``tidak_di_master``; pasangan
    master yang tak muncul di peta = ``tidak_di_peta``; pasangan peta yang
    muncul >1x = ``ganda``. Nilai 16 digit di kolom ``idsls`` tidak mendapat
    perlakuan khusus: ia tetap ``tidak_di_master`` karena memang tidak
    terdaftar sebagai SLS, plus catatan bahwa kolomnya salah isi.
    """
    hitung = dict(hitung_peta or {})
    temuan: list[BarisUnmatch] = []
    sisa_master = dict(master)
    induk_master = {kode for kode, _sub in master}
    for pasang in sorted(peta):
        idsls, subsls = pasang
        nama = peta[pasang]
        if pasang in sisa_master:
            del sisa_master[pasang]
            if hitung.get(pasang, 1) > 1:
                temuan.append(
                    BarisUnmatch(
                        jenis=JENIS_GANDA,
                        idsls_peta=idsls or None,
                        idsubsls_peta=subsls or None,
                        idsls_master=idsls or None,
                        idsubsls_master=subsls or None,
                        nmsls=nama,
                        catatan=f"{hitung[pasang]} baris",
                    )
                )
            if rapikan_nama(nama) != rapikan_nama(master[pasang]):
                temuan.append(
                    BarisUnmatch(
                        jenis=JENIS_NAMA_BEDA,
                        idsls_peta=idsls or None,
                        idsubsls_peta=subsls or None,
                        idsls_master=idsls or None,
                        idsubsls_master=subsls or None,
                        nmsls=nama,
                        catatan=f'master: "{(master[pasang] or "").strip()}"',
                    )
                )
            continue
        catatan: list[str] = []
        if hitung.get(pasang, 1) > 1:
            catatan.append(f"ganda di peta ({hitung[pasang]} baris)")
        if idsls and (len(idsls) != 14 or not idsls.isdigit()):
            catatan.append("kolom idsls bukan kode SLS 14 digit")
        elif (
            idsls
            and subsls
            and idsls in induk_master
        ):
            catatan.append("induk terdaftar di master (kemungkinan subsls baru hasil pemekaran)")
        temuan.append(
            BarisUnmatch(
                jenis=JENIS_TIDAK_DI_MASTER,
                idsls_peta=idsls or None,
                idsubsls_peta=subsls or None,
                idsls_master=None,
                idsubsls_master=None,
                nmsls=nama,
                catatan="; ".join(catatan) or None,
            )
        )
    for pasang in sorted(sisa_master):
        idsls, subsls = pasang
        temuan.append(
            BarisUnmatch(
                jenis=JENIS_TIDAK_DI_PETA,
                idsls_peta=None,
                idsubsls_peta=None,
                idsls_master=idsls or None,
                idsubsls_master=subsls or None,
                nmsls=master[pasang],
            )
        )
    return HasilMatching(lolos=not temuan, temuan=temuan)


def periksa_topologi(
    geometri: list[Any],
    atribut: list[dict[str, str]] | None = None,
) -> HasilTopologi:
    """Jalankan 4 aturan QGIS Topology Checker pada geometri poligon.

    Aturan yang direplikasi persis dari ``src/plugins/topology/topolTest.cpp``:

    - ``must not have invalid geometries`` (``checkValid``)
    - ``must not have duplicates`` (``checkDuplicates``)
    - ``must not overlap`` (``checkOverlaps``)
    - ``must not have gaps`` (``checkGaps``)

    Fitur bergeometri bukan poligon (mis. titik pada data uji sintetis)
    diabaikan agar tes non-poligon tetap berjalan mulus.
    """
    import shapely
    from shapely import STRtree
    from shapely.validation import explain_validity

    baris_atribut = atribut or []

    def _info_baris(indeks: int) -> tuple[str | None, str | None, str | None]:
        if indeks < len(baris_atribut):
            info = baris_atribut[indeks]
            return (
                info.get("kode") or None,
                info.get("sub") or None,
                info.get("nama") or None,
            )
        return None, None, None

    poligon_indeks: list[int] = []
    for urut, geom in enumerate(geometri):
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            poligon_indeks.append(urut)

    if not poligon_indeks:
        return HasilTopologi(lolos=True)

    temuan: list[BarisUnmatch] = []

    # 1. must not have invalid geometries (checkValid)
    valid_map: dict[int, bool] = {}
    jumlah_invalid = 0
    for urut in poligon_indeks:
        geom = geometri[urut]
        valid = bool(shapely.is_valid(geom))
        valid_map[urut] = valid
        if not valid:
            jumlah_invalid += 1
            idsls, idsubsls, nama = _info_baris(urut)
            alasan = explain_validity(geom)
            temuan.append(
                BarisUnmatch(
                    jenis=JENIS_GEOM_INVALID,
                    idsls_peta=idsls,
                    idsubsls_peta=idsubsls,
                    idsls_master=None,
                    idsubsls_master=None,
                    nmsls=nama,
                    catatan=f"baris {urut + 1}: {alasan}"[:255],
                )
            )

    # Indeks spasial bounding-box seperti QgsSpatialIndex di QGIS.
    kotak = [shapely.box(*geometri[urut].bounds) for urut in poligon_indeks]
    pohon = STRtree(kotak)

    # 2. must not have duplicates (checkDuplicates)
    duplikat_lewati: set[int] = set()
    jumlah_duplikat = 0
    for pos_a, urut_a in enumerate(poligon_indeks):
        if urut_a in duplikat_lewati:
            continue
        geom_a = geometri[urut_a]
        for pos_b in pohon.query(kotak[pos_a], predicate="intersects"):
            pos_b = int(pos_b)
            urut_b = poligon_indeks[pos_b]
            if urut_b == urut_a:
                continue
            geom_b = geometri[urut_b]
            if shapely.equals(geom_a, geom_b):
                duplikat_lewati.add(urut_b)
                jumlah_duplikat += 1
                idsls_a, idsubsls_a, nama_a = _info_baris(urut_a)
                _idsls_b, idsubsls_b, _nama_b = _info_baris(urut_b)
                lawan = idsubsls_b or f"baris {urut_b + 1}"
                temuan.append(
                    BarisUnmatch(
                        jenis=JENIS_GEOM_DUPLIKAT,
                        idsls_peta=idsls_a,
                        idsubsls_peta=idsubsls_a,
                        idsls_master=None,
                        idsubsls_master=None,
                        nmsls=nama_a,
                        catatan=f"geometri duplikat dengan {lawan}"[:255],
                    )
                )

    # 3. must not overlap (checkOverlaps)
    overlap_lewati: set[int] = set()
    jumlah_overlap = 0
    for pos_a, urut_a in enumerate(poligon_indeks):
        if urut_a in overlap_lewati or not valid_map[urut_a]:
            continue
        geom_a = geometri[urut_a]
        shapely.prepare(geom_a)
        for pos_b in pohon.query(kotak[pos_a], predicate="intersects"):
            pos_b = int(pos_b)
            urut_b = poligon_indeks[pos_b]
            if urut_b == urut_a or not valid_map[urut_b]:
                continue
            geom_b = geometri[urut_b]
            if shapely.overlaps(geom_a, geom_b):
                overlap_lewati.add(urut_b)
                jumlah_overlap += 1
                idsls_a, idsubsls_a, nama_a = _info_baris(urut_a)
                _idsls_b, idsubsls_b, _nama_b = _info_baris(urut_b)
                lawan = idsubsls_b or f"baris {urut_b + 1}"
                temuan.append(
                    BarisUnmatch(
                        jenis=JENIS_GEOM_OVERLAP,
                        idsls_peta=idsls_a,
                        idsubsls_peta=idsubsls_a,
                        idsls_master=None,
                        idsubsls_master=None,
                        nmsls=nama_a,
                        catatan=f"tumpang tindih dengan {lawan}"[:255],
                    )
                )

    # 4. must not have gaps (checkGaps)
    potongan_valid = [
        bagian
        for urut in poligon_indeks
        if valid_map[urut]
        for bagian in shapely.get_parts(geometri[urut])
    ]
    jumlah_gap = 0
    if potongan_valid:
        gabungan = shapely.unary_union(potongan_valid)
        if not gabungan.is_empty:
            batas = shapely.box(*gabungan.bounds).buffer(2, quad_segs=3)
            selisih = shapely.difference(batas, gabungan)
            daftar_celah = list(shapely.get_parts(selisih))[1:]
            jumlah_gap = len(daftar_celah)
            for nomor_celah, celah in enumerate(daftar_celah, start=1):
                titik = celah.representative_point()
                kandidat = [
                    poligon_indeks[int(pos)]
                    for pos in pohon.query(
                        shapely.box(*celah.bounds), predicate="intersects"
                    )
                    if shapely.intersects(
                        geometri[poligon_indeks[int(pos)]], celah.buffer(1e-7)
                    )
                ]
                idsls_c: str | None = None
                idsubsls_c: str | None = None
                nama_c: str | None = None
                sekitar: list[str] = []
                for urut_k in kandidat[:3]:
                    s_sls, s_sub, s_nama = _info_baris(urut_k)
                    if idsls_c is None and (s_sls or s_sub):
                        idsls_c, idsubsls_c, nama_c = s_sls, s_sub, s_nama
                    if s_sub and s_sub not in sekitar:
                        sekitar.append(s_sub)
                info_sekitar = (
                    f" sekitar {', '.join(sekitar)}" if sekitar else ""
                )
                temuan.append(
                    BarisUnmatch(
                        jenis=JENIS_GEOM_GAP,
                        idsls_peta=idsls_c,
                        idsubsls_peta=idsubsls_c,
                        idsls_master=None,
                        idsubsls_master=None,
                        nmsls=nama_c,
                        catatan=(
                            f"celah #{nomor_celah} di ({titik.y:.6f}, "
                            f"{titik.x:.6f}){info_sekitar}"
                        )[:255],
                    )
                )

    lolos = (
        jumlah_invalid == 0
        and jumlah_duplikat == 0
        and jumlah_overlap == 0
        and jumlah_gap == 0
    )
    return HasilTopologi(
        lolos=lolos,
        jumlah_invalid=jumlah_invalid,
        jumlah_duplikat=jumlah_duplikat,
        jumlah_overlap=jumlah_overlap,
        jumlah_gap=jumlah_gap,
        temuan=temuan,
    )


def rangkum_pesan(
    skema: HasilSkema,
    duplikat: HasilDuplikat,
    konsistensi: HasilKonsistensi,
    matching: HasilMatching,
    baris_kosong: int = 0,
    topologi: HasilTopologi | None = None,
) -> tuple[bool, str]:
    """Susun ringkasan per blok, satu blok satu baris (tanpa rahasia)."""
    bagian: list[str] = []
    if skema.lolos:
        bagian.append(
            "Validasi Kelengkapan Atribut: Sukses \u2014 "
            "17 kolom wajib sudah ada pada peta Anda."
        )
    elif skema.kolom_hilang:
        bagian.append(
            "Validasi Kelengkapan Atribut: Gagal \u2014 "
            f"kolom hilang: {', '.join(skema.kolom_hilang)}."
        )
    else:
        rincian = "; ".join(
            f"{satu.kolom} {satu.masalah} (contoh: {', '.join(satu.contoh)})"
            for satu in skema.temuan
        )
        bagian.append(f"Validasi Kelengkapan Atribut: Gagal \u2014 {rincian}.")
    if duplikat.lolos:
        bagian.append(
            "Validasi Duplikat: Sukses \u2014 "
            "tidak ada pasangan idsls+idsubsls yang ganda."
        )
    else:
        contoh = ", ".join(duplikat.contoh)
        bagian.append(
            f"Validasi Duplikat: Gagal \u2014 "
            f"{duplikat.jumlah_ganda} pasangan ganda; contoh: {contoh}."
        )
    if baris_kosong:
        bagian.append(
            f"Catatan: {baris_kosong} baris kosong dilewati (tidak ikut validasi)."
        )
    if konsistensi.lolos:
        bagian.append(
            "Validasi Konsistensi Kode: Sukses \u2014 "
            "idsls/idsubsls cocok susunan kdprov..kdsubsls."
        )
    else:
        contoh = ", ".join(
            satu.idsubsls_peta or satu.idsls_peta or "-"
            for satu in konsistensi.temuan[: CONTOH_N]
        )
        bagian.append(
            "Validasi Konsistensi Kode: Gagal \u2014 "
            f"{len(konsistensi.temuan)} baris tidak cocok susunan kode; "
            f"contoh: {contoh}. Perbaiki kolom kode di QGIS lalu unggah ulang."
        )
    if matching.lolos:
        bagian.append(
            "Validasi Matching dengan Master MFD: Sukses \u2014 "
            "peta cocok dengan master (0 temuan)."
        )
    else:
        hitung_jenis: dict[str, int] = {}
        contoh_jenis: dict[str, list[BarisUnmatch]] = {}
        for satu in matching.temuan:
            hitung_jenis[satu.jenis] = hitung_jenis.get(satu.jenis, 0) + 1
            contoh_jenis.setdefault(satu.jenis, []).append(satu)
        label_jenis = {
            JENIS_TIDAK_DI_PETA: "tidak ada di peta",
            JENIS_TIDAK_DI_MASTER: "tidak ada di master",
            JENIS_GANDA: "ganda",
            JENIS_NAMA_BEDA: "nama beda",
        }
        rincian = "; ".join(
            f"{label_jenis.get(jenis, jenis)}={hitung_jenis.get(jenis, 0)}"
            for jenis in (JENIS_TIDAK_DI_PETA, JENIS_TIDAK_DI_MASTER, JENIS_GANDA, JENIS_NAMA_BEDA)
        )
        bagian.append(f"Validasi Matching dengan Master MFD: Gagal \u2014 {rincian}.")
        for jenis in (JENIS_TIDAK_DI_PETA, JENIS_TIDAK_DI_MASTER, JENIS_GANDA, JENIS_NAMA_BEDA):
            contoh = contoh_jenis.get(jenis, [])[:3]
            if contoh:
                kode = ", ".join(
                    satu.idsubsls_peta
                    or satu.idsubsls_master
                    or satu.idsls_peta
                    or satu.idsls_master
                    or "-"
                    for satu in contoh
                )
                bagian.append(f"Contoh {label_jenis[jenis]}: {kode}.")
        if hitung_jenis.get(JENIS_GANDA, 0) >= 20:
            bagian.append(
                "Kemungkinan 2 layer tergabung (banyak pasangan ganda): "
                "periksa/buang layer ganda di QGIS sebelum ekspor ulang."
            )
    topo = topologi if topologi is not None else HasilTopologi(lolos=True)
    if topologi is not None:
        if topo.lolos:
            bagian.append(
                "Validasi Topologi (Topology Checker): Sukses \u2014 "
                "tidak ada celah (gap), tumpang tindih (overlap), duplikat geometri, "
                "atau geometri tidak valid."
            )
        else:
            rincian_topo = (
                f"celah (gap)={topo.jumlah_gap}; "
                f"tumpang tindih (overlap)={topo.jumlah_overlap}; "
                f"duplikat geometri={topo.jumlah_duplikat}; "
                f"geometri tidak valid={topo.jumlah_invalid}"
            )
            bagian.append(
                f"Validasi Topologi (Topology Checker): Gagal \u2014 {rincian_topo}."
            )
    if not matching.lolos or not topo.lolos:
        bagian.append(
            "Unduh rincian Excel di halaman Riwayat, perbaiki di QGIS, lalu unggah ulang."
        )
    lolos = (
        skema.lolos
        and duplikat.lolos
        and konsistensi.lolos
        and matching.lolos
        and topo.lolos
    )
    judul = "Validasi SLS 2026 S1: LOLOS" if lolos else "Validasi SLS 2026 S1: GAGAL"
    return lolos, judul + "\n" + "\n".join(bagian)


def gabungkan_hasil(
    skema: HasilSkema,
    duplikat: HasilDuplikat,
    konsistensi: HasilKonsistensi,
    matching: HasilMatching,
    baris_kosong: int = 0,
    topologi: HasilTopologi | None = None,
) -> HasilValidasi:
    """Gabungkan lima blok + pesan."""
    lolos, pesan = rangkum_pesan(
        skema,
        duplikat,
        konsistensi,
        matching,
        baris_kosong=baris_kosong,
        topologi=topologi,
    )
    return HasilValidasi(
        lolos=lolos,
        skema=skema,
        duplikat=duplikat,
        konsistensi=konsistensi,
        matching=matching,
        pesan=pesan,
        topologi=topologi if topologi is not None else HasilTopologi(lolos=True),
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


def baca_master_impor(
    jalur_msubsls: str | Path,
) -> tuple[dict[tuple[str, str], str | None], int, int, list[str]]:
    """Baca satu berkas msubsls untuk impor ke database.

    Kembalikan ``(mapping pasangan -> nmsls, total_baris, baris_dilewati,
    contoh)``. Hanya baris dengan ``idsubsls`` 16 digit yang dipakai; sisanya
    dihitung sebagai dilewati beserta contohnya untuk laporan impor.
    """
    from openpyxl import load_workbook

    jalur = Path(jalur_msubsls)
    wb = load_workbook(str(jalur), read_only=True, data_only=True)
    try:
        ws = wb.active
        assert ws is not None
        baris = ws.iter_rows(values_only=True)
        kepala = [str(kolom).strip() if kolom is not None else "" for kolom in next(baris)]
        if "idsubsls" not in kepala:
            raise ValueError(
                f"kolom 'idsubsls' tidak ada di {jalur.name} "
                f"(kolom: {', '.join(kepala[:12])}...)"
            )
        indeks = kepala.index("idsubsls")
        indeks_nama = kepala.index("nmsls") if "nmsls" in kepala else None
        master: dict[tuple[str, str], str | None] = {}
        dilewati = 0
        contoh_lewat: list[str] = []
        total_baris = 0
        for satu in baris:
            if satu is None or indeks >= len(satu):
                continue
            total_baris += 1
            subsls = normalisasi_idsls(satu[indeks])
            if not subsls:
                dilewati += 1
                continue
            if len(subsls) != 16 or not subsls.isdigit():
                dilewati += 1
                if len(contoh_lewat) < 3:
                    mentah = satu[indeks]
                    contoh_lewat.append(
                        str(mentah).strip() if mentah is not None else ""
                    )
                continue
            idsls = subsls[:14]
            nama = None
            if indeks_nama is not None and indeks_nama < len(satu):
                mentah = satu[indeks_nama]
                nama = str(mentah).strip() if mentah is not None else None
            master.setdefault((idsls, subsls), nama or None)
    finally:
        wb.close()
    return master, total_baris, dilewati, contoh_lewat


def kolom_berkas_peta(berkas: str | Path, layer: str | None) -> list[str]:
    """Daftar kolom berkas peta (hanya metadata, tanpa baca baris)."""
    import pyogrio

    info = pyogrio.read_info(str(berkas), layer=layer)
    return [str(nama) for nama in info["fields"]]


def baca_peta(
    berkas: str | Path, layer: str | None
) -> tuple[
    dict[tuple[str, str], str | None],
    list[tuple[str, str]],
    dict[str, list[Any]],
    list[str],
    str,
    str,
    int,
    list[dict[str, str]],
]:
    """Baca atribut peta (tanpa geometri): pasangan ``(idsls, idsubsls)``.

    Kembalikan ``(peta, pasangan, contoh_nilai, kolom, kdprov, kdkab,
    baris_kosong, atribut)``. ``peta`` = mapping pasangan -> ``nmsls``
    (kunci kosong ``""`` bila kolomnya kosong); ``pasangan`` = daftar semua
    pasangan termasuk rangkap (untuk hitung duplikat); ``kolom`` = daftar
    nama kolom berkas; ``contoh_nilai`` = nilai per kolom untuk cek panjang
    (seluruh baris dipindai); ``atribut`` = satu dict per baris tak-kosong
    (``kode``, ``sub``, potongan ``kdprov``..``kdsubsls`` yang dinormalisasi,
    ``nama``) untuk blok konsistensi.
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
        nama: list(data[nama]) if nama in data.columns else []
        for nama in KOLOM_PETA_V
        if nama in data.columns
    }
    mentah_idsls = list(data["idsls"]) if "idsls" in data.columns else []
    mentah_sub = list(data["idsubsls"]) if "idsubsls" in data.columns else []
    if "nmsls" in data.columns:
        mentah_nama: list = list(data["nmsls"])
    else:
        mentah_nama = [None] * max(len(mentah_idsls), len(mentah_sub))
    jumlah = max(len(mentah_idsls), len(mentah_sub), len(mentah_nama))
    seri_potong = {
        nama: list(data[nama]) if nama in data.columns else []
        for nama in PANJANG_SUSUNAN_V
    }
    peta: dict[tuple[str, str], str | None] = {}
    pasangan: list[tuple[str, str]] = []
    atribut: list[dict[str, str]] = []
    baris_kosong = 0
    for urut in range(jumlah):
        mentah_a = mentah_idsls[urut] if urut < len(mentah_idsls) else None
        mentah_b = mentah_sub[urut] if urut < len(mentah_sub) else None
        mentah_n = mentah_nama[urut] if urut < len(mentah_nama) else None
        kode = normalisasi_idsls(mentah_a) or ""
        sub = normalisasi_idsls(mentah_b) or ""
        if not kode and not sub:
            baris_kosong += 1
            continue
        pasangan.append((kode, sub))
        teks_nama = str(mentah_n).strip() if mentah_n is not None else ""
        baris_atribut = {"kode": kode, "sub": sub, "nama": teks_nama}
        for nama, seri in seri_potong.items():
            mentah = seri[urut] if urut < len(seri) else None
            baris_atribut[nama] = normalisasi_idsls(mentah) or ""
        atribut.append(baris_atribut)
        if (kode, sub) not in peta:
            peta[(kode, sub)] = teks_nama or None

    def _tunggal(nama: str) -> str:
        if nama not in data.columns:
            return ""
        unik = sorted(
            {str(nilai).strip() for nilai in data[nama].dropna() if str(nilai).strip()}
        )
        return unik[0] if len(unik) == 1 else (unik[0] if unik else "")

    kdprov = _tunggal("kdprov")
    kdkab = _tunggal("kdkab")
    return peta, pasangan, contoh, kolom, kdprov, kdkab, baris_kosong, atribut


def validasi_berkas(
    berkas: str | Path,
    layer: str | None,
    master: Mapping[tuple[str, str], str | None],
    kode_kab: str | None = None,
) -> HasilValidasi:
    """Jalankan lima blok validasi untuk satu berkas peta (dipakai worker).

    ``master`` = mapping pasangan ``(idsls, idsubsls)`` -> ``nmsls`` dari
    database (lihat ``app.layanan.muat_master``); berkas Excel hanya dibaca
    saat impor, bukan saat validasi.
    """
    import pyogrio

    peta, pasangan, contoh, kolom, kdprov, kdkab, baris_kosong, atribut = (
        baca_peta(berkas, layer)
    )
    skema = periksa_skema(kolom, contoh)
    skema.jumlah_baris = len(pasangan)
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
    from collections import Counter

    duplikat = periksa_duplikat([kunci_pasangan(a, b) for a, b in pasangan])
    konsistensi = periksa_konsistensi(atribut)
    buruk = konsistensi.pasangan_buruk
    if buruk:
        peta = {kunci: nama for kunci, nama in peta.items() if kunci not in buruk}
        pasangan = [kunci for kunci in pasangan if kunci not in buruk]
    hitung = Counter(pasangan)
    matching = bandingkan(peta, master, hitung)

    kolom_geom = [nama for nama in ("idsls", "idsubsls", "nmsls") if nama in kolom]
    gdf_geom = pyogrio.read_dataframe(
        str(berkas), layer=layer, columns=kolom_geom, read_geometry=True
    )
    atribut_geom: list[dict[str, str]] = []
    seri_idsls = list(gdf_geom["idsls"]) if "idsls" in gdf_geom.columns else []
    seri_sub = list(gdf_geom["idsubsls"]) if "idsubsls" in gdf_geom.columns else []
    seri_nama = list(gdf_geom["nmsls"]) if "nmsls" in gdf_geom.columns else []
    for urut in range(len(gdf_geom)):
        kode_g = normalisasi_idsls(seri_idsls[urut] if urut < len(seri_idsls) else None) or ""
        sub_g = normalisasi_idsls(seri_sub[urut] if urut < len(seri_sub) else None) or ""
        nama_m = seri_nama[urut] if urut < len(seri_nama) else None
        nama_g = str(nama_m).strip() if nama_m is not None else ""
        atribut_geom.append({"kode": kode_g, "sub": sub_g, "nama": nama_g})
    topologi = periksa_topologi(list(gdf_geom.geometry), atribut_geom)

    return gabungkan_hasil(
        skema,
        duplikat,
        konsistensi,
        matching,
        baris_kosong=baris_kosong,
        topologi=topologi,
    )
