"""Layanan unggah berkas dan query laporan (dipakai API dan tes).

Semua fungsi di sini sinkron (``def``), tanpa akses jaringan: FastAPI
menjalankannya di threadpool, jadi event loop tidak terblokir.

Rekap progres dibaca dari tabel snapshot ``rekap_desa``/``rekap_kabupaten`` (PRD §7):
ringkasan, tren, dan rekap kecamatan/desa hanya menjumlahkan tabel itu. Drill-down
SLS/SubSLS dihitung saat diminta dari ``titik_hasil`` -- jadi hanya bisa untuk run
yang detail titiknya masih disimpan (baseline dan sukses terakhir per kabupaten/tipe).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO, Literal

import pyogrio
from sqlalchemy import and_, func, null, or_, select, union_all
from sqlalchemy.orm import Session, aliased

from app import rekap as modul_rekap
from app.models import (
    DASAR_TUGAS,
    KOLOM_HITUNGAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    GeotagMaster,
    RekapDesa,
    RekapKabupaten,
    Run,
    TitikHasil,
    Wilayah,
    hari_ini,
)
from app.proses_a import KOLOM_PETA, KOLOM_TITIK
from app.proses_b import KOLOM_TITIK_B
from app.wilayah import KOLOM_DIMENSI as KOLOM_WILAYAH

# Kolom wajib tiap berkas masukan, per tipe proses.
KOLOM_WAJIB: dict[str, dict[str, Sequence[str]]] = {
    TIPE_A: {"titik": KOLOM_TITIK, "peta": KOLOM_PETA},
    TIPE_B: {"titik": KOLOM_TITIK_B, "peta": KOLOM_PETA},
}

# Tingkat rekap progres (PRD §5): kolom kode + kolom nama pada tabel ``wilayah``.
# ``sls`` = tingkat SLS (idsls), ``subsls`` = tingkat SubSLS (idsubsls, level_6).
TINGKAT: dict[str, tuple[str, str]] = {
    "kabupaten": ("kdkab", "nmkab"),
    "kecamatan": ("kdkec", "nmkec"),
    "desa": ("kddesa", "nmdesa"),
    "sls": ("idsls", "nmsls"),
    "subsls": ("idsubsls", "nmsls"),
}

#: Tingkat yang dibaca dari tabel rekap (snapshot per desa/kabupaten).
TINGKAT_REKAP: tuple[str, ...] = ("kabupaten", "kecamatan", "desa")
#: Tingkat yang dihitung saat diminta dari ``titik_hasil`` (butuh detail titik).
TINGKAT_DETAIL: tuple[str, ...] = ("sls", "subsls")

Tingkat = Literal["kabupaten", "kecamatan", "desa", "sls", "subsls"]
Dasar = Literal["tugas", "posisi"]

# Nama kolom ``titik_hasil`` yang dibalas API.
KOLOM_TITIK_HASIL: tuple[str, ...] = tuple(
    kolom.name for kolom in TitikHasil.__table__.columns
)

#: Label untuk baris rekap yang tidak menunjuk wilayah.
NAMA_TANPA_WILAYAH = "(tanpa wilayah)"

UKURAN_POTONGAN = 1024 * 1024  # 1 MB per potong saat menyimpan unggahan


class KesalahanUnggahan(ValueError):
    """Berkas unggahan tidak bisa dipakai; pesannya untuk pengguna."""


class DetailTidakTersedia(ValueError):
    """Drill-down SLS/SubSLS diminta, tetapi ``titik_hasil`` run itu sudah dipangkas."""


class KesalahanPerubahan(ValueError):
    """Perubahan antar dua run tidak bisa dihitung (mis. ada run yang belum sukses)."""


def kode_kabupaten(kdprov: str, kdkab: str) -> str:
    """Kode kabupaten/kota 4 digit (``3307``), dari kode peta yang mungkin ``07``."""
    prov = str(kdprov).strip()
    kab = str(kdkab).strip()
    if not prov or not kab:
        raise KesalahanUnggahan("kdprov dan kdkab tidak boleh kosong")
    if len(kab) == 2:
        return f"{prov[:2]}{kab}"
    return kab


def kandidat_kdkab(kdprov: str | None, kdkab: str) -> list[str]:
    """Bentuk kode kabupaten/kota yang mungkin tersimpan di ``runs``.

    Peta wilkerstat memakai kode pendek (``07``), sedangkan master/SSO memakai
    kode 4 digit (``3307``). Penyaring harus mencocokkan keduanya.
    """
    prov = str(kdprov).strip() if kdprov is not None else ""
    kode = str(kdkab).strip()
    if prov and len(kode) == 2:
        kode = f"{prov[:2]}{kode}"
    if len(kode) == 4:
        return sorted({kode, kode[2:]})
    return [kode]


def normalisasi_kode_kabupaten(kdprov: str, kdkab: str) -> str:
    """Validasi kode kabupaten/kota untuk master geotag (harus 4 digit)."""
    prov = str(kdprov).strip()
    kode = kode_kabupaten(prov, kdkab)
    if len(prov) != 2 or not prov.isdigit():
        raise KesalahanUnggahan("kdprov harus 2 digit, mis. 33")
    if len(kode) != 4 or not kode.isdigit() or not kode.startswith(prov):
        raise KesalahanUnggahan(
            f"kdkab harus 4 digit dan berawalan kdprov ({prov}), mis. {prov}07"
        )
    return kode


@dataclass(frozen=True)
class InfoUnggahan:
    """Hasil pemeriksaan berkas unggahan sebelum baris ``runs`` dibuat."""

    kdprov: str
    kdkab: str
    layer_input: str | None
    layer_peta: str | None

    @property
    def kode_kabupaten(self) -> str:
        """Kode 4 digit untuk pencarian master geotag."""
        return kode_kabupaten(self.kdprov, self.kdkab)


@dataclass(frozen=True)
class InfoMaster:
    """Hasil pemeriksaan geotag master."""

    layer: str | None
    jumlah_baris: int


@dataclass(frozen=True)
class InfoTitikB:
    """Hasil pemeriksaan berkas titik Proses B (tanpa peta)."""

    kdprov: str
    #: Kode 4 digit (provinsi + kabupaten/kota), mis. ``3307``.
    kdkab: str
    layer: str | None

    @property
    def kode_kabupaten(self) -> str:
        """Kode 4 digit untuk pencarian run A terakhir."""
        return self.kdkab


def simpan_berkas(sumber: BinaryIO, tujuan: Path) -> int:
    """Tulis berkas unggahan ke disk per potong (hemat memori); kembalikan ukurannya."""
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    ukuran = 0
    with tujuan.open("wb") as keluar:
        while potongan := sumber.read(UKURAN_POTONGAN):
            keluar.write(potongan)
            ukuran += len(potongan)
    return ukuran


def pilih_layer(
    berkas: Path, kolom_wajib: Sequence[str], layer: str | None, peran: str
) -> str | None:
    """Cari layer yang punya semua ``kolom_wajib`` (hanya baca metadata berkas).

    Kalau ``layer`` diisi, layer itulah yang dipakai (dan diperiksa kolomnya).
    """
    try:
        daftar = [str(nama) for nama in pyogrio.list_layers(berkas)[:, 0]]
    except Exception as galat:  # noqa: BLE001 - pesan apa pun diteruskan ke pengguna
        raise KesalahanUnggahan(f"berkas {peran} tidak bisa dibaca: {galat}") from galat

    if not daftar:
        raise KesalahanUnggahan(f"berkas {peran} tidak punya layer apa pun")
    if layer is not None and layer not in daftar:
        raise KesalahanUnggahan(
            f"layer '{layer}' tidak ada di berkas {peran}; pilihan: {', '.join(daftar)}"
        )

    for nama in [layer] if layer is not None else daftar:
        kolom = {str(k) for k in pyogrio.read_info(berkas, layer=nama)["fields"]}
        if set(kolom_wajib) <= kolom:
            return nama

    kurang = ", ".join(sorted(set(kolom_wajib) - kolom))
    raise KesalahanUnggahan(
        f"layer berkas {peran} tidak punya kolom wajib ({kurang}); "
        f"layer tersedia: {', '.join(daftar)}"
    )


def _kode_tunggal(data: Any, kolom: str, peran: str, satuan: str) -> str:
    """Ambil satu nilai kode dari kolom peta (satu job = satu wilayah)."""
    kode = sorted({str(nilai).strip() for nilai in data[kolom].dropna() if str(nilai).strip()})
    if not kode:
        raise KesalahanUnggahan(f"kolom {kolom} di berkas peta kosong")
    if len(kode) > 1:
        contoh = ", ".join(kode[:5])
        raise KesalahanUnggahan(
            f"berkas peta memuat {len(kode)} {satuan} ({contoh}, ...); "
            f"satu job hanya untuk satu {peran}"
        )
    return kode[0]


def periksa_peta(berkas: Path, layer: str | None) -> tuple[str | None, str, str]:
    """Periksa peta dan ambil kdprov + kdkab-nya; peta harus satu kabupaten/kota.

    Satu job hanya untuk satu kabupaten/kota (PRD §8, aturan "satu job aktif per
    kabupaten/tipe"), jadi nilai ``kdprov``/``kdkab`` di peta harus tunggal.
    """
    nama_layer = pilih_layer(berkas, KOLOM_PETA, layer, "peta")
    data = pyogrio.read_dataframe(
        berkas, layer=nama_layer, columns=["kdprov", "kdkab"], read_geometry=False
    )
    kdprov = _kode_tunggal(data, "kdprov", "kabupaten/kota", "provinsi")
    kdkab = _kode_tunggal(data, "kdkab", "kabupaten/kota", "kabupaten/kota")
    return nama_layer, kdprov, kdkab


def periksa_unggahan(
    tipe: str,
    berkas_input: Path,
    berkas_peta: Path,
    layer_input: str | None,
    layer_peta: str | None,
) -> InfoUnggahan:
    """Periksa kedua berkas unggahan; kembalikan kdprov/kdkab + layer yang dipakai."""
    if tipe not in KOLOM_WAJIB:
        raise KesalahanUnggahan(f"tipe harus {TIPE_A} atau {TIPE_B}, bukan '{tipe}'")

    kolom = KOLOM_WAJIB[tipe]
    nama_input = pilih_layer(berkas_input, kolom["titik"], layer_input, "titik")
    nama_peta, kdprov, kdkab = periksa_peta(berkas_peta, layer_peta)
    return InfoUnggahan(
        kdprov=kdprov, kdkab=kdkab, layer_input=nama_input, layer_peta=nama_peta
    )


def _kode_level_6(berkas: Path, layer: str | None) -> tuple[str, ...]:
    """Baca ``level_6_full_code`` unik yang terisi dari berkas titik."""
    data = pyogrio.read_dataframe(
        berkas, layer=layer, columns=["level_6_full_code"], read_geometry=False
    )
    seri = data["level_6_full_code"].dropna().astype("string").str.strip()
    seri = seri.str.replace(r"\.0$", "", regex=True)
    return tuple(nilai for nilai in seri.unique() if nilai)


def periksa_master_geotag(
    berkas: Path, layer: str | None, kode_kab: str
) -> InfoMaster:
    """Periksa geotag master: layer cocok dan semua titik milik kabupaten itu.

    ``level_6_full_code`` yang kosong diabaikan; kalau tidak ada satu pun kode,
    berkas ditolak karena kabupatennya tidak bisa diverifikasi. Semua kode yang
    terisi harus berawalan kode kabupaten/kota 4 digit (``kode_kab``).
    """
    try:
        nama_layer = pilih_layer(
            berkas, KOLOM_WAJIB[TIPE_A]["titik"], layer, "geotag"
        )
    except KesalahanUnggahan as galat:
        raise KesalahanUnggahan(
            f"{galat}. File master harus asli dari GS, bukan hasil Proses 1/2."
        ) from galat
    kode = _kode_level_6(berkas, nama_layer)
    if not kode:
        raise KesalahanUnggahan(
            "geotag tidak punya level_6_full_code; kabupaten/kota tidak bisa diverifikasi"
        )

    salah = [nilai for nilai in kode if not nilai.startswith(kode_kab)]
    if salah:
        contoh = ", ".join(salah[:5])
        raise KesalahanUnggahan(
            f"geotag berisi titik di luar kabupaten/kota {kode_kab} "
            f"(contoh level_6_full_code: {contoh})"
        )

    info = pyogrio.read_info(berkas, layer=nama_layer)
    return InfoMaster(layer=nama_layer, jumlah_baris=int(info["features"]))


def periksa_titik_b(berkas: Path, layer: str | None) -> InfoTitikB:
    """Periksa berkas titik Proses B dan tentukan kabupaten/kotanya.

    Berkas B adalah keluaran Proses A yang sudah diedit, jadi tidak membawa peta.
    Kabupaten/kota diturunkan dari 4 digit pertama ``level_6_full_code``.
    """
    nama_layer = pilih_layer(berkas, KOLOM_WAJIB[TIPE_B]["titik"], layer, "titik")
    kode = _kode_level_6(berkas, nama_layer)
    if not kode:
        raise KesalahanUnggahan(
            "titik Proses B tidak punya level_6_full_code; kabupaten/kota tidak bisa ditentukan"
        )

    awalan = {nilai[:4] for nilai in kode if len(nilai) >= 4 and nilai[:4].isdigit()}
    if not awalan:
        raise KesalahanUnggahan(
            "level_6_full_code titik Proses B tidak berisi kode kabupaten/kota 4 digit"
        )
    if len(awalan) > 1:
        contoh = ", ".join(sorted(awalan)[:5])
        raise KesalahanUnggahan(
            f"titik Proses B memuat lebih dari satu kabupaten/kota ({contoh}); "
            "satu job hanya untuk satu kabupaten/kota"
        )

    kode_kab = awalan.pop()
    return InfoTitikB(
        kdprov=kode_kab[:2], kdkab=kode_kab, layer=nama_layer
    )


def buat_run(
    sesi: Session,
    *,
    tipe: str,
    info: InfoUnggahan,
    user: str | None,
    nama_input: str,
    nama_peta: str,
    berkas_input: Path,
    berkas_peta: Path,
    tanggal_data: date | None = None,
    geotag_master_id: int | None = None,
    sumber_run_a_id: int | None = None,
) -> Run:
    """Buat baris ``runs`` berstatus ``menunggu`` (siap diambil worker)."""
    run = Run(
        tipe=tipe,
        kdprov=info.kdprov,
        kdkab=info.kdkab,
        user=user,
        status=STATUS_MENUNGGU,
        nama_file_input=nama_input,
        nama_file_peta=nama_peta,
        berkas_input=str(berkas_input),
        berkas_peta=str(berkas_peta),
        layer_input=info.layer_input,
        layer_peta=info.layer_peta,
        tanggal_data=hari_ini() if tanggal_data is None else tanggal_data,
        geotag_master_id=geotag_master_id,
        sumber_run_a_id=sumber_run_a_id,
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)
    return run


def buat_master(
    sesi: Session,
    *,
    kdprov: str,
    kdkab: str,
    tanggal_data: date | None,
    nama_file: str,
    berkas: Path,
    layer: str | None,
    jumlah_baris: int | None,
    user: str | None,
) -> GeotagMaster:
    """Simpan satu versi geotag master (versi lama tidak dihapus)."""
    master = GeotagMaster(
        kdprov=kdprov,
        kdkab=kdkab,
        tanggal_data=hari_ini() if tanggal_data is None else tanggal_data,
        nama_file=nama_file,
        berkas=str(berkas),
        layer=layer,
        jumlah_baris=jumlah_baris,
        user=user,
    )
    sesi.add(master)
    sesi.commit()
    sesi.refresh(master)
    return master


def master_terbaru(sesi: Session, kode_kab: str) -> GeotagMaster | None:
    """Versi geotag master terbaru untuk kabupaten/kota 4 digit."""
    kode = str(kode_kab).strip()
    return sesi.scalars(
        select(GeotagMaster)
        .where(GeotagMaster.kdkab == kode)
        .order_by(GeotagMaster.id.desc())
        .limit(1)
    ).first()


def daftar_master(
    sesi: Session,
    *,
    kdprov: str | None = None,
    kdkab: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[GeotagMaster]]:
    """Daftar versi geotag master, terbaru lebih dulu."""
    saring = []
    if kdprov is not None:
        saring.append(GeotagMaster.kdprov == kdprov)
    if kdkab is not None:
        kode = kdkab
        if kdprov is not None and len(str(kdkab)) == 2:
            kode = kode_kabupaten(kdprov, kdkab)
        saring.append(GeotagMaster.kdkab == kode)

    total = int(
        sesi.scalar(
            select(func.count()).select_from(GeotagMaster).where(*saring)
        )
        or 0
    )
    baris = list(
        sesi.scalars(
            select(GeotagMaster)
            .where(*saring)
            .order_by(GeotagMaster.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return total, baris


def run_a_terakhir(
    sesi: Session, kdprov: str, kode_kab: str
) -> Run | None:
    """Run Proses A sukses terakhir untuk kabupaten/kota (peta untuk B)."""
    kode = str(kode_kab).strip()
    kandidat = {kode}
    if len(kode) == 4:
        kandidat.add(kode[2:])
    return sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_A,
            Run.status == STATUS_SUKSES,
            Run.kdprov == kdprov,
            Run.kdkab.in_(sorted(kandidat)),
        )
        .order_by(Run.id.desc())
        .limit(1)
    ).first()


def ambil_run(sesi: Session, run_id: int) -> Run | None:
    """Ambil satu job berdasarkan id."""
    return sesi.get(Run, run_id)


def jumlah_tersimpan(sesi: Session, run_id: int) -> int:
    """Jumlah baris hasil yang tersimpan untuk satu job."""
    return int(
        sesi.scalar(
            select(func.count()).select_from(TitikHasil).where(TitikHasil.run_id == run_id)
        )
        or 0
    )


def daftar_run(
    sesi: Session,
    *,
    tipe: str | None = None,
    status: str | None = None,
    kdprov: str | None = None,
    kdkab: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Run]]:
    """Daftar job terbaru lebih dulu, dengan penyaring opsional (paging)."""
    saring = []
    if tipe is not None:
        saring.append(Run.tipe == tipe)
    if status is not None:
        saring.append(Run.status == status)
    if kdprov is not None:
        saring.append(Run.kdprov == kdprov)
    if kdkab is not None:
        saring.append(Run.kdkab.in_(kandidat_kdkab(kdprov, kdkab)))

    total = int(sesi.scalar(select(func.count()).select_from(Run).where(*saring)) or 0)
    baris = list(
        sesi.scalars(
            select(Run).where(*saring).order_by(Run.id.desc()).limit(limit).offset(offset)
        )
    )
    return total, baris


def nomor_urut_run(sesi: Session, baris: Sequence[Run]) -> dict[int, int]:
    """Nomor urut job per (``kdprov``, ``kdkab``, ``tipe``), bukan id global."""
    if not baris:
        return {}

    luar = aliased(Run)
    nomor = (
        select(func.count())
        .select_from(Run)
        .where(
            Run.kdprov == luar.kdprov,
            Run.kdkab == luar.kdkab,
            Run.tipe == luar.tipe,
            Run.id <= luar.id,
        )
        .correlate(luar)
        .scalar_subquery()
    )
    ids = [satu.id for satu in baris]
    hasil = sesi.execute(
        select(luar.id, nomor.label("nomor")).where(luar.id.in_(ids))
    ).all()
    return {int(satu_id): int(satu_nomor) for satu_id, satu_nomor in hasil}


def nomor_versi_master(
    sesi: Session, baris: Sequence[GeotagMaster]
) -> dict[int, int]:
    """Nomor versi master per kabupaten/kota, bukan id global."""
    if not baris:
        return {}

    luar = aliased(GeotagMaster)
    nomor = (
        select(func.count())
        .select_from(GeotagMaster)
        .where(
            GeotagMaster.kdkab == luar.kdkab,
            GeotagMaster.id <= luar.id,
        )
        .correlate(luar)
        .scalar_subquery()
    )
    ids = [satu.id for satu in baris]
    hasil = sesi.execute(
        select(luar.id, nomor.label("nomor")).where(luar.id.in_(ids))
    ).all()
    return {int(satu_id): int(satu_nomor) for satu_id, satu_nomor in hasil}


def lengkapi_nomor_versi(
    sesi: Session, baris: Sequence[GeotagMaster]
) -> None:
    nomor = nomor_versi_master(sesi, baris)
    for satu in baris:
        satu.nomor_versi = nomor.get(satu.id)


def lengkapi_nomor_urut(sesi: Session, baris: Sequence[Run]) -> None:
    """Isi nomor urut job, sumber run A, dan versi master untuk tampilan."""
    nomor = nomor_urut_run(sesi, baris)
    for satu in baris:
        satu.nomor_urut = nomor.get(satu.id)

    sumber_ids = {
        satu.sumber_run_a_id for satu in baris if satu.sumber_run_a_id is not None
    }
    if sumber_ids:
        sumber = list(sesi.scalars(select(Run).where(Run.id.in_(sumber_ids))))
        nomor_sumber = nomor_urut_run(sesi, sumber)
        for satu in sumber:
            satu.nomor_urut = nomor_sumber.get(satu.id)
        peta = {satu.id: satu.nomor_urut for satu in sumber}
    else:
        peta = {}
    for satu in baris:
        satu.sumber_run_a_nomor = (
            peta.get(satu.sumber_run_a_id) if satu.sumber_run_a_id else None
        )

    master_ids = {
        satu.geotag_master_id
        for satu in baris
        if satu.geotag_master_id is not None
    }
    if master_ids:
        master = list(
            sesi.scalars(select(GeotagMaster).where(GeotagMaster.id.in_(master_ids)))
        )
        nomor_master = nomor_versi_master(sesi, master)
        for satu in master:
            satu.nomor_versi = nomor_master.get(satu.id)
        peta_master = {satu.id: satu.nomor_versi for satu in master}
    else:
        peta_master = {}
    for satu in baris:
        satu.geotag_master_nomor = (
            peta_master.get(satu.geotag_master_id)
            if satu.geotag_master_id
            else None
        )


def _wilayah_dict(baris: Mapping[str, Any], awalan: str) -> dict[str, Any] | None:
    """Susun dict wilayah dari kolom berawalan (``tugas_``/``asal_``/``edit_``)."""
    if baris.get(f"{awalan}_idsubsls") is None:
        return None
    return {kolom: baris.get(f"{awalan}_{kolom}") for kolom in KOLOM_WILAYAH}


def hasil_run(
    sesi: Session, run_id: int, *, limit: int = 100, offset: int = 0
) -> tuple[int, list[dict[str, object]]]:
    """Sebagian baris hasil (paging), urut seperti keluaran Proses A/B.

    Yang tersimpan hanya titik yang perlu perhatian (``flag_repair`` = 1,
    ``flag_edit_atr_repair`` = 1, atau tidak masuk poligon mana pun). Nama/kode
    wilayah diambil dari tabel ``wilayah`` lewat join: ``wilayah_tugas`` (dari
    ``level_6_full_code``), ``wilayah_asal`` (hasil join peta), dan ``wilayah_edit``
    (hasil join peta untuk Proses B).
    """
    tugas = aliased(Wilayah, name="wilayah_tugas")
    asal = aliased(Wilayah, name="wilayah_asal")
    edit = aliased(Wilayah, name="wilayah_edit")

    kolom: list[Any] = [TitikHasil.__table__.columns[nama] for nama in KOLOM_TITIK_HASIL]
    kolom += [
        getattr(peta, nama).label(f"{awalan}_{nama}")
        for awalan, peta in (("tugas", tugas), ("asal", asal), ("edit", edit))
        for nama in KOLOM_WILAYAH
    ]

    total = int(
        sesi.scalar(
            select(func.count()).select_from(TitikHasil).where(TitikHasil.run_id == run_id)
        )
        or 0
    )
    baris = sesi.execute(
        select(*kolom)
        .join(tugas, tugas.idsubsls == TitikHasil.level_6_full_code, isouter=True)
        .join(asal, asal.id == TitikHasil.wilayah_asal_id, isouter=True)
        .join(edit, edit.id == TitikHasil.wilayah_edit_id, isouter=True)
        .where(TitikHasil.run_id == run_id)
        .order_by(TitikHasil.urut)
        .limit(limit)
        .offset(offset)
    ).mappings()

    keluaran: list[dict[str, object]] = [
        {
            **{nama: satu[nama] for nama in KOLOM_TITIK_HASIL},
            "wilayah_tugas": _wilayah_dict(satu, "tugas"),
            "wilayah_asal": _wilayah_dict(satu, "asal"),
            "wilayah_edit": _wilayah_dict(satu, "edit"),
        }
        for satu in baris
    ]
    return total, keluaran


# --------------------------------------------------------------------------- rekap


def _sumbu(tabel: object) -> dict[str, object]:
    """``SUM(kolom)`` tiap kolom hitungan ``tabel`` (0 kalau tidak ada baris)."""
    return {
        nama: func.coalesce(func.sum(getattr(tabel, nama)), 0).label(nama)
        for nama in KOLOM_HITUNGAN
    }


def _persen(belum: int, ditindak: int) -> float | None:
    """Persentase progres; ``None`` (ditampilkan kosong) kalau penyebutnya 0."""
    penyebut = belum + ditindak
    return round(100.0 * ditindak / penyebut, 2) if penyebut else None


def _ditindak(nilai: Mapping[str, Any]) -> int:
    """Jumlah titik yang ditindak (posisi benar + posisi salah)."""
    return int(nilai["ditindak_posisi_benar"]) + int(nilai["ditindak_posisi_salah"])


def _baris_rekap(nilai: Mapping[str, Any], kode: Any, nama: Any) -> dict[str, object]:
    """Susun satu baris rekap (kode NULL = kategori "(tanpa wilayah)")."""
    return {
        "kode": None if kode is None else str(kode),
        "nama": NAMA_TANPA_WILAYAH if kode is None else (None if nama is None else str(nama)),
        **{kolom: int(nilai[kolom]) for kolom in KOLOM_HITUNGAN},
        "persen_progres": _persen(int(nilai["belum"]), _ditindak(nilai)),
    }


def _peta_nama(
    sesi: Session, kolom_nama: str, kunci: Sequence[str], saring: Sequence[object] = ()
) -> dict[tuple[str, ...], str]:
    """Peta kode wilayah -> nama dari tabel ``wilayah`` (nama terbesar yang ada)."""
    kolom = [getattr(Wilayah, nama) for nama in kunci]
    baris = sesi.execute(
        select(*kolom, func.max(getattr(Wilayah, kolom_nama)))
        .where(*saring)
        .group_by(*kolom)
    ).all()

    keluaran: dict[tuple[str, ...], str] = {}
    for satu in baris:
        kode = tuple(str(nilai) for nilai in satu[: len(kunci)])
        nama = satu[-1]
        if nama is not None and all(nilai is not None for nilai in satu[: len(kunci)]):
            keluaran.setdefault(kode, str(nama))
    return keluaran


def _saring_wilayah(run: Run) -> list[object]:
    """Penyaring nama wilayah untuk run ini (satu kabupaten/kota)."""
    return [Wilayah.kdprov == run.kdprov, Wilayah.kdkab == run.kdkab]


def _rekap_dari_tabel(sesi: Session, run: Run, tingkat: str, dasar: str) -> dict[str, object]:
    """Rekap kabupaten/kecamatan/desa dari snapshot ``rekap_desa``/``rekap_kabupaten``.

    Tingkat kecamatan = jumlah per ``kdkec``, tingkat desa = jumlah per
    (``kdkec``, ``kddesa``); nama wilayah diambil dari tabel ``wilayah``.
    """
    kabupaten = tingkat == "kabupaten"
    sumber = RekapKabupaten if kabupaten else RekapDesa
    if kabupaten:
        kunci_kode = ["kdprov", "kdkab"]
        kolom_nama = "nmkab"
    elif tingkat == "kecamatan":
        kunci_kode = ["kdkec"]
        kolom_nama = "nmkec"
    else:
        kunci_kode = ["kdkec", "kddesa"]
        kolom_nama = "nmdesa"

    kode = tuple(getattr(sumber, nama) for nama in kunci_kode)
    nama = _peta_nama(sesi, kolom_nama, kunci_kode, _saring_wilayah(run))
    hasil = sesi.execute(
        select(*kode, *_sumbu(sumber).values())
        .where(sumber.run_id == run.id, sumber.dasar == dasar)
        .group_by(*kode)
    ).mappings()

    baris: list[dict[str, object]] = []
    for satu in hasil:
        kunci = tuple(None if satu[kolom] is None else str(satu[kolom]) for kolom in kunci_kode)
        baris.append(_baris_rekap(satu, kunci[-1], nama.get(kunci)))
    # Urutan kode menanjak, baris "(tanpa wilayah)" paling akhir (urutan NULL
    # berbeda antara MySQL dan SQLite, jadi diurutkan di sini saja).
    baris.sort(key=lambda satu: (satu["kode"] is None, satu["kode"] or ""))
    return _bungkus_rekap(run, tingkat, dasar, baris)


def _rekap_detail(sesi: Session, run: Run, tingkat: str, dasar: str) -> dict[str, object]:
    """Drill-down SLS/SubSLS dihitung saat diminta dari ``titik_hasil``.

    Hanya bisa untuk run yang detail titiknya masih tersimpan
    (``runs.detail_tersedia``): ``titik_hasil`` memuat seluruh titik ``belum`` dan
    ``ditindak``, tetapi titik ``benar_awal`` sudah dipangkas.
    """
    if not run.detail_tersedia:
        raise DetailTidakTersedia(
            f"detail titik run {run.id} sudah dipangkas; drill-down SLS/SubSLS hanya "
            "tersedia untuk run baseline dan run sukses terakhir per kabupaten/tipe"
        )
    if tingkat == "sls":
        kolom_kode, kolom_nama = Wilayah.idsls, Wilayah.nmsls
    else:
        kolom_kode, kolom_nama = Wilayah.idsubsls, Wilayah.nmsls

    belum, ditindak_benar, ditindak_salah = modul_rekap.kolom_ringkas()
    hasil = sesi.execute(
        select(kolom_kode, kolom_nama, belum, ditindak_benar, ditindak_salah)
        .select_from(TitikHasil)
        .join(Wilayah, modul_rekap.klausa_wilayah(dasar), isouter=True)
        .where(TitikHasil.run_id == run.id)
        .group_by(kolom_kode, kolom_nama)
    ).all()

    baris: list[dict[str, object]] = []
    for kode, nama, satu_belum, satu_benar, satu_salah in hasil:
        nilai = {
            "belum": int(satu_belum),
            "ditindak": int(satu_benar) + int(satu_salah),
        }
        baris.append(
            {
                "kode": None if kode is None else str(kode),
                "nama": NAMA_TANPA_WILAYAH if kode is None else (None if nama is None else str(nama)),
                **nilai,
                "persen_progres": _persen(nilai["belum"], nilai["ditindak"]),
            }
        )
    baris.sort(key=lambda satu: (satu["kode"] is None, satu["kode"] or ""))

    ringkas = {
        kolom: sum(int(satu[kolom]) for satu in baris) for kolom in ("belum", "ditindak")
    }
    return {
        "run_id": run.id,
        "tingkat": tingkat,
        "dasar": dasar,
        **ringkas,
        "persen_progres": _persen(ringkas["belum"], ringkas["ditindak"]),
        "baris": baris,
    }


def _bungkus_rekap(
    run: Run, tingkat: str, dasar: str, baris: list[dict[str, object]]
) -> dict[str, object]:
    """Jumlahkan baris rekap jadi balasan rekap satu run."""
    ringkas = {kolom: sum(int(satu[kolom]) for satu in baris) for kolom in KOLOM_HITUNGAN}
    return {
        "run_id": run.id,
        "tingkat": tingkat,
        "dasar": dasar,
        "total": ringkas.pop("jumlah"),
        **ringkas,
        "persen_progres": _persen(ringkas["belum"], _ditindak(ringkas)),
        "baris": baris,
    }


def rekap_run(sesi: Session, run: Run, tingkat: Tingkat, dasar: str = DASAR_TUGAS) -> dict[str, object]:
    """Rekap progres satu run per tingkat wilayah untuk satu dasar.

    Tingkat ``kabupaten``/``kecamatan``/``desa`` dibaca dari snapshot
    ``rekap_kabupaten``/``rekap_desa`` (bukan memindai ``titik_hasil``); tingkat
    ``sls``/``subsls`` dihitung saat diminta dari ``titik_hasil``.

    Persentase progres = (``ditindak_posisi_benar`` + ``ditindak_posisi_salah``) /
    (``belum`` + ``ditindak_posisi_benar`` + ``ditindak_posisi_salah``); jadi
    ``benar_awal`` tidak ikut dihitung. Kalau penyebutnya 0, nilainya ``None``
    (ditampilkan kosong). Baris kategori "(tanpa wilayah)" selalu diletakkan paling
    akhir.
    """
    if tingkat in TINGKAT_DETAIL:
        return _rekap_detail(sesi, run, tingkat, dasar)
    return _rekap_dari_tabel(sesi, run, tingkat, dasar)


# ---------------------------------------------------------------- ringkasan & tren


def _saring_run(
    tipe: str | None, provinsi: str | None, kdkab: str | None
) -> list[object]:
    """Penyaring run untuk ringkasan/tren (selalu dibatasi run sukses)."""
    saring: list[object] = [Run.status == STATUS_SUKSES]
    if tipe is not None:
        saring.append(Run.tipe == tipe)
    if provinsi is not None:
        saring.append(Run.kdprov == provinsi)
    if kdkab is not None:
        saring.append(Run.kdkab.in_(kandidat_kdkab(provinsi, kdkab)))
    return saring


def ringkasan(
    sesi: Session,
    *,
    tipe: str | None = None,
    provinsi: str | None = None,
    kdkab: str | None = None,
    dasar: str = DASAR_TUGAS,
) -> dict[str, object]:
    """Ringkasan provinsi: satu baris per kabupaten/kota.

    Tiap baris memuat run sukses **terakhir tiap tipe** (``terakhir``), dengan
    ``belum``/``ditindak``/``persen_progres`` dan ``tanggal_data``-nya, plus penanda
    ``belum_ada_upload_tipe_b`` (di kabupaten/kota itu belum pernah ada unggahan
    Proses B). Angka dibaca dari ``rekap_kabupaten``.
    """
    terakhir = (
        select(
            Run.kdprov.label("kdprov"),
            Run.kdkab.label("kdkab"),
            Run.tipe.label("tipe"),
            func.max(Run.id).label("run_id"),
        )
        .where(*_saring_run(tipe, provinsi, kdkab))
        .group_by(Run.kdprov, Run.kdkab, Run.tipe)
        .subquery()
    )
    hasil = sesi.execute(
        select(
            terakhir.c.kdprov,
            terakhir.c.kdkab,
            terakhir.c.tipe,
            terakhir.c.run_id,
            Run.tanggal_data,
            RekapKabupaten.belum,
            RekapKabupaten.ditindak_posisi_benar,
            RekapKabupaten.ditindak_posisi_salah,
        )
        .select_from(terakhir)
        .join(Run, Run.id == terakhir.c.run_id)
        .join(
            RekapKabupaten,
            and_(RekapKabupaten.run_id == Run.id, RekapKabupaten.dasar == dasar),
        )
        .order_by(terakhir.c.kdprov, terakhir.c.kdkab, terakhir.c.tipe)
    ).mappings()

    saring_wilayah: list[object] = []
    if provinsi is not None:
        saring_wilayah.append(Wilayah.kdprov == provinsi)
    nmprov = _peta_nama(sesi, "nmprov", ("kdprov",), saring_wilayah)
    nmkab = _peta_nama(sesi, "nmkab", ("kdprov", "kdkab"), saring_wilayah)
    ada_tipe_b = {
        (str(satu[0]), str(satu[1]))
        for satu in sesi.execute(select(Run.kdprov, Run.kdkab).where(Run.tipe == TIPE_B).distinct())
    }

    per_kab: dict[tuple[str, str], dict[str, object]] = {}
    for satu in hasil:
        kunci = (str(satu["kdprov"]), str(satu["kdkab"]))
        kab = per_kab.setdefault(
            kunci,
            {
                "kdprov": kunci[0],
                "kdkab": kunci[1],
                "nmprov": nmprov.get((kunci[0],)),
                "nmkab": nmkab.get(kunci),
                "belum_ada_upload_tipe_b": kunci not in ada_tipe_b,
                "terakhir": [],
            },
        )
        nilai = {
            "belum": int(satu["belum"]),
            "ditindak_posisi_benar": int(satu["ditindak_posisi_benar"]),
            "ditindak_posisi_salah": int(satu["ditindak_posisi_salah"]),
        }
        terakhir_satu = kab["terakhir"]
        assert isinstance(terakhir_satu, list)
        terakhir_satu.append(
            {
                "tipe": str(satu["tipe"]),
                "run_id": int(satu["run_id"]),
                "tanggal_data": satu["tanggal_data"],
                "belum": nilai["belum"],
                "ditindak": _ditindak(nilai),
                "persen_progres": _persen(nilai["belum"], _ditindak(nilai)),
            }
        )
    return {"baris": list(per_kab.values())}


def _metrik_progres(
    sesi: Session, run: Run, dasar: str
) -> tuple[int, int] | None:
    """Ambil (jumlah, belum) dari snapshot rekap atau detail titik run lama.

    Run yang diproses sebelum snapshot rekap tersedia tidak punya baris
    ``rekap_kabupaten``. Untuk run seperti itu, hitung ``belum`` dari
    ``titik_hasil`` selama detailnya masih disimpan. Bila keduanya tidak ada,
    kembalikan ``None`` supaya UI tidak menampilkan target palsu.
    """
    rekap = sesi.scalars(
        select(RekapKabupaten).where(
            RekapKabupaten.run_id == run.id,
            RekapKabupaten.dasar == dasar,
        )
    ).first()
    if rekap is not None:
        return int(rekap.jumlah), int(rekap.belum)

    jumlah_detail = (
        sesi.scalar(
            select(func.count())
            .select_from(TitikHasil)
            .where(TitikHasil.run_id == run.id)
        )
        or 0
    )
    if jumlah_detail == 0:
        if run.detail_tersedia:
            return int(run.jumlah_baris or 0), 0
        return None
    belum = (
        sesi.scalar(
            select(func.count())
            .select_from(TitikHasil)
            .where(TitikHasil.run_id == run.id, TitikHasil.flag_repair == 1)
        )
        or 0
    )
    return int(run.jumlah_baris or jumlah_detail), int(belum)


def _pilih_target_a(
    sesi: Session, kdprov: str, kdkab: str, dasar: str
) -> tuple[Run | None, tuple[int, int] | None]:
    """Run A terbaru yang targetnya bisa dibaca untuk satu kabupaten/kota.

    Master geotag adalah acuan dari provinsi. Setiap Proses A baru memakai master
    terbaru, jadi target mengikuti run A terbaru yang sukses, bukan run pertama.
    """
    # Peta wilkerstat menyimpan kode pendek (07/72), sedangkan UI memakai kode
    # 4 digit (3307/3372). Cocokkan keduanya.
    kode_kab = kandidat_kdkab(kdprov, kdkab)
    kandidat_a = sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_A,
            Run.status == STATUS_SUKSES,
            Run.kdprov == kdprov,
            Run.kdkab.in_(kode_kab),
        )
        .order_by(Run.id.desc())
    ).all()

    # Utamakan run yang punya snapshot rekap supaya tabulasi target juga bisa
    # dibuka. Run lama tanpa snapshot baru memakai detail titik sebagai cadangan.
    for kandidat in kandidat_a:
        rekap = sesi.scalars(
            select(RekapKabupaten).where(
                RekapKabupaten.run_id == kandidat.id,
                RekapKabupaten.dasar == dasar,
            )
        ).first()
        if rekap is not None:
            return kandidat, (int(rekap.jumlah), int(rekap.belum))
    for kandidat in kandidat_a:
        metrik = _metrik_progres(sesi, kandidat, dasar)
        if metrik is not None:
            return kandidat, metrik
    return None, None


def _saring_b_setelah_target(run_a: Run | None) -> list[object]:
    """Syarat B yang sebanding dengan target A terbaru.

    B harus dibuat setelah A target. Kalau sumber A-nya dicatat, sumber itu harus
    sama dengan A target; B lama tanpa ``sumber_run_a_id`` tetap diterima.
    """
    if run_a is None:
        return []
    return [
        Run.id > run_a.id,
        or_(Run.sumber_run_a_id.is_(None), Run.sumber_run_a_id == run_a.id),
    ]


def _b_sebanding(run_b: Run, run_a: Run) -> bool:
    """True kalau B dibuat setelah A target dan memakai sumber A yang sama."""
    if run_b.id <= run_a.id:
        return False
    return run_b.sumber_run_a_id in (None, run_a.id)


def progres_b(
    sesi: Session,
    *,
    kdprov: str,
    kdkab: str,
    dasar: str = DASAR_TUGAS,
) -> dict[str, object]:
    """Perjalanan Proses B satu kabupaten/kota terhadap target Proses A terbaru.

    Target = ``belum`` (flag 1) pada run Proses A sukses terbaru yang metriknya
    masih bisa dibaca. Setiap run B sukses setelah A target menjadi satu titik
    waktu. ``beres`` = target - sisa flag 1; nilai dapat turun bila muncul flag
    baru, dan UI wajib menjelaskannya.
    """
    kode_kab = kandidat_kdkab(kdprov, kdkab)
    run_a, metrik_a = _pilih_target_a(sesi, kdprov, kdkab, dasar)

    target: dict[str, object] | None = None
    target_flag = 0
    if run_a is not None and metrik_a is not None:
        target_total, target_flag = metrik_a
        target = {
            "run_a_id": run_a.id,
            "nomor_urut": None,
            "tanggal_data": run_a.tanggal_data,
            "total": target_total,
            "flag_1": target_flag,
        }

    baris: list[dict[str, object]] = []
    run_b = sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_B,
            Run.status == STATUS_SUKSES,
            Run.kdprov == kdprov,
            Run.kdkab.in_(kode_kab),
            *_saring_b_setelah_target(run_a),
        )
        .order_by(Run.id)
    ).all()
    semua_run = ([run_a] if run_a is not None else []) + list(run_b)
    nomor = nomor_urut_run(sesi, semua_run)
    if target is not None:
        target["nomor_urut"] = nomor.get(run_a.id) if run_a is not None else None

    sebelumnya: int | None = target_flag if target is not None else None
    for run in run_b:
        metrik = _metrik_progres(sesi, run, dasar)
        if metrik is None:
            continue
        total, sisa = metrik
        if target is None:
            beres = 0
            persen = None
            perubahan = 0
        else:
            beres = max(target_flag - sisa, 0)
            persen = round(beres / target_flag * 100, 1) if target_flag else None
            perubahan = (sebelumnya - sisa) if sebelumnya is not None else 0
            sebelumnya = sisa
        baris.append(
            {
                "run_id": run.id,
                "nomor_urut": nomor.get(run.id),
                "tanggal_data": run.tanggal_data,
                "selesai_pada": run.finished_at,
                "total": total,
                "sisa_flag_1": sisa,
                "beres": beres,
                "persen": persen,
                "perubahan": perubahan,
            }
        )

    saring = [Wilayah.kdprov == kdprov, Wilayah.kdkab.in_(kode_kab)]
    nmprov = _peta_nama(sesi, "nmprov", ("kdprov",), saring[:1]).get((kdprov,))
    peta_kab = _peta_nama(sesi, "nmkab", ("kdprov", "kdkab"), saring)
    nmkab = next(
        (
            peta_kab.get((kdprov, kode))
            for kode in (kdkab, *kode_kab)
            if peta_kab.get((kdprov, kode))
        ),
        None,
    )
    return {
        "kdprov": kdprov,
        "kdkab": kdkab,
        "nmprov": nmprov,
        "nmkab": nmkab,
        "target": target,
        "baris": baris,
    }


def _metrik_wilayah(
    sesi: Session,
    run: Run,
    tingkat: str,
    dasar: str,
    kdprov: str,
    kode_kab: Sequence[str],
    kdkec: str | None = None,
) -> dict[tuple[str | None, ...], dict[str, int]]:
    """Metrik target/sisa per wilayah dari snapshot rekap satu run."""
    if tingkat == "kabupaten":
        sumber = RekapKabupaten
        kunci = [RekapKabupaten.kdkab]
        saring = [
            RekapKabupaten.run_id == run.id,
            RekapKabupaten.dasar == dasar,
            RekapKabupaten.kdprov == kdprov,
            RekapKabupaten.kdkab.in_(kode_kab),
        ]
    else:
        sumber = RekapDesa
        if tingkat == "kecamatan":
            kunci = [RekapDesa.kdkec]
            saring = [
                RekapDesa.run_id == run.id,
                RekapDesa.dasar == dasar,
                RekapDesa.kdprov == kdprov,
                RekapDesa.kdkab.in_(kode_kab),
            ]
        else:
            kunci = [RekapDesa.kdkec, RekapDesa.kddesa]
            saring = [
                RekapDesa.run_id == run.id,
                RekapDesa.dasar == dasar,
                RekapDesa.kdprov == kdprov,
                RekapDesa.kdkab.in_(kode_kab),
                RekapDesa.kdkec == kdkec,
            ]

    hasil = sesi.execute(
        select(*kunci, *_sumbu(sumber).values()).where(*saring).group_by(*kunci)
    ).mappings()
    keluaran: dict[tuple[str | None, ...], dict[str, int]] = {}
    for satu in hasil:
        kode = tuple(None if satu[kolom.name] is None else str(satu[kolom.name]) for kolom in kunci)
        keluaran[kode] = {nama: int(satu[nama]) for nama in KOLOM_HITUNGAN}
    return keluaran


def _status_tabulasi(target: int, sisa: int, ada_b: bool) -> str:
    if target <= 0:
        return "tanpa_target"
    if not ada_b:
        return "belum_b"
    if sisa <= 0:
        return "selesai"
    if target - sisa < 0:
        return "mundur"
    return "berjalan"


def _ringkas_metrik(run: Run | None, metrik: tuple[int, int] | None, nomor: int | None) -> dict[str, object] | None:
    if run is None or metrik is None:
        return None
    return {
        "run_id": run.id,
        "nomor_urut": nomor,
        "tanggal_data": run.tanggal_data,
    }


def _baris_kabupaten(
    kode_kab: str,
    nama: str | None,
    total: int,
    target: int,
    sisa_target: int,
    ada_b: bool,
) -> dict[str, object]:
    selesai = target - sisa_target
    return {
        "kode": kode_kab,
        "induk": None,
        "nama": nama,
        "level": "kabupaten",
        "jumlah": total,
        "target": target,
        "selesai": selesai,
        "sisa": sisa_target,
        "persen": round(selesai / target * 100, 2) if target else None,
        "status": _status_tabulasi(target, sisa_target, ada_b),
        "ada_b": ada_b,
    }


def tabulasi_progres(
    sesi: Session,
    *,
    kdprov: str,
    kdkab: str | None = None,
    kdkec: str | None = None,
    tingkat: str = "kabupaten",
    dasar: str = DASAR_TUGAS,
) -> dict[str, object]:
    """Tabulasi target A terbaru vs sisa B terakhir, per tingkat wilayah.

    Satu permintaan hanya mengembalikan satu tingkat: kabupaten/kota, lalu
    kecamatan untuk satu kabupaten/kota, lalu desa untuk satu kecamatan.
    """
    if tingkat not in ("kabupaten", "kecamatan", "desa"):
        raise KesalahanPerubahan("tingkat tabulasi harus kabupaten, kecamatan, atau desa")
    if tingkat != "kabupaten" and not kdkab:
        raise KesalahanPerubahan("kdkab wajib diisi untuk tingkat kecamatan/desa")
    if tingkat == "desa" and not kdkec:
        raise KesalahanPerubahan("kdkec wajib diisi untuk tingkat desa")

    kode_kab = kandidat_kdkab(kdprov, kdkab) if kdkab else []
    saring_nama: list[object] = [Wilayah.kdprov == kdprov]
    if kode_kab:
        saring_nama.append(Wilayah.kdkab.in_(kode_kab))
    nmprov = _peta_nama(sesi, "nmprov", ("kdprov",), [Wilayah.kdprov == kdprov]).get((kdprov,))
    peta_kab = _peta_nama(sesi, "nmkab", ("kdprov", "kdkab"), saring_nama)

    def nama_kab(kode: str) -> str | None:
        for calon in (kode, kode[-2:]):
            hasil = peta_kab.get((kdprov, calon))
            if hasil:
                return hasil
        return None

    if tingkat == "kabupaten":
        target_peta: dict[str, tuple[Run, tuple[int, int]]] = {}
        if kdkab:
            run_a, metrik_a = _pilih_target_a(sesi, kdprov, kdkab, dasar)
            if run_a is not None and metrik_a is not None:
                target_peta[kode_kabupaten(kdprov, kdkab)] = (run_a, metrik_a)
            kode_semua = [kode_kabupaten(kdprov, kdkab)]
        else:
            kode_semua = sorted(
                {
                    kode_kabupaten(kdprov, run.kdkab)
                    for run in sesi.scalars(
                        select(Run).where(
                            Run.tipe == TIPE_A,
                            Run.status == STATUS_SUKSES,
                            Run.kdprov == kdprov,
                        )
                    ).all()
                }
                | {
                    kode_kabupaten(kdprov, kode)
                    for _, kode in peta_kab
                }
            )
            # Pilih target dengan aturan yang sama seperti ``progres_b``: run A
            # pertama yang punya snapshot rekap, baru cadangan detail titik.
            for kode in kode_semua:
                run_a, metrik_a = _pilih_target_a(sesi, kdprov, kode, dasar)
                if run_a is not None and metrik_a is not None:
                    target_peta[kode] = (run_a, metrik_a)

        terbaru_b: dict[str, Run] = {}
        for run in sesi.scalars(
            select(Run)
            .where(
                Run.tipe == TIPE_B,
                Run.status == STATUS_SUKSES,
                Run.kdprov == kdprov,
            )
            .order_by(Run.id)
        ).all():
            kode = kode_kabupaten(kdprov, run.kdkab)
            target_metrik = target_peta.get(kode)
            if target_metrik is not None and not _b_sebanding(run, target_metrik[0]):
                continue
            terbaru_b[kode] = run
        b_peta: dict[str, tuple[Run, tuple[int, int]]] = {}
        for kode, run_b in terbaru_b.items():
            metrik_b = _metrik_progres(sesi, run_b, dasar)
            if metrik_b is not None:
                b_peta[kode] = (run_b, metrik_b)

        baris = []
        for kode in kode_semua:
            target_metrik = target_peta.get(kode)
            total, target = target_metrik[1] if target_metrik is not None else (0, 0)
            run_b_metrik = b_peta.get(kode)
            sisa = run_b_metrik[1][1] if run_b_metrik is not None else target
            baris.append(
                _baris_kabupaten(kode, nama_kab(kode), total, target, sisa, run_b_metrik is not None)
            )

        kode_terpilih = kode_kabupaten(kdprov, kdkab) if kdkab else None
        run_a_meta = target_peta.get(kode_terpilih, (None, None))[0] if kode_terpilih else None
        metrik_a_meta = target_peta.get(kode_terpilih, (None, None))[1] if kode_terpilih else None
        run_b_meta = b_peta.get(kode_terpilih, (None, None))[0] if kode_terpilih else None
        metrik_b_meta = b_peta.get(kode_terpilih, (None, None))[1] if kode_terpilih else None
        semua = [run for run in (run_a_meta, run_b_meta) if run is not None]
        nomor = nomor_urut_run(sesi, semua)
        return {
            "tingkat": tingkat,
            "dasar": dasar,
            "kdprov": kdprov,
            "kdkab": kdkab,
            "kdkec": None,
            "nmprov": nmprov,
            "nmkab": nama_kab(kode_terpilih) if kode_terpilih else None,
            "nmkec": None,
            "target": _ringkas_metrik(
                run_a_meta,
                metrik_a_meta,
                nomor.get(run_a_meta.id) if run_a_meta else None,
            ),
            "pembanding": _ringkas_metrik(
                run_b_meta,
                metrik_b_meta,
                nomor.get(run_b_meta.id) if run_b_meta else None,
            ),
            "baris": baris,
        }

    assert kdkab is not None
    run_a, metrik_a = _pilih_target_a(sesi, kdprov, kdkab, dasar)
    if run_a is None or metrik_a is None:
        return {
            "tingkat": tingkat,
            "dasar": dasar,
            "kdprov": kdprov,
            "kdkab": kdkab,
            "kdkec": kdkec,
            "nmprov": nmprov,
            "nmkab": nama_kab(kode_kabupaten(kdprov, kdkab)),
            "nmkec": None,
            "target": None,
            "pembanding": None,
            "baris": [],
        }

    run_b = sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_B,
            Run.status == STATUS_SUKSES,
            Run.kdprov == kdprov,
            Run.kdkab.in_(kode_kab),
            *_saring_b_setelah_target(run_a),
        )
        .order_by(Run.id.desc())
        .limit(1)
    ).first()
    metrik_b = _metrik_progres(sesi, run_b, dasar) if run_b is not None else None
    if metrik_b is None:
        run_b = None

    target_peta = _metrik_wilayah(sesi, run_a, tingkat, dasar, kdprov, kode_kab, kdkec)
    b_meter = _metrik_wilayah(sesi, run_b, tingkat, dasar, kdprov, kode_kab, kdkec) if run_b else {}

    if tingkat == "kecamatan":
        peta_nama = _peta_nama(sesi, "nmkec", ("kdkec",), saring_nama)
    else:
        peta_nama = _peta_nama(sesi, "nmdesa", ("kdkec", "kddesa"), saring_nama)
    peta_kec = _peta_nama(sesi, "nmkec", ("kdkec",), saring_nama)
    nmkec = peta_kec.get((kdkec,)) if kdkec else None

    baris = []
    for kunci in sorted(set(target_peta) | set(b_meter), key=lambda satu: (satu[0] is None, *satu)):
        target_metrik = target_peta.get(kunci)
        b_metrik = b_meter.get(kunci)
        target = target_metrik["belum"] if target_metrik is not None else 0
        sisa = b_metrik["belum"] if b_metrik is not None else target
        selesai = target - sisa
        kode = kunci[-1]
        induk = kunci[0] if tingkat == "desa" else kode_kabupaten(kdprov, kdkab)
        if kode is None:
            nama = NAMA_TANPA_WILAYAH
        elif tingkat == "kecamatan":
            nama = peta_nama.get((kode,))
        else:
            nama = peta_nama.get((kunci[0], kode)) if kunci[0] is not None else None
        baris.append(
            {
                "kode": kode,
                "induk": induk,
                "nama": nama,
                "level": tingkat,
                "jumlah": target_metrik["jumlah"] if target_metrik is not None else 0,
                "target": target,
                "selesai": selesai,
                "sisa": sisa,
                "persen": round(selesai / target * 100, 2) if target else None,
                "status": _status_tabulasi(target, sisa, b_metrik is not None),
                "ada_b": b_metrik is not None,
            }
        )

    semua = [run for run in (run_a, run_b) if run is not None]
    nomor = nomor_urut_run(sesi, semua)
    return {
        "tingkat": tingkat,
        "dasar": dasar,
        "kdprov": kdprov,
        "kdkab": kdkab,
        "kdkec": kdkec,
        "nmprov": nmprov,
        "nmkab": nama_kab(kode_kabupaten(kdprov, kdkab)),
        "nmkec": nmkec,
        "target": _ringkas_metrik(run_a, metrik_a, nomor.get(run_a.id)),
        "pembanding": _ringkas_metrik(run_b, metrik_b, nomor.get(run_b.id) if run_b else None),
        "baris": baris,
    }


def tren(
    sesi: Session,
    *,
    tingkat: str = "kabupaten",
    tipe: str | None = None,
    provinsi: str | None = None,
    kdkab: str | None = None,
    dasar: str = DASAR_TUGAS,
) -> dict[str, object]:
    """Tren progres per ``tanggal_data``, dibaca dari ``rekap_kabupaten``.

    Untuk tiap (kabupaten/kota, tipe, tanggal) diambil **run sukses terakhir hari
    itu**, lalu dilaporkan ``belum``/``ditindak``/``persen_progres``. Tingkat
    ``provinsi`` menjumlahkan kabupaten/kota per (provinsi, tipe, tanggal): tiap
    kabupaten/kota menyumbang run sukses terakhirnya pada tanggal itu.
    """
    if tingkat not in ("kabupaten", "provinsi"):
        raise KesalahanPerubahan("tingkat tren harus 'kabupaten' atau 'provinsi'")

    terakhir = (
        select(
            Run.kdprov.label("kdprov"),
            Run.kdkab.label("kdkab"),
            Run.tipe.label("tipe"),
            Run.tanggal_data.label("tanggal_data"),
            func.max(Run.id).label("run_id"),
        )
        .where(*_saring_run(tipe, provinsi, kdkab))
        .group_by(Run.kdprov, Run.kdkab, Run.tipe, Run.tanggal_data)
        .subquery()
    )
    hasil = sesi.execute(
        select(
            terakhir.c.kdprov,
            terakhir.c.kdkab,
            terakhir.c.tipe,
            terakhir.c.tanggal_data,
            terakhir.c.run_id,
            RekapKabupaten.belum,
            RekapKabupaten.ditindak_posisi_benar,
            RekapKabupaten.ditindak_posisi_salah,
        )
        .select_from(terakhir)
        .join(Run, Run.id == terakhir.c.run_id)
        .join(
            RekapKabupaten,
            and_(RekapKabupaten.run_id == Run.id, RekapKabupaten.dasar == dasar),
        )
        .order_by(terakhir.c.tanggal_data, terakhir.c.kdprov, terakhir.c.kdkab, terakhir.c.tipe)
    ).mappings()

    kabupaten: list[dict[str, object]] = []
    for satu in hasil:
        nilai = {
            "belum": int(satu["belum"]),
            "ditindak_posisi_benar": int(satu["ditindak_posisi_benar"]),
            "ditindak_posisi_salah": int(satu["ditindak_posisi_salah"]),
        }
        kabupaten.append(
            {
                "tingkat": "kabupaten",
                "kdprov": str(satu["kdprov"]),
                "kdkab": str(satu["kdkab"]),
                "tipe": str(satu["tipe"]),
                "tanggal_data": satu["tanggal_data"],
                "run_id": int(satu["run_id"]),
                "belum": nilai["belum"],
                "ditindak": _ditindak(nilai),
                "persen_progres": _persen(nilai["belum"], _ditindak(nilai)),
            }
        )

    if tingkat == "kabupaten":
        return {"tingkat": tingkat, "dasar": dasar, "tipe": tipe, "baris": kabupaten}

    per_provinsi: dict[tuple[str, str, Any], dict[str, object]] = {}
    for satu in kabupaten:
        kunci = (str(satu["kdprov"]), str(satu["tipe"]), satu["tanggal_data"])
        gabung = per_provinsi.setdefault(
            kunci,
            {
                "tingkat": "provinsi",
                "kdprov": kunci[0],
                "kdkab": None,
                "tipe": kunci[1],
                "tanggal_data": kunci[2],
                "run_id": None,
                "belum": 0,
                "ditindak": 0,
                "persen_progres": None,
            },
        )
        gabung["belum"] = int(gabung["belum"]) + int(satu["belum"])
        gabung["ditindak"] = int(gabung["ditindak"]) + int(satu["ditindak"])
    for satu in per_provinsi.values():
        penyebut = int(satu["belum"]) + int(satu["ditindak"])
        satu["persen_progres"] = round(100.0 * int(satu["ditindak"]) / penyebut, 2) if penyebut else None
    return {
        "tingkat": tingkat,
        "dasar": dasar,
        "tipe": tipe,
        "baris": sorted(per_provinsi.values(), key=lambda satu: (str(satu["tanggal_data"]), str(satu["kdprov"]), str(satu["tipe"]))),
    }


# ------------------------------------------------------------------------ perubahan


def _kunci_desa(baris: Mapping[str, Any]) -> tuple[str, ...]:
    """Kunci desa satu baris ``rekap_desa`` (NULL jadi string kosong)."""
    return tuple(
        "" if baris[nama] is None else str(baris[nama])
        for nama in ("kdprov", "kdkab", "kdkec", "kddesa")
    )


def _selisih(
    awal: Mapping[str, Any] | None, akhir: Mapping[str, Any] | None
) -> dict[str, int]:
    """Selisih (akhir - awal) tiap kolom hitungan; run yang tidak ada dianggap 0."""
    return {
        nama: int(akhir[nama] if akhir is not None else 0)
        - int(awal[nama] if awal is not None else 0)
        for nama in KOLOM_HITUNGAN
    }


def _rekap_satu(
    sesi: Session, tabel: type[RekapDesa] | type[RekapKabupaten], run: Run, dasar: str
) -> Mapping[str, Any] | None:
    """Satu baris rekap (kolom hitungan saja) satu run+dasar, ``None`` kalau kosong."""
    return (
        sesi.execute(
            select(*[getattr(tabel, nama) for nama in KOLOM_HITUNGAN]).where(
                tabel.run_id == run.id, tabel.dasar == dasar
            )
        )
        .mappings()
        .one_or_none()
    )


def _status_titik(repair: Any, edit: Any, initial: Any) -> str:
    """Kategori satu titik (sama dengan kolom rekap); titik tak ada = ``benar_awal``."""
    if repair == 1:
        return "belum"
    if repair == 0 and edit == 1:
        return "ditindak_posisi_benar" if initial == 0 else "ditindak_posisi_salah"
    return "benar_awal"


def _titik_berubah(
    sesi: Session, run_awal: Run, run_akhir: Run, *, limit: int = 200, offset: int = 0
) -> dict[str, object]:
    """Perubahan status per titik (``assignment_id``) antara dua run.

    Kembaliannya hanya titik yang statusnya/flag-nya berbeda, dihitung di basis data
    (tiga bagian: hanya di run awal, berbeda, hanya di run akhir). Titik yang tidak
    ada di ``titik_hasil`` sebuah run berarti tidak perlu perhatian pada run itu
    (``benar_awal``), karena baris seperti itu sudah dipangkas dari penyimpanan.
    """

    def potongan(run_id: int) -> Any:
        return (
            select(
                TitikHasil.assignment_id.label("assignment_id"),
                TitikHasil.flag_repair.label("flag_repair"),
                TitikHasil.flag_edit_atr_repair.label("flag_edit_atr_repair"),
                TitikHasil.flag_repair_initial.label("flag_repair_initial"),
            )
            .where(TitikHasil.run_id == run_id)
            .subquery()
        )

    awal = potongan(run_awal.id)
    akhir = potongan(run_akhir.id)
    sama_syarat = or_(
        func.coalesce(awal.c.flag_repair, -1) != func.coalesce(akhir.c.flag_repair, -1),
        func.coalesce(awal.c.flag_edit_atr_repair, -1)
        != func.coalesce(akhir.c.flag_edit_atr_repair, -1),
        func.coalesce(awal.c.flag_repair_initial, -1)
        != func.coalesce(akhir.c.flag_repair_initial, -1),
    )
    hanya_awal = (
        select(
            awal.c.assignment_id,
            awal.c.flag_repair.label("flag_repair_awal"),
            awal.c.flag_edit_atr_repair.label("flag_edit_atr_repair_awal"),
            awal.c.flag_repair_initial.label("flag_repair_initial_awal"),
            null().label("flag_repair_akhir"),
            null().label("flag_edit_atr_repair_akhir"),
            null().label("flag_repair_initial_akhir"),
        )
        .select_from(awal)
        .outerjoin(akhir, akhir.c.assignment_id == awal.c.assignment_id)
        .where(akhir.c.assignment_id.is_(None))
    )
    berbeda = (
        select(
            awal.c.assignment_id,
            awal.c.flag_repair.label("flag_repair_awal"),
            awal.c.flag_edit_atr_repair.label("flag_edit_atr_repair_awal"),
            awal.c.flag_repair_initial.label("flag_repair_initial_awal"),
            akhir.c.flag_repair.label("flag_repair_akhir"),
            akhir.c.flag_edit_atr_repair.label("flag_edit_atr_repair_akhir"),
            akhir.c.flag_repair_initial.label("flag_repair_initial_akhir"),
        )
        .select_from(awal)
        .join(akhir, akhir.c.assignment_id == awal.c.assignment_id)
        .where(sama_syarat)
    )
    hanya_akhir = (
        select(
            akhir.c.assignment_id,
            null().label("flag_repair_awal"),
            null().label("flag_edit_atr_repair_awal"),
            null().label("flag_repair_initial_awal"),
            akhir.c.flag_repair.label("flag_repair_akhir"),
            akhir.c.flag_edit_atr_repair.label("flag_edit_atr_repair_akhir"),
            akhir.c.flag_repair_initial.label("flag_repair_initial_akhir"),
        )
        .select_from(akhir)
        .outerjoin(awal, awal.c.assignment_id == akhir.c.assignment_id)
        .where(awal.c.assignment_id.is_(None))
    )
    gabung = union_all(hanya_awal, berbeda, hanya_akhir).subquery()

    total = int(sesi.scalar(select(func.count()).select_from(gabung)) or 0)
    baris = []
    for satu in sesi.execute(
        select(gabung).order_by(gabung.c.assignment_id).limit(limit).offset(offset)
    ).mappings():
        baris.append(
            {
                "assignment_id": str(satu["assignment_id"]),
                "status_awal": _status_titik(
                    satu["flag_repair_awal"],
                    satu["flag_edit_atr_repair_awal"],
                    satu["flag_repair_initial_awal"],
                ),
                "status_akhir": _status_titik(
                    satu["flag_repair_akhir"],
                    satu["flag_edit_atr_repair_akhir"],
                    satu["flag_repair_initial_akhir"],
                ),
                "flag_repair_awal": satu["flag_repair_awal"],
                "flag_repair_akhir": satu["flag_repair_akhir"],
                "flag_edit_atr_repair_awal": satu["flag_edit_atr_repair_awal"],
                "flag_edit_atr_repair_akhir": satu["flag_edit_atr_repair_akhir"],
                "flag_repair_initial_awal": satu["flag_repair_initial_awal"],
                "flag_repair_initial_akhir": satu["flag_repair_initial_akhir"],
            }
        )
    return {
        "run_awal": run_awal.id,
        "run_akhir": run_akhir.id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "baris": baris,
    }


def perubahan(
    sesi: Session,
    *,
    run_awal: Run,
    run_akhir: Run,
    dasar: str = DASAR_TUGAS,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, object]:
    """Perubahan antara dua run: selisih rekap + (kalau memenuhi syarat) per titik.

    - Selisih rekap kabupaten dan desa dihitung untuk **pasangan run mana pun**
      (baris yang semua selisihnya 0 tidak dibalas);
    - perubahan status per titik (``assignment_id``) hanya dihitung kalau pasangannya
      **baseline vs run sukses terakhir** untuk kabupaten/kota+tipe yang sama dan
      detail titik kedua run masih tersedia.
    """
    if run_awal.status != STATUS_SUKSES or run_akhir.status != STATUS_SUKSES:
        raise KesalahanPerubahan("perubahan hanya bisa dihitung untuk run yang sudah sukses")

    kab_awal = _rekap_satu(sesi, RekapKabupaten, run_awal, dasar)
    kab_akhir = _rekap_satu(sesi, RekapKabupaten, run_akhir, dasar)

    def rekap_desa(run: Run) -> dict[tuple[str, ...], Mapping[str, Any]]:
        kolom = ("kdprov", "kdkab", "kdkec", "kddesa", *KOLOM_HITUNGAN)
        return {
            _kunci_desa(satu): satu
            for satu in sesi.execute(
                select(*[getattr(RekapDesa, nama) for nama in kolom]).where(
                    RekapDesa.run_id == run.id, RekapDesa.dasar == dasar
                )
            ).mappings()
        }

    desa_awal, desa_akhir = rekap_desa(run_awal), rekap_desa(run_akhir)
    desa: list[dict[str, object]] = []
    for kunci in sorted(set(desa_awal) | set(desa_akhir)):
        selisih = _selisih(desa_awal.get(kunci), desa_akhir.get(kunci))
        if any(selisih.values()):
            desa.append(
                {
                    "kdprov": kunci[0] or None,
                    "kdkab": kunci[1] or None,
                    "kdkec": kunci[2] or None,
                    "kddesa": kunci[3] or None,
                    "selisih": selisih,
                }
            )

    catatan: list[str] = []
    titik: dict[str, object] | None = None
    kunci_sama = (run_awal.kdprov, run_awal.kdkab, run_awal.tipe) == (
        run_akhir.kdprov,
        run_akhir.kdkab,
        run_akhir.tipe,
    )
    if not kunci_sama:
        catatan.append(
            "selisih menjumlahkan kabupaten/kota atau tipe yang berbeda; "
            "perubahan per titik hanya untuk pasangan baseline vs run terbaru "
            "pada kabupaten/kota+tipe yang sama"
        )
    else:
        urut = modul_rekap.run_sekelompok(sesi, run_awal)
        baseline, terbaru = (urut[0], urut[-1]) if urut else (None, None)
        if {run_awal.id, run_akhir.id} == {baseline, terbaru}:
            if run_awal.detail_tersedia and run_akhir.detail_tersedia:
                titik = _titik_berubah(sesi, run_awal, run_akhir, limit=limit, offset=offset)
            else:
                catatan.append(
                    "detail titik salah satu run sudah dipangkas; "
                    "perubahan per titik tidak bisa dihitung"
                )
        else:
            catatan.append(
                "perubahan per titik hanya untuk pasangan baseline "
                f"(run {baseline}) vs run sukses terakhir (run {terbaru})"
            )

    return {
        "run_awal": run_awal.id,
        "run_akhir": run_akhir.id,
        "dasar": dasar,
        "kabupaten": _selisih(kab_awal, kab_akhir),
        "desa": desa,
        "titik": titik,
        "catatan": " ".join(catatan) if catatan else None,
    }
