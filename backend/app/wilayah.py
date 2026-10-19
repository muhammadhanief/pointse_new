"""Dimensi wilayah (tabel ``wilayah``): pemuatan dari peta dan pencarian id.

``titik_hasil`` menyimpan ``wilayah_asal_id``/``wilayah_edit_id`` (bukan kode dan
nama wilayah), dan rekap per SubSLS juga menunjuk ke tabel ini, jadi satu kode
``idsubsls`` cukup punya satu baris. Aturan yang dipegang: **hanya upsert, tidak
pernah menghapus** (peta berikutnya menyegarkan nama, bukan menghapus baris lama).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import geopandas as gpd
import pandas as pd
from sqlalchemy import bindparam, insert, select, update
from sqlalchemy.orm import Session

from app.models import Wilayah

# Kolom dimensi yang disimpan dari peta (tanpa geometri).
KOLOM_DIMENSI: tuple[str, ...] = (
    "idsubsls",
    "idsls",
    "nmsls",
    "kdprov",
    "nmprov",
    "kdkab",
    "nmkab",
    "kdkec",
    "nmkec",
    "kddesa",
    "nmdesa",
)

# Kolom yang disegarkan saat upsert (kunci ``idsubsls`` tidak ikut diubah).
KOLOM_SEGAR: tuple[str, ...] = KOLOM_DIMENSI[1:]

# Potongan kode BPS pada ``idsubsls`` (16 angka, contoh 3307010001000100):
# prov(2) kab(2) kec(3) desa(3) sls(4) subsls(2) -- kode disimpan pendek
# mengikuti berkas peta, mis. kdkab = "07", kddesa = "001".
BATAS_KODE: dict[str, tuple[int, int]] = {
    "kdprov": (0, 2),
    "kdkab": (2, 4),
    "kdkec": (4, 7),
    "kddesa": (7, 10),
}
PANJANG_IDSLS = 14

#: Jumlah baris per perintah SQL (upsert/pencarian).
UKURAN_UPSERT = 1000


def bersih(nilai: Any) -> str | None:
    """Teks tanpa spasi tepi; kosong/NULL jadi ``None``."""
    if nilai is None:
        return None
    try:
        if pd.isna(nilai):
            return None
    except (TypeError, ValueError):
        pass
    teks = str(nilai).strip()
    return teks or None


def _potong(daftar: Sequence[Any], ukuran: int) -> Iterator[Sequence[Any]]:
    """Potong daftar jadi beberapa bagian sebesar ``ukuran``."""
    for mulai in range(0, len(daftar), ukuran):
        yield daftar[mulai : mulai + ukuran]


def kode_induk(idsubsls: object) -> dict[str, str | None]:
    """Turunkan kode induk (prov/kab/kec/desa) dari kode ``idsubsls``."""
    kode = bersih(idsubsls)
    if not kode or len(kode) < PANJANG_IDSLS:
        return {nama: None for nama in (*BATAS_KODE, "idsls")}
    induk: dict[str, str | None] = {
        nama: kode[mulai:sampai] for nama, (mulai, sampai) in BATAS_KODE.items()
    }
    induk["idsls"] = kode[:PANJANG_IDSLS]
    return induk


def baris_dari_peta(peta: gpd.GeoDataFrame) -> list[dict[str, object]]:
    """Ambil baris dimensi wilayah dari peta (satu baris per ``idsubsls``)."""
    kurang = [kolom for kolom in KOLOM_DIMENSI if kolom not in peta.columns]
    if kurang:
        raise ValueError(f"peta kurang kolom wilayah: {', '.join(kurang)}")

    kerangka = pd.DataFrame(
        {kolom: [bersih(nilai) for nilai in peta[kolom]] for kolom in KOLOM_DIMENSI}
    )
    kerangka = kerangka.dropna(subset=["idsubsls"])
    kerangka = kerangka.drop_duplicates(subset=["idsubsls"], keep="first")
    return kerangka.to_dict("records")


def baris_minimal(idsubsls: object) -> dict[str, object]:
    """Baris dimensi seadanya (tanpa nama) untuk kode yang belum ada di peta.

    Dipakai supaya titik dengan kode SubSLS di luar peta yang diunggah tetap
    punya ``wilayah_id`` (bukan NULL) sehingga tidak hilang dari rekap.
    """
    kode = bersih(idsubsls)
    if kode is None:
        raise ValueError("idsubsls kosong")
    baris: dict[str, object] = {"idsubsls": kode, "nmsls": None}
    baris.update({nama: None for nama in ("nmprov", "nmkab", "nmkec", "nmdesa")})
    baris.update(kode_induk(kode))
    return baris


def upsert(sesi: Session, baris: Sequence[dict[str, object]]) -> int:
    """Tambah/perbarui baris dimensi (kunci ``idsubsls``); kembalikan jumlah baris."""
    jumlah = 0
    for potongan in _potong(baris, UKURAN_UPSERT):
        kode = [satu["idsubsls"] for satu in potongan]
        ada = set(
            sesi.scalars(select(Wilayah.idsubsls).where(Wilayah.idsubsls.in_(kode)))
        )
        baru = [satu for satu in potongan if satu["idsubsls"] not in ada]
        lama = [satu for satu in potongan if satu["idsubsls"] in ada]

        if baru:
            sesi.execute(insert(Wilayah.__table__), baru)
        if lama:
            # Lewat ``Table`` (bukan kelas ORM) supaya dieksekusi sebagai Core:
            # update per baris lewat executemany, bukan bulk update ORM.
            perintah = (
                update(Wilayah.__table__)
                .where(Wilayah.__table__.c.idsubsls == bindparam("kunci"))
                .values({kolom: bindparam(kolom) for kolom in KOLOM_SEGAR})
            )
            sesi.execute(
                perintah,
                [
                    {"kunci": satu["idsubsls"], **{kolom: satu[kolom] for kolom in KOLOM_SEGAR}}
                    for satu in lama
                ],
            )
        jumlah += len(potongan)
    sesi.flush()
    return jumlah


def peta_id(sesi: Session, kode: Iterable[object]) -> dict[str, int]:
    """Kembalikan ``idsubsls -> wilayah.id`` untuk kode yang dipakai.

    Kode yang belum ada di ``wilayah`` dilengkapi lebih dulu dengan
    :func:`baris_minimal` (nama kosong, kode induk diturunkan dari kodenya).
    """
    kode_unik = sorted({kunci for kunci in map(bersih, kode) if kunci})
    hasil: dict[str, int] = {}

    for _ in range(2):
        dicari = [kunci for kunci in kode_unik if kunci not in hasil]
        for potongan in _potong(dicari, UKURAN_UPSERT):
            baris = sesi.execute(
                select(Wilayah.id, Wilayah.idsubsls).where(Wilayah.idsubsls.in_(potongan))
            )
            for id_baris, idsubsls in baris:
                kunci = bersih(idsubsls)
                if kunci:
                    hasil[kunci] = int(id_baris)

        kurang = [kunci for kunci in kode_unik if kunci not in hasil]
        if not kurang:
            break
        upsert(sesi, [baris_minimal(kunci) for kunci in kurang])

    return hasil
