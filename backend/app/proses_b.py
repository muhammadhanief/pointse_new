"""Proses B: pengecekan titik hasil penggeseran terhadap peta wilkerstat lama.

Replikasi model QGIS ``02 Pengecekan Titik.model3``:

1. masukan: titik hasil pengolahan (keluaran Proses A yang sudah diedit/digeser)
   dan peta wilkerstat lama lapangan. Model **tidak** punya node ``reprojectlayer``,
   jadi CRS kedua masukan dipakai apa adanya (dianggap sudah sama);
2. ``refactorfields`` tahap 1: tambah ``latitude_edited``/``longitude_edited``
   (dari ``$y``/``$x`` geometri) dan
   ``flag_edit_atr_repair = if("flag_repair" != "flag_repair_initial", 1, 0)``;
3. ``joinattributesbylocation`` ke peta lama dengan aturan sama seperti Proses A
   (predikat intersects, poligon pertama, titik tak cocok dipertahankan);
4. ``mergevectorlayers`` + ``removeduplicatesbyattribute`` pada ``assignment_id``;
5. ``refactorfields`` tahap 2 dan 3: hitung ``flag_position``, ``flag_repair_initial``
   baru, dan ``flag_repair`` akhir, hasilnya 35 kolom.

Modul ini murni: fungsinya hanya menerima GeoDataFrame dan mengembalikan hasil,
tanpa membaca file dan tanpa mengakses basis data.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from app.proses_a import KOLOM_PETA, cek_kolom

# Kolom titik hasil pengolahan yang wajib ada (keluaran Proses A + geometri).
KOLOM_TITIK_B: tuple[str, ...] = (
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
    "kk",
    "btt",
    "bku",
    "bttk",
    "bbtt",
    "usaha",
    "nama_usaha_bang",
)

# Urutan 35 kolom keluaran (FIELDS_MAPPING refactorfields_4 pada model QGIS).
KOLOM_HASIL_B: tuple[str, ...] = (
    "assignment_id",
    "unique_bang",
    "flag_psls",
    "flag_position",
    "flag_edit_atr_repair",
    "flag_repair_initial",
    "flag_repair",
    "level_6_full_code",
    "idsubsls_origin",
    "idsubsls_edited",
    "latitude_origin",
    "longitude_origin",
    "latitude_edited",
    "longitude_edited",
    "no_bang",
    "kode_bang_value",
    "ada_keluarga_value",
    "ada_bang_usaha_value",
    "jumlah_usaha_ditemukan",
    "kk",
    "btt",
    "bku",
    "bttk",
    "bbtt",
    "usaha",
    "kdprov",
    "nmprov",
    "kdkab",
    "nmkab",
    "kdkec",
    "nmkec",
    "kddesa",
    "nmdesa",
    "nmsls",
    "nama_usaha_bang",
)


def _sama(kiri: pd.Series, kanan: pd.Series) -> pd.Series:
    """Perbandingan ``=`` ala QGIS; nilai kosong (NULL) selalu False.

    Di QGIS ``a = b`` memakai perbandingan angka bila salah satu sisi angka
    (teks angka dikonversi dulu), selain itu perbandingan teks. Bila salah satu
    sisi NULL hasilnya NULL, dan ``if(NULL, ...)`` mengambil cabang salah —
    jadi di sini NULL selalu dianggap tidak sama.
    """
    if pd.api.types.is_numeric_dtype(kiri) or pd.api.types.is_numeric_dtype(kanan):
        a = pd.to_numeric(kiri, errors="coerce")
        b = pd.to_numeric(kanan, errors="coerce")
        return (a == b) & a.notna() & b.notna()

    a = kiri.astype("string")
    b = kanan.astype("string")
    return (a == b) & a.notna() & b.notna()


def _flag_tanpa_kosong(nilai: pd.Series) -> pd.Series:
    """Ubah hasil hitung jadi ``int8``; kalau ada nilai kosong pakai ``Int8``."""
    return nilai.astype("int8") if not nilai.isna().any() else nilai.astype("Int8")


def _proses_b_inti(
    titik: gpd.GeoDataFrame, peta: gpd.GeoDataFrame, urut_awal: int = 0
) -> gpd.GeoDataFrame:
    """Inti Proses B; juga dipakai per potongan titik (mode hemat memori).

    Selain 35 kolom hasil, keluaran menyertakan kolom bantu ``_posisi`` dan
    ``_urut`` untuk menggabungkan potongan dengan urutan yang sama seperti
    :func:`proses_b` (lihat :func:`app.proses_a._proses_a_inti`).
    """
    if not isinstance(titik, gpd.GeoDataFrame):
        raise TypeError(f"titik harus GeoDataFrame, bukan {type(titik).__name__}")
    if not isinstance(peta, gpd.GeoDataFrame):
        raise TypeError(f"peta harus GeoDataFrame, bukan {type(peta).__name__}")
    cek_kolom(titik, KOLOM_TITIK_B, "titik")
    cek_kolom(peta, KOLOM_PETA, "peta")

    indeks_asli = titik.index
    titik_urut = titik.reset_index(drop=True).copy()
    titik_urut["_urut"] = range(urut_awal, urut_awal + len(titik_urut))
    # refactorfields tahap 1: $y / $x geometri titik saat ini.
    titik_urut["_latitude_edited"] = titik_urut.geometry.y.astype("float64")
    titik_urut["_longitude_edited"] = titik_urut.geometry.x.astype("float64")

    # Kolom peta diberi awalan: titik masukan biasanya sudah punya kdprov..nmsls
    # (keluaran Proses A), dan joinattributesbylocation memakai nilai dari peta.
    nama_geom_peta = peta.geometry.name
    peta_urut = peta.reset_index(drop=True)[list(KOLOM_PETA) + [nama_geom_peta]].copy()
    peta_urut = peta_urut.rename(columns={kol: f"_peta_{kol}" for kol in KOLOM_PETA})
    peta_urut["_posisi"] = range(len(peta_urut))

    # joinattributesbylocation ke peta lama (aturan sama dengan Proses A).
    gabung = gpd.sjoin(titik_urut, peta_urut, how="left", predicate="intersects")

    # Poligon pertama (urutan peta) untuk tiap titik.
    gabung = gabung.sort_values(["_urut", "_posisi"], kind="stable")
    gabung = gabung.drop_duplicates(subset="_urut", keep="first")

    # Urutan seperti QGIS: kelompok per poligon, titik tak cocok di akhir.
    cocok = gabung["_posisi"].notna()
    gabung = pd.concat(
        [
            gabung[cocok].sort_values(["_posisi", "_urut"], kind="stable"),
            gabung[~cocok].sort_values("_urut", kind="stable"),
        ]
    )

    # mergevectorlayers + removeduplicatesbyattribute(assignment_id).
    gabung = gabung.drop_duplicates(subset="assignment_id", keep="first")

    urut = gabung["_urut"].to_numpy()
    # Posisi baris di potongan ini (lihat _proses_a_inti).
    posisi_lokal = urut - urut_awal

    # ---- refactorfields tahap 2: flag_edit_atr_repair, flag_position, flag_repair_initial ----
    flag_repair_awal = pd.to_numeric(gabung["flag_repair"], errors="coerce")
    flag_repair_initial_awal = pd.to_numeric(gabung["flag_repair_initial"], errors="coerce")

    # if("flag_repair" != "flag_repair_initial", 1, 0); NULL → 0.
    flag_edit = (
        ~_sama(gabung["flag_repair"], gabung["flag_repair_initial"])
        & flag_repair_awal.notna()
        & flag_repair_initial_awal.notna()
    )

    # if("latitude_origin" = "latitude_edited", 0, 1) — model asli hanya latitude.
    flag_position = ~_sama(gabung["latitude_origin"], gabung["_latitude_edited"])

    # if("level_6_full_code" = "idsubsls", 0, 1) dengan idsubsls = hasil join baru.
    flag_repair_initial_baru = ~_sama(gabung["level_6_full_code"], gabung["_peta_idsubsls"])

    # ---- refactorfields tahap 3: flag_repair akhir ----
    # if("flag_repair" = 1 AND "flag_repair_initial" = 0, 0,
    #    if("flag_repair_initial" = 1 AND "flag_edit_atr_repair" = 0, 1, "flag_repair"))
    flag_repair_akhir = flag_repair_awal.to_numpy(dtype="float64", copy=True)
    flag_repair_akhir[(flag_repair_awal == 1).to_numpy() & ~flag_repair_initial_baru.to_numpy()] = 0
    flag_repair_akhir[
        flag_repair_initial_baru.to_numpy() & ~flag_edit.to_numpy()
    ] = 1

    # ---- susun 35 kolom keluaran ----
    hasil = pd.DataFrame(index=gabung.index)
    hasil["assignment_id"] = gabung["assignment_id"].to_numpy()
    hasil["unique_bang"] = gabung["unique_bang"].to_numpy()
    hasil["flag_psls"] = gabung["flag_psls"].to_numpy()
    hasil["flag_position"] = _flag_tanpa_kosong(flag_position).to_numpy()
    hasil["flag_edit_atr_repair"] = _flag_tanpa_kosong(flag_edit).to_numpy()
    hasil["flag_repair_initial"] = _flag_tanpa_kosong(flag_repair_initial_baru).to_numpy()
    hasil["flag_repair"] = _flag_tanpa_kosong(pd.Series(flag_repair_akhir)).to_numpy()
    # Nilai apa adanya dari berkas unggahan (sebelum dihitung ulang model).
    # Tidak termasuk KOLOM_HASIL_B supaya keluaran GPKG tetap 35 kolom QGIS.
    hasil["flag_repair_unggah"] = _flag_tanpa_kosong(flag_repair_awal).to_numpy()
    hasil["level_6_full_code"] = gabung["level_6_full_code"].to_numpy()
    hasil["idsubsls_origin"] = gabung["idsubsls_origin"].to_numpy()
    hasil["idsubsls_edited"] = gabung["_peta_idsubsls"].to_numpy()
    hasil["latitude_origin"] = gabung["latitude_origin"].to_numpy()
    hasil["longitude_origin"] = gabung["longitude_origin"].to_numpy()
    hasil["latitude_edited"] = gabung["_latitude_edited"].to_numpy()
    hasil["longitude_edited"] = gabung["_longitude_edited"].to_numpy()
    hasil["no_bang"] = gabung["no_bang"].to_numpy()
    hasil["kode_bang_value"] = gabung["kode_bang_value"].to_numpy()
    hasil["ada_keluarga_value"] = gabung["ada_keluarga_value"].to_numpy()
    hasil["ada_bang_usaha_value"] = gabung["ada_bang_usaha_value"].to_numpy()
    hasil["jumlah_usaha_ditemukan"] = gabung["jumlah_usaha_ditemukan"].to_numpy()
    hasil["kk"] = gabung["kk"].to_numpy()
    hasil["btt"] = gabung["btt"].to_numpy()
    hasil["bku"] = gabung["bku"].to_numpy()
    hasil["bttk"] = gabung["bttk"].to_numpy()
    hasil["bbtt"] = gabung["bbtt"].to_numpy()
    hasil["usaha"] = gabung["usaha"].to_numpy()
    hasil["kdprov"] = gabung["_peta_kdprov"].to_numpy()
    hasil["nmprov"] = gabung["_peta_nmprov"].to_numpy()
    hasil["kdkab"] = gabung["_peta_kdkab"].to_numpy()
    hasil["nmkab"] = gabung["_peta_nmkab"].to_numpy()
    hasil["kdkec"] = gabung["_peta_kdkec"].to_numpy()
    hasil["nmkec"] = gabung["_peta_nmkec"].to_numpy()
    hasil["kddesa"] = gabung["_peta_kddesa"].to_numpy()
    hasil["nmdesa"] = gabung["_peta_nmdesa"].to_numpy()
    hasil["nmsls"] = gabung["_peta_nmsls"].to_numpy()
    hasil["nama_usaha_bang"] = gabung["nama_usaha_bang"].to_numpy()

    # Kolom bantu untuk penggabungan potongan (tidak ikut keluaran proses_b).
    hasil["_posisi"] = gabung["_posisi"].to_numpy()
    hasil["_urut"] = gabung["_urut"].to_numpy()

    hasil = gpd.GeoDataFrame(
        hasil,
        geometry=titik_urut.geometry.to_numpy()[posisi_lokal],
        crs=titik.crs,
    )
    hasil.index = indeks_asli.to_numpy()[posisi_lokal]
    return hasil[
        list(KOLOM_HASIL_B) + ["flag_repair_unggah", "_posisi", "_urut", "geometry"]
    ]


def proses_b(titik: gpd.GeoDataFrame, peta: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Jalankan Proses B (pengecekan titik hasil penggeseran) sesuai model QGIS.

    Parameters
    ----------
    titik : GeoDataFrame
        Titik hasil pengolahan (keluaran :func:`app.proses_a.proses_a` yang
        sudah diedit/digeser). Wajib punya kolom ``KOLOM_TITIK_B``.
    peta : GeoDataFrame
        Peta batas wilkerstat **lama** lapangan. Wajib punya kolom ``KOLOM_PETA``.

    Returns
    -------
    GeoDataFrame
        Kolom ``KOLOM_HASIL_B`` (urutan sama dengan model QGIS) + geometri titik
        dalam CRS masukan. Urutan baris seperti Proses A: terkelompok per
        poligon peta lama (urutan peta), titik tak cocok di akhir; index-nya
        index asli ``titik``. ``assignment_id`` unik.

    Notes
    -----
    Model 02 tidak punya node reproject, jadi kedua masukan dianggap ber-CRS
    sama (pemanggil yang bertanggung jawab menyiapkannya, mis. lapisan API).

    Aturan join, penghapusan duplikat, dan urutan baris mengikuti Proses A
    (lihat :mod:`app.proses_a`), karena model QGIS-nya memakai node yang sama.
    """
    hasil = _proses_b_inti(titik, peta)
    return hasil[list(KOLOM_HASIL_B) + ["flag_repair_unggah", "geometry"]]


def proses_b_potongan(
    titik: gpd.GeoDataFrame, peta: gpd.GeoDataFrame, urut_awal: int = 0
) -> gpd.GeoDataFrame:
    """Proses B untuk **satu potongan** titik (mode hemat memori).

    Aturan hitungnya sama dengan :func:`proses_b`. Pemanggil yang menyiapkan
    CRS (model 02 tidak punya node reproject) dan menggabungkan potongan
    memakai kolom bantu ``_posisi``/``_urut``.
    """
    return _proses_b_inti(titik, peta, urut_awal)

