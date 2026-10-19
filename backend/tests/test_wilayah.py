"""Tes dimensi wilayah: pemuatan dari peta, upsert (tanpa menghapus), pencarian id."""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import wilayah as modul
from app.models import Wilayah

# Kode SubSLS 16 angka seperti berkas peta asli (kdkab pendek: "07").
KODE_SUBSLS = "3307010001000100"
KODE_SLS = "33070100010001"


def baris_peta(idsubsls: str = KODE_SUBSLS, nmsls: str = "SLS 001") -> dict[str, object]:
    """Satu baris peta lengkap (tanpa geometri)."""
    return {
        "idsubsls": idsubsls,
        "idsls": KODE_SLS,
        "nmsls": nmsls,
        "kdprov": "33",
        "nmprov": "JAWA TENGAH",
        "kdkab": "07",
        "nmkab": "WONOSOBO",
        "kdkec": "010",
        "nmkec": "MOJOTENGAH",
        "kddesa": "001",
        "nmdesa": "KALIBEBER",
    }


def peta_uji(nmsls: str = "SLS 001", *, tambahan: list[str] | None = None) -> gpd.GeoDataFrame:
    """Peta kecil: beberapa SubSLS (kode BPS pendek seperti berkas asli)."""
    baris = [
        {**baris_peta(nmsls=nmsls), "geometry": box(0, 0, 1, 1)},
        *[
            {**baris_peta(kode), "geometry": box(2, 2, 3, 3)}
            for kode in (tambahan or [])
        ],
    ]
    return gpd.GeoDataFrame(baris, crs="EPSG:4326")


def test_bersih_menyeragamkan_nilai() -> None:
    """Nilai kosong/NaN jadi None; teks dirapikan spasi tepinya."""
    assert modul.bersih(None) is None
    assert modul.bersih("   ") is None
    assert modul.bersih(float("nan")) is None
    assert modul.bersih(" A1 ") == "A1"
    assert modul.bersih(7) == "7"


def test_baris_dari_peta_unik_dan_tanpa_geometri() -> None:
    """Peta bisa punya poligon berulang per SubSLS: dimensi hanya satu baris."""
    peta_ulang = gpd.GeoDataFrame(
        [
            {**baris_peta(nmsls="SLS 001"), "geometry": box(0, 0, 1, 1)},
            {**baris_peta(nmsls="DUPLIKAT"), "geometry": box(1, 1, 2, 2)},
        ],
        crs="EPSG:4326",
    )

    baris = modul.baris_dari_peta(peta_ulang)

    assert len(baris) == 1
    assert baris[0]["idsubsls"] == KODE_SUBSLS
    assert baris[0]["nmsls"] == "SLS 001"  # baris pertama yang dipertahankan
    assert "geometry" not in baris[0]
    assert set(baris[0]) == set(modul.KOLOM_DIMENSI)

    assert modul.baris_dari_peta(peta_uji())[0]["kdkab"] == "07"


def test_baris_dari_peta_menolak_kolom_kurang() -> None:
    """Peta tanpa kolom wilayah ditolak dengan pesan jelas."""
    peta = gpd.GeoDataFrame(
        [{"idsubsls": KODE_SUBSLS, "geometry": box(0, 0, 1, 1)}], crs="EPSG:4326"
    )
    with pytest.raises(ValueError, match="kurang kolom wilayah"):
        modul.baris_dari_peta(peta)


def test_peta_id_hanya_kode_yang_ada_di_wilayah(sesi: Session) -> None:
    """Kode yang tidak ada di ``wilayah`` dibiarkan tanpa id (tidak dibuatkan baris).

    Titik dengan kode seperti itu disimpan dengan kolom wilayah NULL dan dihitung
    pada kategori "(tanpa wilayah)" rekap, jadi tabel dimensi tetap bersih.
    """
    modul.upsert(sesi, modul.baris_dari_peta(peta_uji()))
    sesi.commit()

    id_wilayah = modul.peta_id(sesi, [KODE_SUBSLS, "A1", None, "  ", KODE_SUBSLS])

    assert set(id_wilayah) == {KODE_SUBSLS}
    assert id_wilayah[KODE_SUBSLS] == sesi.scalar(
        select(Wilayah.id).where(Wilayah.idsubsls == KODE_SUBSLS)
    )
    assert sesi.scalar(select(func.count()).select_from(Wilayah)) == 1
    # panggilan berikutnya dengan kode tak dikenal juga tidak menambah baris
    assert modul.peta_id(sesi, ["A1"]) == {}
    assert sesi.scalar(select(func.count()).select_from(Wilayah)) == 1


def test_upsert_menambah_menyegarkan_dan_tidak_menghapus(sesi: Session) -> None:
    """Upsert wilayah: baris baru ditambah, nama lama disegarkan, tidak ada yang dihapus."""
    kode_lain = f"{KODE_SUBSLS[:-2]}01"

    assert modul.upsert(sesi, modul.baris_dari_peta(peta_uji())) == 1
    assert modul.upsert(sesi, modul.baris_dari_peta(peta_uji(tambahan=[kode_lain]))) == 2
    # Peta berikutnya dengan nama baru: baris lama disegarkan, bukan diduplikasi.
    modul.upsert(sesi, [baris_peta(nmsls="NAMA BARU")])
    sesi.commit()

    semua = {satu.idsubsls: satu for satu in sesi.scalars(select(Wilayah))}
    assert set(semua) == {KODE_SUBSLS, kode_lain}
    assert semua[KODE_SUBSLS].nmsls == "NAMA BARU", "nama lama harus disegarkan"
    assert semua[KODE_SUBSLS].nmkec == "MOJOTENGAH"
    assert sesi.scalar(select(func.count()).select_from(Wilayah)) == 2
