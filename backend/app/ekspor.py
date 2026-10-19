"""Ekspor CSV/GPKG: keluaran Proses A, titik perlu tindakan, dan rekap progres.

Tiga jenis ekspor (PRD §6 fitur 5):

- **Keluaran Proses A** (GPKG): dihitung ulang dari berkas mentah run dengan
  :func:`app.proses_a.proses_a`, jadi kolom dan urutannya sama persis dengan
  keluaran model QGIS. Berkas mentah hanya disimpan untuk run **baseline** dan
  **sukses terakhir** per kabupaten/kota+tipe; run lain dibalas
  :class:`EksporTidakTersedia` (HTTP 409). Hasilnya di-cache di
  ``DIR_UNGGAHAN/_ekspor`` (LRU, ``MAKS_CACHE_HASIL_A`` berkas) supaya unduhan
  berikutnya tidak memproses ulang.
- **Titik perlu tindakan** (CSV/GPKG): dibaca dari ``titik_hasil`` run (yang
  memang hanya menyimpan titik perlu perhatian), geometri disusun dari koordinat
  ``latitude_edited``/``longitude_edited`` bila ada, kalau tidak dari koordinat
  origin.
- **Rekap kabupaten/desa** (CSV): baris ``rekap_kabupaten``/``rekap_desa``
  digabung ke ``runs``, dengan saringan tipe, wilayah, dasar, dan rentang
  ``tanggal_data``.

Modul ini tidak mengubah Proses A/B; hanya membaca hasilnya.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
import uuid
from collections.abc import Iterable, Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import Point
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.config import Settings
from app.models import (
    DASAR_POSISI,
    DASAR_TUGAS,
    KOLOM_HITUNGAN,
    STATUS_SUKSES,
    TIPE_A,
    RekapDesa,
    RekapKabupaten,
    Run,
    TitikHasil,
    Wilayah,
)
from app.proses_a import proses_a
from app.worker import baca_masukan

#: Nama layer GPKG keluaran Proses A (sama dengan model QGIS).
LAYER_HASIL_A = "hasil_identifikasi_titik"
#: Nama layer GPKG titik perlu tindakan.
LAYER_TITIK = "titik_perlu_tindakan"
#: CRS ekspor titik.
CRS_EKSPOR = "EPSG:4326"
#: Folder cache GPKG keluaran Proses A (di dalam folder unggahan).
NAMA_FOLDER_CACHE = "_ekspor"
#: Jumlah GPKG keluaran Proses A yang di-cache (LRU); ±124 MB per run pada data uji.
MAKS_CACHE_HASIL_A = 2
#: Awalan nama berkas cache keluaran Proses A.
AWALAN_CACHE_HASIL_A = "hasil_a_run"
#: Jumlah baris per potongan saat menulis GPKG titik.
UKURAN_POTONGAN = 20_000
#: Batas spool CSV di memori; lebih dari ini otomatis pindah ke berkas sementara.
UKURAN_SPOOL = 8 * 1024 * 1024

#: Urutan kolom ekspor titik perlu tindakan (CSV maupun GPKG).
KOLOM_TITIK: tuple[str, ...] = (
    "urut",
    "assignment_id",
    "level_6_full_code",
    "idsubsls_tugas",
    "idsubsls_asal",
    "idsubsls_edit",
    "kdprov",
    "nmprov",
    "kdkab",
    "nmkab",
    "kdkec",
    "nmkec",
    "kddesa",
    "nmdesa",
    "nmsls",
    "flag_psls",
    "flag_repair",
    "flag_repair_initial",
    "flag_edit_atr_repair",
    "flag_position",
    "kk",
    "btt",
    "bku",
    "bttk",
    "bbtt",
    "usaha",
    "latitude_origin",
    "longitude_origin",
    "latitude_edited",
    "longitude_edited",
)

#: Kolom angka bulat pada ekspor titik (ditulis sebagai integer, boleh NULL).
KOLOM_ANGKA: tuple[str, ...] = (
    "flag_psls",
    "flag_repair",
    "flag_repair_initial",
    "flag_edit_atr_repair",
    "flag_position",
    "kk",
    "btt",
    "bku",
    "bttk",
    "bbtt",
    "usaha",
)

#: Kolom angka desimal pada ekspor titik.
KOLOM_DESIMAL: tuple[str, ...] = (
    "latitude_origin",
    "longitude_origin",
    "latitude_edited",
    "longitude_edited",
)

#: Kolom rekap kabupaten pada CSV.
KOLOM_REKAP_KABUPATEN: tuple[str, ...] = (
    "run_id",
    "tipe",
    "tanggal_data",
    "dasar",
    "kdprov",
    "nmprov",
    "kdkab",
    "nmkab",
    *KOLOM_HITUNGAN,
    "persen_progres",
)

#: Kolom rekap desa pada CSV.
KOLOM_REKAP_DESA: tuple[str, ...] = (
    "run_id",
    "tipe",
    "tanggal_data",
    "dasar",
    "kdprov",
    "nmprov",
    "kdkab",
    "nmkab",
    "kdkec",
    "nmkec",
    "kddesa",
    "nmdesa",
    *KOLOM_HITUNGAN,
    "persen_progres",
)

#: Tingkat rekap yang bisa diekspor ke CSV.
TINGKAT_EKSPOR: tuple[str, ...] = ("kabupaten", "desa")


class EksporTidakTersedia(ValueError):
    """Ekspor tidak bisa dibuat; pesannya untuk pengguna (dibalas HTTP 409)."""


class KesalahanSaringan(ValueError):
    """Saringan ekspor tidak valid; pesannya untuk pengguna (dibalas HTTP 422)."""


def _persen(belum: int, ditindak: int) -> float | None:
    """Persentase progres (rumus sama dengan ``app.layanan._persen``)."""
    penyebut = belum + ditindak
    return round(100.0 * ditindak / penyebut, 2) if penyebut else None


def _ditindak(baris: dict[str, Any]) -> int:
    """Jumlah titik ditindak = posisi benar + posisi salah."""
    return int(baris["ditindak_posisi_benar"]) + int(baris["ditindak_posisi_salah"])


# ------------------------------------------------------------------ berkas bantu


def _folder_sementara(setelan: Settings) -> Path:
    """Folder berkas sementara ekspor (di folder unggahan, bukan /tmp)."""
    folder = Path(setelan.dir_unggahan)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def berkas_sementara(akhiran: str, folder: Path | None = None) -> Path:
    """Buat berkas sementara kosong (pemanggil yang menghapusnya)."""
    berkas = tempfile.NamedTemporaryFile(
        prefix="pointse_", suffix=akhiran, dir=folder, delete=False
    )
    berkas.close()
    return Path(berkas.name)


def spool_csv(
    judul: Sequence[str], baris: Iterable[Sequence[Any]], folder: Path | None = None
) -> BinaryIO:
    """Tulis CSV ke spool (memori, pindah ke disk bila besar); posisi di awal."""
    spool = tempfile.SpooledTemporaryFile(max_size=UKURAN_SPOOL, mode="w+b", dir=folder)
    teks = io.TextIOWrapper(spool, encoding="utf-8", newline="")
    penulis = csv.writer(teks, lineterminator="\n")
    penulis.writerow(judul)
    for satu in baris:
        penulis.writerow(["" if nilai is None else nilai for nilai in satu])
    teks.flush()
    teks.detach()  # jangan tutup spool saat pembungkus teks dibuang
    spool.seek(0)
    return spool


def alirkan(spool: BinaryIO) -> Iterator[bytes]:
    """Alirkan isi spool per potongan lalu tutup."""
    try:
        while potongan := spool.read(1024 * 1024):
            yield potongan
    finally:
        spool.close()


def _potongan(baris: Iterable[dict[str, Any]], ukuran: int) -> Iterator[list[dict[str, Any]]]:
    """Kelompokkan baris jadi potongan berukuran tetap."""
    kelompok: list[dict[str, Any]] = []
    for satu in baris:
        kelompok.append(satu)
        if len(kelompok) >= ukuran:
            yield kelompok
            kelompok = []
    if kelompok:
        yield kelompok


# ------------------------------------------------------------ keluaran Proses A


def _folder_cache(setelan: Settings) -> Path:
    """Folder cache ekspor (dibuat bila belum ada)."""
    folder = Path(setelan.dir_unggahan) / NAMA_FOLDER_CACHE
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _berkas_cache(run: Run, setelan: Settings) -> Path:
    """Path cache GPKG keluaran Proses A untuk satu run."""
    return _folder_cache(setelan) / f"{AWALAN_CACHE_HASIL_A}{run.id}.gpkg"


def _rapikan_cache(setelan: Settings, terbaru: Path) -> None:
    """Sisakan ``MAKS_CACHE_HASIL_A`` berkas cache terbaru (LRU berdasarkan mtime).

    Berkas yang sedang diunduh bisa gagal dihapus di Windows; kegagalan itu
    diabaikan dan akan dirapikan pada permintaan berikutnya.
    """
    try:
        berkas = sorted(
            _folder_cache(setelan).glob(f"{AWALAN_CACHE_HASIL_A}*.gpkg"),
            key=lambda satu: satu.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for lama in berkas[MAKS_CACHE_HASIL_A:]:
        if lama == terbaru:
            continue
        try:
            lama.unlink(missing_ok=True)
        except OSError:
            continue


def berkas_hasil_a(run: Run, setelan: Settings) -> Path:
    """Path GPKG keluaran Proses A untuk satu run (buat bila belum ada).

    Hasil di-cache di ``DIR_UNGGAHAN/_ekspor`` dan hanya
    ``MAKS_CACHE_HASIL_A`` berkas terbaru yang disimpan.

    Raises
    ------
    EksporTidakTersedia
        Run bukan Proses A, belum sukses, atau berkas mentahnya sudah dipangkas.
    """
    if run.tipe != TIPE_A:
        raise EksporTidakTersedia(
            "ekspor hasil Proses A hanya untuk run tipe A, bukan tipe " + run.tipe
        )
    if run.status != STATUS_SUKSES:
        raise EksporTidakTersedia(
            f"run {run.id} belum sukses (status '{run.status}'), hasilnya belum bisa diekspor"
        )

    berkas_input = Path(run.berkas_input)
    berkas_peta = Path(run.berkas_peta)
    if not berkas_input.is_file() or not berkas_peta.is_file():
        raise EksporTidakTersedia(
            f"berkas mentah run {run.id} sudah dipangkas; ekspor hanya tersedia untuk "
            "run baseline dan sukses terakhir per kabupaten/kota dan tipe"
        )

    tujuan = _berkas_cache(run, setelan)
    if tujuan.is_file():
        os.utime(tujuan)  # tandai baru dipakai (LRU)
        return tujuan

    titik, peta = baca_masukan(run)
    hasil = proses_a(titik, peta)

    # Tulis ke berkas sementara di folder cache, lalu ganti nama (atomik).
    sementara = tujuan.with_name(f".{tujuan.name}.{uuid.uuid4().hex}.tmp.gpkg")
    try:
        hasil.to_file(sementara, driver="GPKG", layer=LAYER_HASIL_A)
        try:
            os.replace(sementara, tujuan)
        except OSError:
            # Balapan dengan permintaan lain (berkas tujuan sedang diunduh di
            # Windows): pakai berkas yang sudah ada.
            if not tujuan.is_file():
                raise
    finally:
        sementara.unlink(missing_ok=True)
    _rapikan_cache(setelan, tujuan)
    return tujuan


# ------------------------------------------------------------- titik perlu tindakan


def _baris_titik(sesi: Session, run_id: int) -> Iterator[dict[str, Any]]:
    """Alirkan titik perlu perhatian satu run, urut seperti keluaran proses."""
    tugas = aliased(Wilayah, name="wilayah_tugas")
    asal = aliased(Wilayah, name="wilayah_asal")
    edit = aliased(Wilayah, name="wilayah_edit")

    kolom: list[Any] = [
        TitikHasil.urut,
        TitikHasil.assignment_id,
        TitikHasil.level_6_full_code,
        tugas.idsubsls.label("idsubsls_tugas"),
        asal.idsubsls.label("idsubsls_asal"),
        edit.idsubsls.label("idsubsls_edit"),
        tugas.kdprov,
        tugas.nmprov,
        tugas.kdkab,
        tugas.nmkab,
        tugas.kdkec,
        tugas.nmkec,
        tugas.kddesa,
        tugas.nmdesa,
        tugas.nmsls,
        TitikHasil.flag_psls,
        TitikHasil.flag_repair,
        TitikHasil.flag_repair_initial,
        TitikHasil.flag_edit_atr_repair,
        TitikHasil.flag_position,
        TitikHasil.kk,
        TitikHasil.btt,
        TitikHasil.bku,
        TitikHasil.bttk,
        TitikHasil.bbtt,
        TitikHasil.usaha,
        TitikHasil.latitude_origin,
        TitikHasil.longitude_origin,
        TitikHasil.latitude_edited,
        TitikHasil.longitude_edited,
    ]
    pernyataan = (
        select(*kolom)
        .join(tugas, tugas.idsubsls == TitikHasil.level_6_full_code, isouter=True)
        .join(asal, asal.id == TitikHasil.wilayah_asal_id, isouter=True)
        .join(edit, edit.id == TitikHasil.wilayah_edit_id, isouter=True)
        .where(TitikHasil.run_id == run_id)
        .order_by(TitikHasil.urut)
    )
    for satu in sesi.execute(pernyataan).yield_per(UKURAN_POTONGAN).mappings():
        yield {nama: satu[nama] for nama in KOLOM_TITIK}


def _pastikan_detail(run: Run) -> None:
    """Tolak ekspor titik kalau ``titik_hasil`` run sudah dipangkas."""
    if not run.detail_tersedia:
        raise EksporTidakTersedia(
            f"detail titik run {run.id} sudah dipangkas; ekspor titik hanya tersedia untuk "
            "run baseline dan sukses terakhir per kabupaten/kota dan tipe"
        )


def spool_titik_csv(sesi: Session, run: Run, setelan: Settings) -> BinaryIO:
    """CSV titik perlu perhatian satu run (spool siap dialirkan)."""
    _pastikan_detail(run)
    baris = (
        [satu[nama] for nama in KOLOM_TITIK] for satu in _baris_titik(sesi, run.id)
    )
    return spool_csv(KOLOM_TITIK, baris, _folder_sementara(setelan))


def _gdf_titik(potongan: list[dict[str, Any]]) -> gpd.GeoDataFrame:
    """Susun potongan baris titik jadi GeoDataFrame dengan tipe kolom tetap."""
    data = pd.DataFrame(potongan, columns=list(KOLOM_TITIK))
    for nama in KOLOM_ANGKA:
        data[nama] = pd.to_numeric(data[nama], errors="coerce").astype("Int32")
    for nama in KOLOM_DESIMAL:
        data[nama] = pd.to_numeric(data[nama], errors="coerce").astype("float64")

    # Geometri: koordinat hasil edit bila ada, kalau tidak koordinat origin.
    lintang = data["latitude_edited"].where(data["latitude_edited"].notna(), data["latitude_origin"])
    bujur = data["longitude_edited"].where(
        data["longitude_edited"].notna(), data["longitude_origin"]
    )
    geometri = [
        Point(x, y) if pd.notna(x) and pd.notna(y) else None
        for x, y in zip(bujur, lintang, strict=True)
    ]
    return gpd.GeoDataFrame(data, geometry=geometri, crs=CRS_EKSPOR)


def berkas_titik_gpkg(sesi: Session, run: Run, setelan: Settings) -> Path:
    """GPKG titik perlu perhatian satu run (berkas sementara, pemanggil menghapus)."""
    _pastikan_detail(run)
    tujuan = berkas_sementara(".gpkg", _folder_sementara(setelan))
    try:
        pertama = True
        for potongan in _potongan(_baris_titik(sesi, run.id), UKURAN_POTONGAN):
            pyogrio.write_dataframe(
                _gdf_titik(potongan),
                tujuan,
                layer=LAYER_TITIK,
                driver="GPKG",
                geometry_type="Point",
                append=not pertama,
            )
            pertama = False
        if pertama:  # tidak ada titik perlu perhatian: tetap buat layer kosong
            pyogrio.write_dataframe(
                _gdf_titik([]),
                tujuan,
                layer=LAYER_TITIK,
                driver="GPKG",
                geometry_type="Point",
                append=False,
            )
    except Exception:
        tujuan.unlink(missing_ok=True)
        raise
    return tujuan


# ------------------------------------------------------------------- rekap CSV


def _nama_kabupaten() -> Any:
    """Subquery nama provinsi/kabupaten dari dimensi ``wilayah`` (satu baris per kode)."""
    return (
        select(
            Wilayah.kdprov,
            Wilayah.kdkab,
            func.max(Wilayah.nmprov).label("nmprov"),
            func.max(Wilayah.nmkab).label("nmkab"),
        )
        .group_by(Wilayah.kdprov, Wilayah.kdkab)
        .subquery("nama_kabupaten")
    )


def _nama_desa() -> Any:
    """Subquery nama wilayah sampai desa dari dimensi ``wilayah``."""
    return (
        select(
            Wilayah.kdprov,
            Wilayah.kdkab,
            Wilayah.kdkec,
            Wilayah.kddesa,
            func.max(Wilayah.nmprov).label("nmprov"),
            func.max(Wilayah.nmkab).label("nmkab"),
            func.max(Wilayah.nmkec).label("nmkec"),
            func.max(Wilayah.nmdesa).label("nmdesa"),
        )
        .group_by(Wilayah.kdprov, Wilayah.kdkab, Wilayah.kdkec, Wilayah.kddesa)
        .subquery("nama_desa")
    )


def _saringan_rekap(
    *,
    tipe: str | None,
    kdprov: str | None,
    kdkab: str | None,
    dasar: str,
    tabel: Any,
    tanggal_awal: date | None,
    tanggal_akhir: date | None,
) -> list[Any]:
    """Syarat WHERE ekspor rekap (dasar, tipe, wilayah, rentang ``tanggal_data``)."""
    if dasar not in (DASAR_TUGAS, DASAR_POSISI):
        raise KesalahanSaringan(f"dasar harus '{DASAR_TUGAS}' atau '{DASAR_POSISI}'")
    if tanggal_awal and tanggal_akhir and tanggal_awal > tanggal_akhir:
        raise KesalahanSaringan("tanggal_awal tidak boleh sesudah tanggal_akhir")

    saring: list[Any] = [tabel.dasar == dasar]
    if tipe is not None:
        saring.append(Run.tipe == tipe)
    if kdprov is not None:
        saring.append(Run.kdprov == kdprov)
    if kdkab is not None:
        saring.append(Run.kdkab == kdkab)
    if tanggal_awal is not None:
        saring.append(Run.tanggal_data >= tanggal_awal)
    if tanggal_akhir is not None:
        saring.append(Run.tanggal_data <= tanggal_akhir)
    return saring


def baris_rekap(
    sesi: Session,
    *,
    tingkat: str,
    tipe: str | None = None,
    kdprov: str | None = None,
    kdkab: str | None = None,
    dasar: str = DASAR_TUGAS,
    tanggal_awal: date | None = None,
    tanggal_akhir: date | None = None,
) -> Iterator[dict[str, Any]]:
    """Baris rekap (satu baris per run per wilayah) untuk diekspor ke CSV."""
    if tingkat == "kabupaten":
        yield from _baris_rekap_kabupaten(
            sesi,
            tipe=tipe,
            kdprov=kdprov,
            kdkab=kdkab,
            dasar=dasar,
            tanggal_awal=tanggal_awal,
            tanggal_akhir=tanggal_akhir,
        )
        return
    if tingkat == "desa":
        yield from _baris_rekap_desa(
            sesi,
            tipe=tipe,
            kdprov=kdprov,
            kdkab=kdkab,
            dasar=dasar,
            tanggal_awal=tanggal_awal,
            tanggal_akhir=tanggal_akhir,
        )
        return
    raise KesalahanSaringan(
        f"tingkat ekspor rekap harus salah satu dari {', '.join(TINGKAT_EKSPOR)}"
    )


def _baris_rekap_kabupaten(
    sesi: Session,
    *,
    tipe: str | None,
    kdprov: str | None,
    kdkab: str | None,
    dasar: str,
    tanggal_awal: date | None,
    tanggal_akhir: date | None,
) -> Iterator[dict[str, Any]]:
    """Rekap per kabupaten/kota (dari tabel ``rekap_kabupaten``)."""
    nama = _nama_kabupaten()
    saring = _saringan_rekap(
        tipe=tipe,
        kdprov=kdprov,
        kdkab=kdkab,
        dasar=dasar,
        tabel=RekapKabupaten,
        tanggal_awal=tanggal_awal,
        tanggal_akhir=tanggal_akhir,
    )

    pernyataan = (
        select(
            Run.id.label("run_id"),
            Run.tipe,
            Run.tanggal_data,
            RekapKabupaten.dasar,
            RekapKabupaten.kdprov,
            nama.c.nmprov,
            RekapKabupaten.kdkab,
            nama.c.nmkab,
            *[getattr(RekapKabupaten, kolom) for kolom in KOLOM_HITUNGAN],
        )
        .join(Run, Run.id == RekapKabupaten.run_id)
        .join(
            nama,
            and_(nama.c.kdprov == RekapKabupaten.kdprov, nama.c.kdkab == RekapKabupaten.kdkab),
            isouter=True,
        )
        .where(*saring)
        .order_by(Run.tanggal_data, Run.id, RekapKabupaten.kdprov, RekapKabupaten.kdkab)
    )
    for satu in sesi.execute(pernyataan).mappings():
        baris = dict(satu)
        baris["persen_progres"] = _persen(int(baris["belum"]), _ditindak(baris))
        yield baris


def _baris_rekap_desa(
    sesi: Session,
    *,
    tipe: str | None,
    kdprov: str | None,
    kdkab: str | None,
    dasar: str,
    tanggal_awal: date | None,
    tanggal_akhir: date | None,
) -> Iterator[dict[str, Any]]:
    """Rekap per desa (dari tabel ``rekap_desa``), termasuk "(tanpa wilayah)"."""
    nama = _nama_desa()
    saring = _saringan_rekap(
        tipe=tipe,
        kdprov=kdprov,
        kdkab=kdkab,
        dasar=dasar,
        tabel=RekapDesa,
        tanggal_awal=tanggal_awal,
        tanggal_akhir=tanggal_akhir,
    )

    pernyataan = (
        select(
            Run.id.label("run_id"),
            Run.tipe,
            Run.tanggal_data,
            RekapDesa.dasar,
            RekapDesa.kdprov,
            nama.c.nmprov,
            RekapDesa.kdkab,
            nama.c.nmkab,
            RekapDesa.kdkec,
            nama.c.nmkec,
            RekapDesa.kddesa,
            nama.c.nmdesa,
            *[getattr(RekapDesa, kolom) for kolom in KOLOM_HITUNGAN],
        )
        .join(Run, Run.id == RekapDesa.run_id)
        .join(
            nama,
            and_(
                nama.c.kdprov.is_not_distinct_from(RekapDesa.kdprov),
                nama.c.kdkab.is_not_distinct_from(RekapDesa.kdkab),
                nama.c.kdkec.is_not_distinct_from(RekapDesa.kdkec),
                nama.c.kddesa.is_not_distinct_from(RekapDesa.kddesa),
            ),
            isouter=True,
        )
        .where(*saring)
        .order_by(
            Run.tanggal_data,
            Run.id,
            RekapDesa.kdprov,
            RekapDesa.kdkab,
            RekapDesa.kdkec,
            RekapDesa.kddesa,
        )
    )
    for satu in sesi.execute(pernyataan).mappings():
        baris = dict(satu)
        if baris["kddesa"] is None:
            baris["nmdesa"] = "(tanpa wilayah)"
        baris["persen_progres"] = _persen(int(baris["belum"]), _ditindak(baris))
        yield baris


def spool_rekap_csv(sesi: Session, setelan: Settings, **saringan: Any) -> BinaryIO:
    """CSV rekap (spool siap dialirkan) sesuai saringan yang diberikan."""
    tingkat = saringan.get("tingkat")
    if tingkat not in TINGKAT_EKSPOR:
        raise KesalahanSaringan(
            f"tingkat ekspor rekap harus salah satu dari {', '.join(TINGKAT_EKSPOR)}"
        )
    judul = KOLOM_REKAP_KABUPATEN if tingkat == "kabupaten" else KOLOM_REKAP_DESA
    baris = (
        [satu[nama] for nama in judul]
        for satu in baris_rekap(sesi, **saringan)
    )
    return spool_csv(judul, baris, _folder_sementara(setelan))
