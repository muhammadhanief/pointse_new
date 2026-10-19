"""Ukur waktu + memori TIAP TAHAP Proses A pada data uji penuh (kdkab 3307).

Fokus alat ukur, bukan aplikasi: kode tahap di sini adalah salinan urutan
langkah di ``app/proses_a.py`` (tanpa perubahan logika). Jumlah waktu tahap
dibandingkan dengan waktu ``proses_a`` utuh sebagai pemeriksaan.

Jalankan dari folder ``backend``:

    .venv\\\\Scripts\\\\python.exe scripts\\\\ukur_tahap_proses_a.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

AKAR_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR_BACKEND))
sys.path.insert(0, str(AKAR_BACKEND / "scripts"))
sys.path.insert(0, str(AKAR_BACKEND / "tests"))

import _memori  # noqa: E402
import qgis_data  # noqa: E402

from app.proses_a import (  # noqa: E402
    CRS_TARGET,
    KOLOM_HASIL,
    KOLOM_PETA,
    KOLOM_TITIK,
    NILAI_BBTT,
    NILAI_BKU,
    NILAI_BTT,
    NILAI_BTTK,
    NILAI_KK,
    _angka,
    _flag,
    cek_kolom,
    pastikan_crs4326,
    proses_a,
)

CATATAN: list[dict[str, object]] = []


def tahap(nama: str, fungsi):
    """Jalankan ``fungsi()`` sambil mencatat waktu dan RSS sebelum/sesudah."""
    rss_sebelum = _memori.memori()
    t0 = time.perf_counter()
    hasil = fungsi()
    waktu = time.perf_counter() - t0
    rss_sesudah = _memori.memori()
    CATATAN.append(
        {
            "tahap": nama,
            "waktu": waktu,
            "rss_sebelum": rss_sebelum,
            "rss_sesudah": rss_sesudah,
        }
    )
    return hasil


def cetak_tabel() -> None:
    print(f"{'tahap':<46}{'waktu':>10}{'RSS sblm':>11}{'RSS sdah':>11}{'delta':>10}")
    print("-" * 88)
    for baris in CATATAN:
        sebelum = baris["rss_sebelum"]
        sesudah = baris["rss_sesudah"]
        delta = (
            "n/a"
            if sebelum is None or sesudah is None
            else f"{sesudah - sebelum:+,.0f} MB"
        )
        print(
            f"{baris['tahap']:<46}{baris['waktu']:>9.1f}s"
            f"{_memori.mb(sebelum):>11}{_memori.mb(sesudah):>11}{delta:>10}"
        )


def main() -> int:
    if not qgis_data.ada_data_uji():
        print("Data uji tidak ada di docs/. Skrip ini butuh data uji penuh.")
        return 1

    print("=" * 88)
    print("UKUR PER TAHAP — PROSES A, data uji kdkab 3307")
    print("=" * 88)
    print(f"python : {sys.version.split()[0]} | memori awal: {_memori.mb(_memori.memori())}")

    # 1-2. Baca file
    titik = tahap("1. baca titik (GPKG, layer geotag)", qgis_data.muat_titik)
    peta = tahap("2. baca peta (GeoJSON)", qgis_data.muat_peta)
    print(f"\n   titik {len(titik):,} baris, crs={titik.crs} | peta {len(peta):,} poligon, crs={peta.crs}")
    print("   catatan: crs titik sudah 4326 dan peta tanpa crs tegas -> tahap reproject=no-op\n")

    # 3. Data titik: reproject + validasi + kolom bantu
    def siapkan_titik():
        t = pastikan_crs4326(titik, "titik")
        cek_kolom(t, KOLOM_TITIK, "titik")
        t = t.reset_index(drop=True)
        t["_urut"] = range(len(t))
        return t

    titik_urut = tahap("3. titik: reproject 4326 + cek kolom + _urut", siapkan_titik)

    # 4. Data peta: reproject + validasi + kolom bantu
    def siapkan_peta():
        p = pastikan_crs4326(peta, "peta")
        cek_kolom(p, KOLOM_PETA, "peta")
        nama_geom = p.geometry.name
        p = p.reset_index(drop=True)[list(KOLOM_PETA) + [nama_geom]].copy()
        p["_posisi"] = range(len(p))
        return p

    peta_urut = tahap("4. peta: reproject 4326 + cek kolom + _posisi", siapkan_peta)

    # 5. Join
    gabung = tahap(
        "5. join: sjoin (how=left, intersects)",
        lambda: gpd.sjoin(titik_urut, peta_urut, how="left", predicate="intersects"),
    )
    jumlah_cocok = int(gabung["_posisi"].notna().sum())
    print(f"\n   hasil sjoin: {len(gabung):,} baris ({jumlah_cocok:,} kecocokan, {len(gabung) - jumlah_cocok:,} tanpa poligon)\n")

    # 6. Pilih poligon pertama + urutkan + buang duplikat
    def pilih_dan_buang_duplikat(gabung):
        gabung = gabung.sort_values(["_urut", "_posisi"], kind="stable")
        gabung = gabung.drop_duplicates(subset="_urut", keep="first")
        cocok = gabung["_posisi"].notna()
        gabung = pd.concat(
            [
                gabung[cocok].sort_values(["_posisi", "_urut"], kind="stable"),
                gabung[~cocok].sort_values("_urut", kind="stable"),
            ]
        )
        return gabung.drop_duplicates(subset="assignment_id", keep="first")

    gabung = tahap(
        "6. poligon pertama + urut per poligon + buang duplikat",
        lambda: pilih_dan_buang_duplikat(gabung),
    )
    print(f"\n   setelah duplikat dibuang: {len(gabung):,} baris\n")

    urut = gabung["_urut"].to_numpy()
    indeks_asli = titik_urut.index.to_numpy()[urut]  # index asli = posisi baris (sudah reset)

    # 7. Hitung 30 kolom + flag
    def hitung_kolom():
        hasil = pd.DataFrame(index=gabung.index)
        hasil["assignment_id"] = gabung["assignment_id"].to_numpy()
        hasil["unique_bang"] = gabung["unique_bang"].to_numpy()
        hasil["flag_psls"] = gabung["flag_psls"].to_numpy()
        beda = gabung["idsubsls"].to_numpy() != gabung["level_6_full_code"].to_numpy()
        hasil["flag_repair_initial"] = beda.astype("int8")
        hasil["flag_repair"] = beda.astype("int8")
        hasil["level_6_full_code"] = gabung["level_6_full_code"].to_numpy()
        hasil["idsubsls_origin"] = gabung["idsubsls"].to_numpy()
        hasil["latitude_origin"] = _angka(gabung["geotag_latitude"]).to_numpy()
        hasil["longitude_origin"] = _angka(gabung["geotag_longitude"]).to_numpy()
        hasil["no_bang"] = gabung["no_bang"].to_numpy()
        hasil["kode_bang_value"] = gabung["kode_bang_value"].to_numpy()
        hasil["ada_keluarga_value"] = gabung["ada_keluarga_value"].to_numpy()
        hasil["ada_bang_usaha_value"] = gabung["ada_bang_usaha_value"].to_numpy()
        hasil["jumlah_usaha_ditemukan"] = gabung["count_usaha"].to_numpy()
        hasil["kdprov"] = gabung["kdprov"].to_numpy()
        hasil["nmprov"] = gabung["nmprov"].to_numpy()
        hasil["kdkab"] = gabung["kdkab"].to_numpy()
        hasil["nmkab"] = gabung["nmkab"].to_numpy()
        hasil["kdkec"] = gabung["kdkec"].to_numpy()
        hasil["nmkec"] = gabung["nmkec"].to_numpy()
        hasil["kddesa"] = gabung["kddesa"].to_numpy()
        hasil["nmdesa"] = gabung["nmdesa"].to_numpy()
        hasil["nmsls"] = gabung["nmsls"].to_numpy()
        hasil["kk"] = _flag(gabung["ada_keluarga_value"], NILAI_KK).to_numpy()
        hasil["btt"] = _flag(gabung["kode_bang_value"], NILAI_BTT).to_numpy()
        hasil["bku"] = _flag(gabung["kode_bang_value"], NILAI_BKU).to_numpy()
        hasil["bttk"] = _flag(gabung["kode_bang_value"], NILAI_BTTK).to_numpy()
        hasil["bbtt"] = _flag(gabung["kode_bang_value"], NILAI_BBTT).to_numpy()
        hasil["usaha"] = gabung["count_usaha"].to_numpy()
        hasil["nama_usaha_bang"] = gabung["nama_usaha_bang"].to_numpy()
        return hasil

    hasil = tahap("7. hitung 30 kolom + 7 flag", hitung_kolom)

    # 8. Bungkus GeoDataFrame + pilih urutan kolom
    def bungkus():
        hasil_gdf = gpd.GeoDataFrame(
            hasil, geometry=titik_urut.geometry.to_numpy()[urut], crs=CRS_TARGET
        )
        hasil_gdf.index = indeks_asli
        return hasil_gdf[list(KOLOM_HASIL) + ["geometry"]]

    hasil_akhir = tahap("8. bungkus GeoDataFrame + urutan kolom", bungkus)

    cetak_tabel()

    total_tahap = sum(b["waktu"] for b in CATATAN[2:])  # tahap 3-8 = isi proses_a
    print("-" * 88)
    print(f"{'jumlah tahap 3-8 (= isi proses_a)':<46}{total_tahap:>9.1f}s")
    print(f"{'1+2 baca file':<46}{CATATAN[0]['waktu'] + CATATAN[1]['waktu']:>9.1f}s")

    # Pemeriksaan: panggil proses_a utuh (data sudah di memori)
    t0 = time.perf_counter()
    proses_a(titik, peta)
    waktu_utuh = time.perf_counter() - t0
    print(f"{'proses_a utuh (data sudah di memori)':<46}{waktu_utuh:>9.1f}s")

    print(
        f"\nmemori puncak proses (RSS) : {_memori.mb(_memori.memori('PeakWorkingSetSize'))}"
        f" | RSS akhir: {_memori.mb(_memori.memori())}"
    )
    print(f"\nhasil akhir: {len(hasil_akhir):,} baris")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
