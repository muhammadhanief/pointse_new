"""Tes unit Proses A (tanpa data uji, tanpa file)."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from app.proses_a import KOLOM_HASIL, proses_a

# Nilai default kolom titik; bisa ditimpa per baris lewat dict di daftar baris.
DEFAULT_TITIK: dict[str, object] = {
    "unique_bang": "3307070005001400#0001",
    "flag_psls": 0,
    "level_6_full_code": "3307070005001400",
    "geotag_latitude": -7.1,
    "geotag_longitude": 109.1,
    "no_bang": "0001",
    "kode_bang_value": "3",
    "ada_keluarga_value": "1",
    "ada_bang_usaha_value": None,
    "count_usaha": "0",
    "nama_usaha_bang": None,
}


def buat_titik(baris: list[dict], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """Bangun GeoDataFrame titik dari daftar dict (wajib ada x, y, assignment_id)."""
    jumlah = len(baris)
    df = pd.DataFrame(baris)
    geometri = [Point(r["x"], r["y"]) for r in baris]
    df = df.drop(columns=["x", "y"])
    for kolom, nilai in DEFAULT_TITIK.items():
        if kolom not in df.columns:
            df[kolom] = [nilai] * jumlah
    return gpd.GeoDataFrame(df, geometry=geometri, crs=crs)


def buat_peta(idsubsls: tuple[str, ...], geometri: list) -> gpd.GeoDataFrame:
    """Peta dua poligon bersebelahan (berbagi garis batas x = 1)."""
    return gpd.GeoDataFrame(
        {
            "kdprov": ["33"] * len(idsubsls),
            "nmprov": ["JAWA TENGAH"] * len(idsubsls),
            "kdkab": ["07"] * len(idsubsls),
            "nmkab": ["WONOSOBO"] * len(idsubsls),
            "kdkec": ["070"] * len(idsubsls),
            "nmkec": ["KALIKAJAR"] * len(idsubsls),
            "kddesa": ["005"] * len(idsubsls),
            "nmdesa": ["REJOSARI"] * len(idsubsls),
            "idsls": [f"SLS{i}" for i in range(len(idsubsls))],
            "nmsls": [f"NAMA SLS {i}" for i in range(len(idsubsls))],
            "idsubsls": list(idsubsls),
        },
        geometry=geometri,
        crs="EPSG:4326",
    )


PETA_DUA = buat_peta(
    ("3307070005001400", "3307070005001500"),
    [box(0, 0, 1, 1), box(1, 0, 2, 1)],
)


def test_kolom_dan_urutan_hasil() -> None:
    """Hasil punya 30 kolom KOLOM_HASIL dengan urutan sama seperti model QGIS."""
    hasil = proses_a(buat_titik([{"assignment_id": "a1", "x": 0.5, "y": 0.5}]), PETA_DUA)
    assert list(hasil.columns) == list(KOLOM_HASIL) + ["geometry"]
    assert hasil.crs is not None and hasil.crs.to_epsg() == 4326


def test_titik_di_dalam_poligon() -> None:
    """Titik di dalam poligon dapat kolom wilayah dan flag_repair 0."""
    hasil = proses_a(buat_titik([{"assignment_id": "a1", "x": 0.5, "y": 0.5}]), PETA_DUA)
    baris = hasil.iloc[0]
    assert baris["idsubsls_origin"] == "3307070005001400"
    assert baris["kdprov"] == "33"
    assert baris["nmsls"] == "NAMA SLS 0"
    assert baris["flag_repair_initial"] == 0
    assert baris["flag_repair"] == 0


def test_titik_di_luar_peta_tetap_ada() -> None:
    """Titik tak cocok tetap dipertahankan; kolom wilayah kosong dan flag_repair 1."""
    hasil = proses_a(buat_titik([{"assignment_id": "a1", "x": 9.0, "y": 9.0}]), PETA_DUA)
    assert len(hasil) == 1
    baris = hasil.iloc[0]
    assert pd.isna(baris["idsubsls_origin"])
    assert pd.isna(baris["kdprov"])
    assert baris["flag_repair_initial"] == 1
    assert baris["flag_repair"] == 1


def test_titik_di_garis_batas_pakai_poligon_pertama() -> None:
    """Titik di garis batas cocok ke 2 poligon; dipakai poligon pertama (x = 1)."""
    hasil = proses_a(buat_titik([{"assignment_id": "a1", "x": 1.0, "y": 0.5}]), PETA_DUA)
    assert len(hasil) == 1
    assert hasil.iloc[0]["idsubsls_origin"] == "3307070005001400"
    # dibalik urutan petanya → poligon kedua yang dipakai
    peta_terbalik = PETA_DUA.iloc[::-1].reset_index(drop=True)
    hasil2 = proses_a(buat_titik([{"assignment_id": "a1", "x": 1.0, "y": 0.5}]), peta_terbalik)
    assert hasil2.iloc[0]["idsubsls_origin"] == "3307070005001500"


def test_titik_di_luar_level_6_flag_repair_1() -> None:
    """idsubsls hasil join beda dari level_6_full_code → flag_repair 1."""
    titik = buat_titik(
        [{"assignment_id": "a1", "x": 0.5, "y": 0.5, "level_6_full_code": "3307070005009999"}]
    )
    hasil = proses_a(titik, PETA_DUA)
    assert hasil.iloc[0]["flag_repair"] == 1


def test_duplikat_assignment_id_dibuang_yang_pertama() -> None:
    """Duplikat assignment_id dibuang; yang dipertahankan kemunculan pertama."""
    titik = buat_titik(
        [
            {"assignment_id": "sama", "x": 0.5, "y": 0.5, "no_bang": "0001"},
            {"assignment_id": "sama", "x": 1.5, "y": 0.5, "no_bang": "0002"},
            {"assignment_id": "lain", "x": 1.5, "y": 0.5, "no_bang": "0003"},
        ]
    )
    hasil = proses_a(titik, PETA_DUA)
    assert list(hasil["assignment_id"]) == ["sama", "lain"]
    assert list(hasil["no_bang"]) == ["0001", "0003"]
    # urutan baris mengikuti urutan titik, index-nya index asli titik
    assert list(hasil.index) == [0, 2]


@pytest.mark.parametrize(
    ("kode_bang", "harapan"),
    [
        ("1", {"bku": 1}),
        ("2", {"btt": 1}),
        ("3", {"btt": 1}),
        ("4", {"bbtt": 1}),
        ("5", {"bbtt": 1}),
        ("6", {"bbtt": 1}),
        ("12", {"bttk": 1}),
        ("99", {}),
    ],
)
def test_rumus_kode_bang_value(kode_bang: str, harapan: dict[str, int]) -> None:
    """btt/bku/bttk/bbtt mengikuti rumus if() pada model QGIS."""
    titik = buat_titik([{"assignment_id": "a1", "x": 0.5, "y": 0.5, "kode_bang_value": kode_bang}])
    baris = proses_a(titik, PETA_DUA).iloc[0]
    for kolom in ("btt", "bku", "bttk", "bbtt"):
        assert baris[kolom] == harapan.get(kolom, 0), kolom


@pytest.mark.parametrize(("nilai", "harapan"), [("1", 1), ("2", 1), ("4", 0), ("5", 0), (None, 0)])
def test_rumus_kk(nilai: str | None, harapan: int) -> None:
    """kk = 1 bila ada_keluarga_value in (1, 2)."""
    titik = buat_titik(
        [{"assignment_id": "a1", "x": 0.5, "y": 0.5, "ada_keluarga_value": nilai}]
    )
    assert proses_a(titik, PETA_DUA).iloc[0]["kk"] == harapan


def test_kolom_turunan_identitas() -> None:
    """latitude_origin/longitude_origin/jumlah_usaha_ditemukan/usaha disalin apa adanya."""
    titik = buat_titik(
        [
            {
                "assignment_id": "a1",
                "x": 0.5,
                "y": 0.5,
                "geotag_latitude": -7.4246661,
                "geotag_longitude": 109.8690932,
                "count_usaha": "3",
            }
        ]
    )
    baris = proses_a(titik, PETA_DUA).iloc[0]
    assert baris["latitude_origin"] == pytest.approx(-7.4246661)
    assert baris["longitude_origin"] == pytest.approx(109.8690932)
    assert baris["jumlah_usaha_ditemukan"] == "3"
    assert baris["usaha"] == "3"


def test_reproject_dari_3857() -> None:
    """Titik/peta bukan EPSG:4326 di-reproject dulu, hasilnya sama."""
    titik_4326 = buat_titik([{"assignment_id": "a1", "x": 0.5, "y": 0.5}])
    hasil_biasa = proses_a(titik_4326, PETA_DUA)

    titik_3857 = titik_4326.to_crs("EPSG:3857")
    peta_3857 = PETA_DUA.to_crs("EPSG:3857")
    hasil_reproject = proses_a(titik_3857, peta_3857)

    assert hasil_reproject.iloc[0]["idsubsls_origin"] == hasil_biasa.iloc[0]["idsubsls_origin"]
    assert hasil_reproject.geometry.iloc[0].x == pytest.approx(0.5)
    assert hasil_reproject.geometry.iloc[0].y == pytest.approx(0.5)
    assert titik_3857.crs.to_epsg() == 3857  # objek asal tidak diubah


def test_tidak_mengubah_input() -> None:
    """Fungsi tidak menambah/mengubah kolom pada GeoDataFrame masukan."""
    titik = buat_titik([{"assignment_id": "a1", "x": 0.5, "y": 0.5}])
    peta = PETA_DUA.copy()
    kolom_titik = list(titik.columns)
    kolom_peta = list(peta.columns)
    proses_a(titik, peta)
    assert list(titik.columns) == kolom_titik
    assert list(peta.columns) == kolom_peta


def test_kolom_kurang_error() -> None:
    """Kolom wajib yang tidak ada memunculkan ValueError yang jelas."""
    titik = buat_titik([{"assignment_id": "a1", "x": 0.5, "y": 0.5}]).drop(columns=["no_bang"])
    with pytest.raises(ValueError, match="no_bang"):
        proses_a(titik, PETA_DUA)

    peta = PETA_DUA.drop(columns=["idsubsls"])
    with pytest.raises(ValueError, match="idsubsls"):
        proses_a(buat_titik([{"assignment_id": "a1", "x": 0.5, "y": 0.5}]), peta)


def test_bukan_geodataframe_error() -> None:
    """Masukan bukan GeoDataFrame ditolak."""
    with pytest.raises(TypeError):
        proses_a(pd.DataFrame({"assignment_id": ["a1"]}), PETA_DUA)  # type: ignore[arg-type]
