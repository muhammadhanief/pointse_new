"""Rekonsiliasi batas berpasangan (Gap & Overlap) antar-kabupaten/kota (run tipe V).

Memeriksa sabuk perbatasan (jarak <= ~220 meter / 0,002 derajat) antara dua
kabupaten/kota bertetangga yang sudah memiliki unggahan peta Validasi SLS 2026
Semester 1 (``tipe = V``).

Modul ini **ringan saat startup**: ``pyogrio`` dan ``shapely`` hanya diimpor di
dalam fungsi spasial yang dipanggil worker/skrip agar proses API tetap hemat
memori dan cepat menyala.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from sqlalchemy import delete, insert, or_, select

from app.models import (
    JENIS_BATAS_GAP,
    JENIS_BATAS_OVERLAP,
    STATUS_BATAS_BELUM_CLEAN,
    STATUS_BATAS_CLEAN,
    STATUS_BATAS_GAGAL,
    STATUS_BELUM_CLEAN,
    STATUS_GAGAL,
    STATUS_SUKSES,
    STATUS_SUKSES_CATATAN,
    TIPE_V,
    RekonsiliasiBatasPasang,
    RekonsiliasiBatasTemuan,
    Run,
    sekarang,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.config import Settings

logger = logging.getLogger(__name__)

#: Konversi kasar derajat ke meter di sekitar lintang Jawa Tengah (~7° LS).
METER_PER_DERAJAT: float = 111_320.0

#: Lebar sabuk perbatasan dalam derajat (~220 meter).
JARAK_SABUK_DERAJAT: float = 0.002

#: Ambang luas minimum bawaan (m2) agar artefak titik/garis degenerat 0 m2
#: diabaikan. ``0.0`` berarti tanpa filter: setiap irisan yang dinyatakan
#: GEOS/QGIS sebagai overlap/gap ikut dicatat (identik dengan Topology Checker
#: QGIS). Nilai efektif dibaca dari tabel ``pengaturan`` lewat
#: :func:`app.pengaturan.baca_luas_min_batas` dan dapat diubah admin.
LUAS_MIN_M2: float = 0.0

#: Tingkat keparahan luas temuan batas.
TINGKAT_SLIVER = "sliver"
TINGKAT_SEDANG = "sedang"
TINGKAT_BESAR = "besar"

#: Kamus ketetanggaan 35 kabupaten/kota Provinsi Jawa Tengah (74 pasang unik)
#: hasil ekstraksi poligon SLS BPS Jawa Tengah (``scripts/cek_tetangga_kab.py``).
TETANGGA_KAB_33: dict[str, tuple[str, ...]] = {
    "3301": ("3302", "3305", "3329"),
    "3302": ("3301", "3303", "3304", "3305", "3327", "3328", "3329"),
    "3303": ("3302", "3304", "3326", "3327"),
    "3304": ("3302", "3303", "3305", "3307", "3325", "3326"),
    "3305": ("3301", "3302", "3304", "3306", "3307"),
    "3306": ("3305", "3307", "3308"),
    "3307": ("3304", "3305", "3306", "3308", "3323", "3324", "3325"),
    "3308": ("3306", "3307", "3309", "3310", "3322", "3323", "3371"),
    "3309": ("3308", "3310", "3311", "3313", "3314", "3315", "3322", "3372"),
    "3310": ("3308", "3309", "3311"),
    "3311": ("3309", "3310", "3312", "3313", "3372"),
    "3312": ("3311", "3313"),
    "3313": ("3309", "3311", "3312", "3314", "3372"),
    "3314": ("3309", "3313", "3315"),
    "3315": ("3309", "3314", "3316", "3318", "3319", "3321", "3322"),
    "3316": ("3315", "3317", "3318"),
    "3317": ("3316", "3318"),
    "3318": ("3315", "3316", "3317", "3319", "3320"),
    "3319": ("3315", "3318", "3320", "3321"),
    "3320": ("3318", "3319", "3321"),
    "3321": ("3315", "3319", "3320", "3322", "3374"),
    "3322": ("3308", "3309", "3315", "3321", "3323", "3324", "3373", "3374"),
    "3323": ("3307", "3308", "3322", "3324"),
    "3324": ("3307", "3322", "3323", "3325", "3374"),
    "3325": ("3304", "3307", "3324", "3326", "3375"),
    "3326": ("3303", "3304", "3325", "3327", "3375"),
    "3327": ("3302", "3303", "3326", "3328"),
    "3328": ("3302", "3327", "3329", "3376"),
    "3329": ("3301", "3302", "3328", "3376"),
    "3371": ("3308",),
    "3372": ("3309", "3311", "3313"),
    "3373": ("3322",),
    "3374": ("3321", "3322", "3324"),
    "3375": ("3325", "3326"),
    "3376": ("3328", "3329"),
}

#: 74 pasangan kanonik ``(kdkab_a, kdkab_b)`` dengan ``kdkab_a < kdkab_b``.
PASANGAN_TETANGGA_33: tuple[tuple[str, str], ...] = tuple(
    sorted(
        {
            (a, b) if a < b else (b, a)
            for a, daftar in TETANGGA_KAB_33.items()
            for b in daftar
        }
    )
)


def pasangan_kanonik(kdkab_1: str, kdkab_2: str) -> tuple[str, str]:
    """Urutkan dua kode kabupaten 4 digit menjadi ``(kdkab_a, kdkab_b)``."""
    a = str(kdkab_1).strip()
    b = str(kdkab_2).strip()
    return (a, b) if a <= b else (b, a)


def klasifikasi_tingkat_luas(luas_m2: float) -> str:
    """Klasifikasikan luas temuan batas (m2) menjadi sliver / sedang / besar."""
    if luas_m2 < 1.0:
        return TINGKAT_SLIVER
    if luas_m2 <= 100.0:
        return TINGKAT_SEDANG
    return TINGKAT_BESAR


@dataclass
class TemuanBatas:
    """Satu titik/poligon temuan Gap atau Overlap antar dua kabupaten/kota."""

    jenis: str
    tingkat: str
    idsls_a: str | None
    idsubsls_a: str | None
    nmsls_a: str | None
    idsls_b: str | None
    idsubsls_b: str | None
    nmsls_b: str | None
    luas_m2: float
    lat: float
    lon: float
    catatan: str | None = None
    geojson_geom: dict[str, Any] | None = None


@dataclass
class HasilRekonsiliasiPasang:
    """Hasil pemeriksaan batas berpasangan antara ``kdkab_a`` dan ``kdkab_b``."""

    kdkab_a: str
    kdkab_b: str
    bersih: bool
    jumlah_overlap: int = 0
    jumlah_gap: int = 0
    total_luas_overlap_m2: float = 0.0
    total_luas_gap_m2: float = 0.0
    temuan: list[TemuanBatas] = field(default_factory=list)
    pesan: str = ""


def _bersihkan_poligon(geom: Any) -> Any | None:
    """Pastikan geometri valid dan hanya menyisakan bagian Polygon/MultiPolygon."""
    import shapely

    if geom is None or geom.is_empty:
        return None
    if not shapely.is_valid(geom):
        geom = shapely.make_valid(geom)
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    bagian = [
        p
        for p in shapely.get_parts(geom)
        if p is not None and not p.is_empty and p.geom_type in ("Polygon", "MultiPolygon")
    ]
    if not bagian:
        return None
    return shapely.unary_union(bagian)


def periksa_batas_dua_geometri(
    kdkab_a: str,
    kdkab_b: str,
    geometri_a: list[Any],
    atribut_a: list[dict[str, str | None]],
    geometri_b: list[Any],
    atribut_b: list[dict[str, str | None]],
    *,
    jarak_sabuk_derajat: float = JARAK_SABUK_DERAJAT,
    luas_min_m2: float = LUAS_MIN_M2,
) -> HasilRekonsiliasiPasang:
    """Periksa Gap dan Overlap pada sabuk perbatasan dua kabupaten/kota (murni).

    Menggunakan indeks spasial ``STRtree`` untuk menyaring poligon yang berada
    dalam jarak ``jarak_sabuk_derajat`` (~220m), lalu menjalankan:
    1. Deteksi **Overlap** antar poligon ``kdkab_a`` dan ``kdkab_b``.
    2. Deteksi **Gap** (celah kosong terjepit) menggunakan metode ``checkGaps``
       QGIS Topology Checker pada gabungan poligon sabuk perbatasan yang
       menyentuh kedua kabupaten sekaligus di dalam koridor pertemuan.

    ``luas_min_m2`` adalah ambang luas minimum (m2). Nilai ``0`` mencatat semua
    irisan yang valid sebagai poligon (sama dengan Topology Checker QGIS).
    """
    import shapely
    from shapely import STRtree

    kdkab_a, kdkab_b = pasangan_kanonik(kdkab_a, kdkab_b)

    valid_a: list[Any] = []
    info_a: list[dict[str, str | None]] = []
    for idx, g in enumerate(geometri_a):
        bersih = _bersihkan_poligon(g)
        if bersih is not None:
            valid_a.append(bersih)
            info_a.append(atribut_a[idx] if idx < len(atribut_a) else {})

    valid_b: list[Any] = []
    info_b: list[dict[str, str | None]] = []
    for idx, g in enumerate(geometri_b):
        bersih = _bersihkan_poligon(g)
        if bersih is not None:
            valid_b.append(bersih)
            info_b.append(atribut_b[idx] if idx < len(atribut_b) else {})

    if not valid_a or not valid_b:
        return HasilRekonsiliasiPasang(
            kdkab_a=kdkab_a,
            kdkab_b=kdkab_b,
            bersih=True,
            pesan="Salah satu berkas tidak memiliki poligon valid.",
        )

    pohon_a = STRtree(valid_a)
    idx_b, idx_a = pohon_a.query(
        valid_b, predicate="dwithin", distance=jarak_sabuk_derajat
    )
    dekat_a = sorted({int(i) for i in idx_a})
    dekat_b = sorted({int(i) for i in idx_b})

    if not dekat_a or not dekat_b:
        return HasilRekonsiliasiPasang(
            kdkab_a=kdkab_a,
            kdkab_b=kdkab_b,
            bersih=True,
            pesan="Tidak ada poligon yang bersinggungan dalam sabuk perbatasan.",
        )

    sub_ga = [valid_a[i] for i in dekat_a]
    sub_ia = [info_a[i] for i in dekat_a]
    sub_gb = [valid_b[i] for i in dekat_b]
    sub_ib = [info_b[i] for i in dekat_b]

    pohon_sub_a = STRtree(sub_ga)
    pohon_sub_b = STRtree(sub_gb)

    temuan: list[TemuanBatas] = []
    jumlah_overlap = 0
    total_luas_overlap = 0.0

    # 1. Deteksi Overlap antar poligon kab A dan kab B
    for loc_a, geom_a in enumerate(sub_ga):
        atr_a = sub_ia[loc_a]
        kandidat_b = pohon_sub_b.query(geom_a, predicate="intersects")
        for loc_b_raw in kandidat_b:
            loc_b = int(loc_b_raw)
            geom_b = sub_gb[loc_b]
            if not (
                shapely.overlaps(geom_a, geom_b)
                or shapely.covers(geom_a, geom_b)
                or shapely.covers(geom_b, geom_a)
            ):
                continue
            irisan = _bersihkan_poligon(shapely.intersection(geom_a, geom_b))
            if irisan is None:
                continue
            luas_m2 = float(shapely.area(irisan) * (METER_PER_DERAJAT**2))
            if luas_min_m2 > 0 and luas_m2 <= luas_min_m2:
                continue
            atr_b = sub_ib[loc_b]
            titik = irisan.representative_point()
            tingkat = klasifikasi_tingkat_luas(luas_m2)
            jumlah_overlap += 1
            total_luas_overlap += luas_m2
            sub_a_kode = atr_a.get("idsubsls") or atr_a.get("idsls") or kdkab_a
            sub_b_kode = atr_b.get("idsubsls") or atr_b.get("idsls") or kdkab_b
            temuan.append(
                TemuanBatas(
                    jenis=JENIS_BATAS_OVERLAP,
                    tingkat=tingkat,
                    idsls_a=atr_a.get("idsls"),
                    idsubsls_a=atr_a.get("idsubsls"),
                    nmsls_a=atr_a.get("nmsls"),
                    idsls_b=atr_b.get("idsls"),
                    idsubsls_b=atr_b.get("idsubsls"),
                    nmsls_b=atr_b.get("nmsls"),
                    luas_m2=round(luas_m2, 4),
                    lat=round(float(titik.y), 7),
                    lon=round(float(titik.x), 7),
                    catatan=(
                        f"Tumpang tindih {sub_a_kode} ({kdkab_a}) dengan "
                        f"{sub_b_kode} ({kdkab_b}) seluas {luas_m2:.2f} m²"
                    )[:255],
                    geojson_geom=json.loads(shapely.to_geojson(irisan)),
                )
            )

    # 2. Deteksi Gap (celah kosong) di sabuk pertemuan kab A dan kab B
    jumlah_gap = 0
    total_luas_gap = 0.0
    union_a = shapely.unary_union(sub_ga)
    union_b = shapely.unary_union(sub_gb)
    gabungan = shapely.unary_union([union_a, union_b])
    if not gabungan.is_empty:
        batas = shapely.box(*gabungan.bounds).buffer(0.05, quad_segs=3)
        selisih = shapely.difference(batas, gabungan)
        semua_lubang = list(shapely.get_parts(selisih))[1:]
        if semua_lubang:
            koridor = shapely.intersection(
                shapely.buffer(union_a, jarak_sabuk_derajat, quad_segs=3),
                shapely.buffer(union_b, jarak_sabuk_derajat, quad_segs=3),
            )
            for celah in semua_lubang:
                if celah is None or celah.is_empty:
                    continue
                celah_buf = celah.buffer(1e-7)
                if not (
                    shapely.intersects(celah_buf, union_a)
                    and shapely.intersects(celah_buf, union_b)
                    and shapely.within(celah, koridor)
                ):
                    continue
                luas_m2 = float(shapely.area(celah) * (METER_PER_DERAJAT**2))
                if luas_min_m2 > 0 and luas_m2 <= luas_min_m2:
                    continue

                # Cari poligon kab A dan kab B yang menyentuh celah ini
                atr_a_celah = _cari_atribut_terdekat(
                    celah_buf, pohon_sub_a, sub_ga, sub_ia
                )
                atr_b_celah = _cari_atribut_terdekat(
                    celah_buf, pohon_sub_b, sub_gb, sub_ib
                )
                titik = celah.representative_point()
                tingkat = klasifikasi_tingkat_luas(luas_m2)
                jumlah_gap += 1
                total_luas_gap += luas_m2
                sub_a_kode = (
                    atr_a_celah.get("idsubsls") or atr_a_celah.get("idsls") or kdkab_a
                )
                sub_b_kode = (
                    atr_b_celah.get("idsubsls") or atr_b_celah.get("idsls") or kdkab_b
                )
                temuan.append(
                    TemuanBatas(
                        jenis=JENIS_BATAS_GAP,
                        tingkat=tingkat,
                        idsls_a=atr_a_celah.get("idsls"),
                        idsubsls_a=atr_a_celah.get("idsubsls"),
                        nmsls_a=atr_a_celah.get("nmsls"),
                        idsls_b=atr_b_celah.get("idsls"),
                        idsubsls_b=atr_b_celah.get("idsubsls"),
                        nmsls_b=atr_b_celah.get("nmsls"),
                        luas_m2=round(luas_m2, 4),
                        lat=round(float(titik.y), 7),
                        lon=round(float(titik.x), 7),
                        catatan=(
                            f"Celah kosong antara {sub_a_kode} ({kdkab_a}) dan "
                            f"{sub_b_kode} ({kdkab_b}) seluas {luas_m2:.2f} m²"
                        )[:255],
                        geojson_geom=json.loads(shapely.to_geojson(celah)),
                    )
                )

    bersih = jumlah_overlap == 0 and jumlah_gap == 0
    if bersih:
        pesan = "Batas kedua kabupaten/kota bersih (0 overlap, 0 gap)."
    else:
        pesan = (
            f"Ditemukan {jumlah_overlap} overlap ({total_luas_overlap:.2f} m²) "
            f"dan {jumlah_gap} gap ({total_luas_gap:.2f} m²)."
        )

    return HasilRekonsiliasiPasang(
        kdkab_a=kdkab_a,
        kdkab_b=kdkab_b,
        bersih=bersih,
        jumlah_overlap=jumlah_overlap,
        jumlah_gap=jumlah_gap,
        total_luas_overlap_m2=round(total_luas_overlap, 4),
        total_luas_gap_m2=round(total_luas_gap, 4),
        temuan=temuan,
        pesan=pesan,
    )


def _cari_atribut_terdekat(
    celah_buf: Any,
    pohon: Any,
    daftar_geom: list[Any],
    daftar_info: list[dict[str, str | None]],
) -> dict[str, str | None]:
    """Ambil atribut poligon yang berpotongan paling panjang dengan ``celah_buf``."""
    import shapely

    kandidat = [int(i) for i in pohon.query(celah_buf, predicate="intersects")]
    if not kandidat:
        terdekat = pohon.query_nearest(celah_buf)
        if len(terdekat) > 0:
            idx = int(terdekat[0])
            return daftar_info[idx]
        return {}
    terbaik_idx = max(
        kandidat,
        key=lambda i: float(shapely.area(shapely.intersection(daftar_geom[i], celah_buf))),
    )
    return daftar_info[terbaik_idx]


def _baca_geometri_dan_atribut_berkas(
    berkas: str | Path, layer: str | None = None
) -> tuple[list[Any], list[dict[str, str | None]]]:
    """Baca poligon dan atribut identitas SLS dari berkas peta GPKG/GeoJSON/SHP."""
    import pyogrio

    info_meta = pyogrio.read_info(str(berkas), layer=layer or None)
    kolom_ada = {str(k).lower(): str(k) for k in info_meta.get("fields", ())}
    ambil_kolom = [
        kolom_ada[k]
        for k in ("idsls", "idsubsls", "nmsls")
        if k in kolom_ada
    ]
    df = pyogrio.read_dataframe(
        str(berkas),
        layer=layer or None,
        columns=ambil_kolom,
    )
    peta_nama_kolom = {str(k).lower(): str(k) for k in df.columns}

    def _ambil_seri(nama: str) -> list[str | None]:
        asli = peta_nama_kolom.get(nama)
        if not asli:
            return [None] * len(df)
        hasil: list[str | None] = []
        for v in df[asli].tolist():
            if v is None or (isinstance(v, float) and v != v):
                hasil.append(None)
            else:
                teks = str(v).strip()
                hasil.append(teks or None)
        return hasil

    idsls_list = _ambil_seri("idsls")
    idsubsls_list = _ambil_seri("idsubsls")
    nmsls_list = _ambil_seri("nmsls")
    geoms = df.geometry.tolist()
    atribut = [
        {
            "idsls": idsls_list[i],
            "idsubsls": idsubsls_list[i],
            "nmsls": nmsls_list[i],
        }
        for i in range(len(geoms))
    ]
    return geoms, atribut


def buat_geojson_fitur(hasil: HasilRekonsiliasiPasang) -> dict[str, Any]:
    """Bangun FeatureCollection GeoJSON (CRS EPSG:4326) dari temuan batas."""
    fitur: list[dict[str, Any]] = []
    for urut, satu in enumerate(hasil.temuan, start=1):
        if not satu.geojson_geom:
            continue
        fitur.append(
            {
                "type": "Feature",
                "id": urut,
                "properties": {
                    "no": urut,
                    "kdkab_a": hasil.kdkab_a,
                    "kdkab_b": hasil.kdkab_b,
                    "jenis": satu.jenis,
                    "tingkat": satu.tingkat,
                    "idsls_a": satu.idsls_a,
                    "idsubsls_a": satu.idsubsls_a,
                    "nmsls_a": satu.nmsls_a,
                    "idsls_b": satu.idsls_b,
                    "idsubsls_b": satu.idsubsls_b,
                    "nmsls_b": satu.nmsls_b,
                    "luas_m2": satu.luas_m2,
                    "lat": satu.lat,
                    "lon": satu.lon,
                    "catatan": satu.catatan,
                },
                "geometry": satu.geojson_geom,
            }
        )
    return {
        "type": "FeatureCollection",
        "name": f"QC_Batas_{hasil.kdkab_a}_{hasil.kdkab_b}",
        "features": fitur,
    }


def jalur_geojson_pasang(
    setelan: Settings, kdkab_a: str, kdkab_b: str
) -> Path:
    """Lokasi penyimpanan berkas GeoJSON QC Batas untuk pasangan ``(kdkab_a, kdkab_b)``."""
    a, b = pasangan_kanonik(kdkab_a, kdkab_b)
    folder = Path(setelan.dir_unggahan) / "rekonsiliasi-batas"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"QC_Batas_{a}_{b}.geojson"


def periksa_batas_dua_berkas(
    kdkab_a: str,
    berkas_a: str | Path,
    layer_a: str | None,
    kdkab_b: str,
    berkas_b: str | Path,
    layer_b: str | None,
    *,
    luas_min_m2: float = LUAS_MIN_M2,
) -> HasilRekonsiliasiPasang:
    """Baca dua berkas peta SLS dan jalankan pemeriksaan batas berpasangan."""
    a, b = pasangan_kanonik(kdkab_a, kdkab_b)
    if a != str(kdkab_a).strip():
        berkas_a, berkas_b = berkas_b, berkas_a
        layer_a, layer_b = layer_b, layer_a
    geom_a, atr_a = _baca_geometri_dan_atribut_berkas(berkas_a, layer_a)
    geom_b, atr_b = _baca_geometri_dan_atribut_berkas(berkas_b, layer_b)
    return periksa_batas_dua_geometri(
        a, b, geom_a, atr_a, geom_b, atr_b, luas_min_m2=luas_min_m2
    )


def run_v_terakhir_per_kab(
    sesi: Session, kdprov: str = "33"
) -> dict[str, Run]:
    """Ambil run ``TIPE_V`` selesai terakhir yang berkas petanya ada untuk tiap kabupaten."""
    from app import layanan

    status_valid = (
        STATUS_SUKSES,
        STATUS_SUKSES_CATATAN,
        STATUS_BELUM_CLEAN,
        STATUS_GAGAL,
    )
    semua = sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_V,
            Run.kdprov == kdprov,
            Run.status.in_(status_valid),
        )
        .order_by(Run.id.asc())
    ).all()
    peta: dict[str, Run] = {}
    for satu in semua:
        kode = layanan.kode_kabupaten(satu.kdprov, satu.kdkab)
        peta[kode] = satu
    return peta


def simpan_hasil_pasang(
    sesi: Session,
    setelan: Settings,
    *,
    kdprov: str,
    kdkab_a: str,
    kdkab_b: str,
    run_a: Run,
    run_b: Run,
    hasil: HasilRekonsiliasiPasang,
) -> RekonsiliasiBatasPasang:
    """Upsert baris ``rekonsiliasi_batas_pasang``, ganti temuan, dan tulis GeoJSON ke disk."""
    a, b = pasangan_kanonik(kdkab_a, kdkab_b)
    if a != kdkab_a:
        run_a, run_b = run_b, run_a

    jalur_geo = jalur_geojson_pasang(setelan, a, b)
    koleksi = buat_geojson_fitur(hasil)
    jalur_geo.write_text(
        json.dumps(koleksi, ensure_ascii=False), encoding="utf-8"
    )

    pasang = sesi.scalars(
        select(RekonsiliasiBatasPasang).where(
            RekonsiliasiBatasPasang.kdkab_a == a,
            RekonsiliasiBatasPasang.kdkab_b == b,
        )
    ).first()
    status_pasang = (
        STATUS_BATAS_CLEAN if hasil.bersih else STATUS_BATAS_BELUM_CLEAN
    )
    waktu = sekarang()
    if pasang is None:
        pasang = RekonsiliasiBatasPasang(
            kdprov=kdprov,
            kdkab_a=a,
            kdkab_b=b,
            run_a_id=run_a.id,
            run_b_id=run_b.id,
            status=status_pasang,
            jumlah_overlap=hasil.jumlah_overlap,
            jumlah_gap=hasil.jumlah_gap,
            total_luas_overlap_m2=hasil.total_luas_overlap_m2,
            total_luas_gap_m2=hasil.total_luas_gap_m2,
            berkas_geojson=str(jalur_geo),
            pesan=hasil.pesan,
            updated_at=waktu,
        )
        sesi.add(pasang)
        sesi.flush()
    else:
        pasang.kdprov = kdprov
        pasang.run_a_id = run_a.id
        pasang.run_b_id = run_b.id
        pasang.status = status_pasang
        pasang.jumlah_overlap = hasil.jumlah_overlap
        pasang.jumlah_gap = hasil.jumlah_gap
        pasang.total_luas_overlap_m2 = hasil.total_luas_overlap_m2
        pasang.total_luas_gap_m2 = hasil.total_luas_gap_m2
        pasang.berkas_geojson = str(jalur_geo)
        pasang.pesan = hasil.pesan
        pasang.updated_at = waktu
        sesi.flush()

    sesi.execute(
        delete(RekonsiliasiBatasTemuan).where(
            RekonsiliasiBatasTemuan.pasang_id == pasang.id
        )
    )
    if hasil.temuan:
        baris_temuan = [
            {
                "pasang_id": pasang.id,
                "kdkab_a": a,
                "kdkab_b": b,
                "jenis": t.jenis,
                "tingkat": t.tingkat,
                "idsls_a": t.idsls_a,
                "idsubsls_a": t.idsubsls_a,
                "nmsls_a": t.nmsls_a,
                "idsls_b": t.idsls_b,
                "idsubsls_b": t.idsubsls_b,
                "nmsls_b": t.nmsls_b,
                "luas_m2": t.luas_m2,
                "lat": t.lat,
                "lon": t.lon,
                "catatan": t.catatan,
                "created_at": waktu,
            }
            for t in hasil.temuan
        ]
        sesi.execute(insert(RekonsiliasiBatasTemuan), baris_temuan)

    return pasang


def perbarui_batas_untuk_run_v(
    sesi: Session, run: Run, setelan: Settings | None = None
) -> int:
    """Hitung ulang batas antara kabupaten milik ``run`` dan seluruh tetangganya yang punya run V.

    Dipanggil otomatis setelah ``simpan_fase_akhir_v`` selesai. Kegagalan baca
    pada satu pasangan tetangga dicatat di log dan tidak menggagalkan job ``V``.
    Mengembalikan jumlah pasangan tetangga yang berhasil diperiksa.
    """
    from app import layanan
    from app.config import get_settings

    if run.tipe != TIPE_V or not run.berkas_peta or not Path(run.berkas_peta).is_file():
        return 0

    setelan = setelan or get_settings()
    kode_utama = layanan.kode_kabupaten(run.kdprov, run.kdkab)
    daftar_tetangga = TETANGGA_KAB_33.get(kode_utama, ())
    if not daftar_tetangga:
        return 0

    from app import pengaturan as pengaturan_app

    luas_min_m2 = pengaturan_app.baca_luas_min_batas(sesi)

    runs_kab = run_v_terakhir_per_kab(sesi, kdprov=run.kdprov)
    runs_kab[kode_utama] = run

    tetangga_siap = [
        kode_lawan
        for kode_lawan in daftar_tetangga
        if (
            (r := runs_kab.get(kode_lawan)) is not None
            and r.berkas_peta
            and Path(r.berkas_peta).is_file()
        )
    ]
    if not tetangga_siap:
        return 0

    try:
        geom_utama, atr_utama = _baca_geometri_dan_atribut_berkas(
            run.berkas_peta, run.layer_peta
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "gagal membaca geometri peta %s untuk rekonsiliasi batas", kode_utama
        )
        return 0

    diperiksa = 0
    for kode_lawan in tetangga_siap:
        run_lawan = runs_kab[kode_lawan]
        try:
            geom_lawan, atr_lawan = _baca_geometri_dan_atribut_berkas(
                run_lawan.berkas_peta, run_lawan.layer_peta
            )
            a, b = pasangan_kanonik(kode_utama, kode_lawan)
            if a == kode_utama:
                hasil = periksa_batas_dua_geometri(
                    a,
                    b,
                    geom_utama,
                    atr_utama,
                    geom_lawan,
                    atr_lawan,
                    luas_min_m2=luas_min_m2,
                )
                run_a, run_b = run, run_lawan
            else:
                hasil = periksa_batas_dua_geometri(
                    a,
                    b,
                    geom_lawan,
                    atr_lawan,
                    geom_utama,
                    atr_utama,
                    luas_min_m2=luas_min_m2,
                )
                run_a, run_b = run_lawan, run
            simpan_hasil_pasang(
                sesi,
                setelan,
                kdprov=run.kdprov,
                kdkab_a=a,
                kdkab_b=b,
                run_a=run_a,
                run_b=run_b,
                hasil=hasil,
            )
            sesi.commit()
            diperiksa += 1
        except Exception:  # noqa: BLE001
            sesi.rollback()
            logger.exception(
                "gagal memeriksa batas %s vs %s", kode_utama, kode_lawan
            )
    return diperiksa


def jalankan_ulang_semua_batas(
    sesi: Session,
    setelan: Settings,
    *,
    luas_min_m2: float = LUAS_MIN_M2,
    progres: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    """Periksa ulang **semua** pasangan tetangga Jawa Tengah dengan ambang baru.

    Hanya pasangan yang kedua kabupaten/kotanya sudah punya run ``V`` beserta
    berkas peta yang masih ada yang diperiksa. Dipanggil worker untuk tombol
    "Jalankan ulang pemeriksaan batas" setelah admin mengubah ambang luas
    minimum. Satu pasangan dibaca dan diperiksa sekaligus supaya pemakaian
    memori tetap di bawah anggaran worker (tidak ada cache antar-pasangan).

    ``progres(sudah, total)`` dipanggil setelah tiap pasangan selesai agar
    halaman admin dapat menampilkan kemajuan.

    Mengembalikan hitungan ``total``, ``sudah``, ``bersih``, ``belum_clean``,
    ``gagal``, dan ``dilewati`` (pasangan yang petanya belum lengkap).
    """
    runs_kab = run_v_terakhir_per_kab(sesi, kdprov="33")

    siap: list[tuple[str, str, Run, Run]] = []
    dilewati = 0
    for a, b in PASANGAN_TETANGGA_33:
        run_a = runs_kab.get(a)
        run_b = runs_kab.get(b)
        if (
            run_a is not None
            and run_b is not None
            and run_a.berkas_peta
            and run_b.berkas_peta
            and Path(run_a.berkas_peta).is_file()
            and Path(run_b.berkas_peta).is_file()
        ):
            siap.append((a, b, run_a, run_b))
        else:
            dilewati += 1

    total = len(siap)
    bersih = belum_clean = gagal = 0
    if progres is not None:
        progres(0, total)

    for urut, (a, b, run_a, run_b) in enumerate(siap, start=1):
        try:
            geom_a, atr_a = _baca_geometri_dan_atribut_berkas(
                run_a.berkas_peta, run_a.layer_peta
            )
            geom_b, atr_b = _baca_geometri_dan_atribut_berkas(
                run_b.berkas_peta, run_b.layer_peta
            )
            hasil = periksa_batas_dua_geometri(
                a, b, geom_a, atr_a, geom_b, atr_b, luas_min_m2=luas_min_m2
            )
            simpan_hasil_pasang(
                sesi,
                setelan,
                kdprov="33",
                kdkab_a=a,
                kdkab_b=b,
                run_a=run_a,
                run_b=run_b,
                hasil=hasil,
            )
            sesi.commit()
            if hasil.bersih:
                bersih += 1
            else:
                belum_clean += 1
        except Exception:  # noqa: BLE001 - satu pasangan gagal tidak menggugurkan sisanya
            sesi.rollback()
            gagal += 1
            logger.exception("gagal memeriksa ulang batas %s vs %s", a, b)
        if progres is not None:
            progres(urut, total)

    return {
        "total": total,
        "sudah": total,
        "bersih": bersih,
        "belum_clean": belum_clean,
        "gagal": gagal,
        "dilewati": dilewati,
    }
