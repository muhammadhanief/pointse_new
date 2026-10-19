"""Proses A: identifikasi titik bangunan terhadap batas wilkerstat.

Replikasi persis model QGIS ``01 Identifikasi Titik.model3``:

1. reproject titik dan peta ke EPSG:4326 (sama seperti dompet ``reprojectlayer``);
2. ``joinattributesbylocation``: predikat **intersects** (model menulis
   ``PREDICATE=[0, 5]`` = intersects + within), ``METHOD=1`` (ambil atribut
   poligon **pertama** yang cocok), ``DISCARD_NONMATCHING=false`` (titik yang
   tidak cocok tetap dipertahankan, kolom wilayah kosong);
3. ``mergevectorlayers`` hasil cocok + tidak cocok, lalu
   ``removeduplicatesbyattribute`` pada ``assignment_id``;
4. ``refactorfields`` membentuk 30 kolom "Hasil Identifikasi Titik".

Modul ini murni: fungsinya hanya menerima GeoDataFrame dan mengembalikan hasil,
tanpa membaca file dan tanpa mengakses basis data.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

CRS_TARGET: str = "EPSG:4326"

# Kolom peta yang diambil saat join (JOIN_FIELDS pada model QGIS).
KOLOM_PETA: tuple[str, ...] = (
    "kdprov",
    "kdkab",
    "kdkec",
    "kddesa",
    "nmprov",
    "nmkab",
    "nmkec",
    "nmdesa",
    "idsls",
    "nmsls",
    "idsubsls",
)

# Kolom titik yang wajib ada (PRD bagian 4).
KOLOM_TITIK: tuple[str, ...] = (
    "assignment_id",
    "unique_bang",
    "flag_psls",
    "level_6_full_code",
    "geotag_latitude",
    "geotag_longitude",
    "no_bang",
    "kode_bang_value",
    "ada_keluarga_value",
    "ada_bang_usaha_value",
    "count_usaha",
    "nama_usaha_bang",
)

# Urutan 30 kolom output (FIELDS_MAPPING pada refactor fields model QGIS).
KOLOM_HASIL: tuple[str, ...] = (
    "assignment_id",
    "unique_bang",
    "flag_psls",
    "flag_repair_initial",
    "flag_repair",
    "level_6_full_code",
    "idsubsls_origin",
    "latitude_origin",
    "longitude_origin",
    "no_bang",
    "kode_bang_value",
    "ada_keluarga_value",
    "ada_bang_usaha_value",
    "jumlah_usaha_ditemukan",
    "kdprov",
    "nmprov",
    "kdkab",
    "nmkab",
    "kdkec",
    "nmkec",
    "kddesa",
    "nmdesa",
    "nmsls",
    "kk",
    "btt",
    "bku",
    "bttk",
    "bbtt",
    "usaha",
    "nama_usaha_bang",
)

# Nilai pembentuk indikator, sesuai rumus if() pada model QGIS.
NILAI_KK: tuple[int, ...] = (1, 2)  # ada_keluarga_value
NILAI_BTT: tuple[int, ...] = (2, 3)  # kode_bang_value
NILAI_BKU: tuple[int, ...] = (1,)
NILAI_BTTK: tuple[int, ...] = (12,)
NILAI_BBTT: tuple[int, ...] = (4, 5, 6)


def pastikan_crs4326(gdf: gpd.GeoDataFrame, nama: str) -> gpd.GeoDataFrame:
    """Kembalikan GeoDataFrame dalam EPSG:4326 (tanpa mengubah objek asal)."""
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError(f"{nama} harus GeoDataFrame, bukan {type(gdf).__name__}")
    if gdf.crs is None:
        # GeoJSON kadang tanpa crs tegas; model QGIS memakainya sebagai EPSG:4326.
        return gdf.set_crs(CRS_TARGET)
    if gdf.crs != CRS_TARGET:
        return gdf.to_crs(CRS_TARGET)
    return gdf


def cek_kolom(gdf: gpd.GeoDataFrame, kolom: tuple[str, ...], nama: str) -> None:
    """Pastikan semua kolom wajib ada; kalau tidak, lempar ValueError."""
    kurang = [k for k in kolom if k not in gdf.columns]
    if kurang:
        raise ValueError(f"{nama} kurang kolom: {', '.join(kurang)}")


def _angka(series: pd.Series) -> pd.Series:
    """Ubah kolom jadi angka; nilai yang tak terbaca jadi NaN (perilaku QGIS)."""
    return pd.to_numeric(series, errors="coerce")


def _flag(series: pd.Series, nilai: tuple[int, ...]) -> pd.Series:
    """Pola ``if(kolom IN (nilai), 1, 0)`` pada model QGIS."""
    return _angka(series).isin(nilai).astype("int8")


def proses_a(titik: gpd.GeoDataFrame, peta: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Jalankan Proses A (identifikasi titik) sesuai model QGIS.

    Parameters
    ----------
    titik : GeoDataFrame
        Titik bangunan. Wajib punya kolom ``KOLOM_TITIK``.
    peta : GeoDataFrame
        Poligon batas wilkerstat. Wajib punya kolom ``KOLOM_PETA``.

    Returns
    -------
    GeoDataFrame
        Kolom ``KOLOM_HASIL`` (urutan sama dengan model QGIS) + geometri titik
        dalam EPSG:4326, ``assignment_id`` unik. Urutan baris meniru QGIS:
        terkelompok per poligon mengikuti urutan ``peta`` (di dalam poligon
        mengikuti urutan ``titik``), lalu titik yang tidak cocok di paling
        akhir. Index tiap baris = index asli ``titik``.

    Notes
    -----
    Bila beberapa poligon cocok untuk satu titik (titik tepat di garis batas),
    dipakai poligon yang **pertama** pada urutan ``peta`` — sama seperti
    ``METHOD=1`` (first matching feature) di QGIS.

    Untuk ``assignment_id`` yang muncul lebih dari sekali, baris **pertama**
    pada urutan hasil di atas yang dipertahankan (perilaku
    ``removeduplicatesbyattribute``), sisanya dibuang. Model QGIS tidak punya
    aturan lain, jadi urutan baris masukan ``titik`` ikut menentukan.
    """
    titik_4326 = pastikan_crs4326(titik, "titik")
    peta_4326 = pastikan_crs4326(peta, "peta")
    cek_kolom(titik_4326, KOLOM_TITIK, "titik")
    cek_kolom(peta_4326, KOLOM_PETA, "peta")

    # Simpan index asli supaya hasil bisa ditelusuri; urutan baris pakai _urut.
    indeks_asli = titik_4326.index
    titik_urut = titik_4326.reset_index(drop=True)
    titik_urut["_urut"] = range(len(titik_urut))

    # Poligon diberi nomor urut; join memakai kolom wilayah saja (JOIN_FIELDS).
    nama_geom_peta = peta_4326.geometry.name
    peta_urut = peta_4326.reset_index(drop=True)[list(KOLOM_PETA) + [nama_geom_peta]].copy()
    peta_urut["_posisi"] = range(len(peta_urut))

    # Join attributes by location: intersects, titik tak cocok tetap ada.
    gabung = gpd.sjoin(titik_urut, peta_urut, how="left", predicate="intersects")

    # METHOD=1: ambil poligon pertama (urutan peta) untuk tiap titik.
    gabung = gabung.sort_values(["_urut", "_posisi"], kind="stable")
    gabung = gabung.drop_duplicates(subset="_urut", keep="first")

    # Urutan output joinattributesbylocation (METHOD=1) di QGIS: algoritme
    # mengiterasi peta poligon demi poligon, jadi baris terkelompok per poligon
    # (urutan peta, lalu urutan titik); titik yang tidak cocok ditambahkan
    # paling akhir lewat mergevectorlayers (OUTPUT + NON_MATCHING).
    cocok = gabung["_posisi"].notna()
    gabung = pd.concat(
        [
            gabung[cocok].sort_values(["_posisi", "_urut"], kind="stable"),
            gabung[~cocok].sort_values("_urut", kind="stable"),
        ]
    )

    # mergevectorlayers + removeduplicatesbyattribute(assignment_id):
    # QGIS mempertahankan baris PERTAMA yang ditemui, sisanya dibuang.
    gabung = gabung.drop_duplicates(subset="assignment_id", keep="first")

    urut = gabung["_urut"].to_numpy()

    # Susun 30 kolom hasil sesuai urutan refactor fields model QGIS.
    hasil = pd.DataFrame(index=gabung.index)
    hasil["assignment_id"] = gabung["assignment_id"].to_numpy()
    hasil["unique_bang"] = gabung["unique_bang"].to_numpy()
    hasil["flag_psls"] = gabung["flag_psls"].to_numpy()

    # if("idsubsls" = "level_6_full_code", 0, 1); idsubsls kosong (tak cocok)
    # diperlakukan berbeda dari level_6_full_code → 1, sama seperti QGIS.
    beda = (gabung["idsubsls"].to_numpy() != gabung["level_6_full_code"].to_numpy())
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

    hasil = gpd.GeoDataFrame(
        hasil,
        geometry=titik_urut.geometry.to_numpy()[urut],
        crs=CRS_TARGET,
    )
    hasil.index = indeks_asli.to_numpy()[urut]
    return hasil[list(KOLOM_HASIL) + ["geometry"]]
