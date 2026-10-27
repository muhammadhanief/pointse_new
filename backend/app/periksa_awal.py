"""Periksa kelengkapan kolom dari **potongan awal** berkas unggahan.

Berkas masukan bisa ratusan MB dan dikirim berpotongan. Kalau kolom wajib baru
diperiksa saat ``POST /runs`` (yaitu setelah semua potongan terkirim dan
disusun), pengguna menunggu seluruh berkas terkirim hanya untuk mendapat pesan
bahwa berkasnya kurang kolom. Modul ini membaca potongan pertama saja:

- **GeoJSON**: nama properti fitur pertama dibaca dari awal teks;
- **GeoPackage/SQLite**: nama kolom dibaca dari teks ``CREATE TABLE`` pada
  halaman awal berkas (skema GeoPackage selalu di awal berkas).

Penilaiannya *best effort*: kalau bentuk berkas tidak dikenali atau potongan
awal belum memuat skema, fungsi mengembalikan ``None`` dan pemeriksaan penuh
tetap dilakukan saat job dibuat (``layanan.periksa_unggahan``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.layanan import (
    KOLOM_PETA,
    KOLOM_PETA_TAMBAHAN,
    KOLOM_TITIK,
    KOLOM_TITIK_B,
    KOLOM_TITIK_B_TAMBAHAN,
)

#: Banyaknya byte awal yang dibaca (potongan unggahan default 16 MiB).
BATAS_BACA = 4 * 1024 * 1024

#: Jendela teks setelah ``CREATE TABLE`` yang ikut dibaca sebagai skema.
_JENDELA_SKEMA = 12_000

#: Penanda bentuk berkas titik: masukan mentah GS (A) atau keluaran Proses A (B).
_TANDA_A = frozenset({"geotag_latitude", "count_usaha"})
_TANDA_B = frozenset({"idsubsls_origin", "jumlah_usaha_ditemukan"})

_TIPE_SQL = (
    "TEXT|INTEGER|INT|BIGINT|SMALLINT|MEDIUMINT|REAL|DOUBLE|FLOAT|NUMERIC|"
    "BOOLEAN|BLOB|DATE|DATETIME|VARCHAR|CHAR|DECIMAL"
)


def _akhir_objek(isi: bytes, mulai: int) -> int | None:
    """Indeks setelah ``}`` penutup objek JSON yang dimulai di ``mulai``."""
    kedalaman = 0
    dalam_teks = False
    lolos = False
    for posisi in range(mulai, len(isi)):
        huruf = isi[posisi : posisi + 1]
        if dalam_teks:
            if lolos:
                lolos = False
            elif huruf == b"\\":
                lolos = True
            elif huruf == b'"':
                dalam_teks = False
            continue
        if huruf == b'"':
            dalam_teks = True
        elif huruf == b"{":
            kedalaman += 1
        elif huruf == b"}":
            kedalaman -= 1
            if kedalaman == 0:
                return posisi + 1
    return None


def _kolom_geojson(isi: bytes) -> tuple[str, ...] | None:
    """Nama properti fitur pertama GeoJSON (``None`` kalau belum lengkap)."""
    awal = isi.find(b'"features"')
    if awal < 0:
        return None
    kurung = isi.find(b"[", awal)
    mulai = isi.find(b"{", awal) if kurung < 0 else isi.find(b"{", kurung)
    if mulai < 0:
        return None
    akhir = _akhir_objek(isi, mulai)
    if akhir is None:
        return None
    try:
        fitur = json.loads(isi[mulai:akhir])
    except ValueError:
        return None
    sifat = fitur.get("properties") if isinstance(fitur, dict) else None
    if not isinstance(sifat, dict):
        return None
    return tuple(sorted(str(nama) for nama in sifat))


def _kolom_gpkg(isi: bytes) -> tuple[str, ...] | None:
    """Nama kolom dari teks ``CREATE TABLE`` pada halaman awal GeoPackage."""
    if not isi.startswith(b"SQLite format 3"):
        return None
    kolom: set[str] = set()
    posisi = 0
    jumlah_tabel = 0
    while True:
        posisi = isi.find(b"CREATE TABLE", posisi)
        if posisi < 0:
            break
        jumlah_tabel += 1
        teks = isi[posisi : posisi + _JENDELA_SKEMA].decode("utf-8", "replace")
        kolom.update(_nama_kolom_sql(teks))
        posisi += len(b"CREATE TABLE")
    if jumlah_tabel == 0:
        return None
    return tuple(sorted(kolom))


def _nama_kolom_sql(teks: str) -> set[str]:
    """Ambil nama kolom dari satu pernyataan ``CREATE TABLE`` (perkiraan)."""
    pola = re.compile(
        rf'(?:"([^"]+)"|\[([^\]]+)\]|`([^`]+)`|([A-Za-z_][A-Za-z0-9_]*))'
        rf"\s+(?:{_TIPE_SQL})\b",
        re.IGNORECASE,
    )
    return {
        next(nilai for nilai in cocok.groups() if nilai).lower()
        for cocok in pola.finditer(teks)
    }


def kolom_dari_potongan(jalur: Path) -> tuple[str, ...] | None:
    """Kolom yang bisa dibaca dari potongan awal; ``None`` kalau tak dikenali."""
    try:
        with jalur.open("rb") as berkas:
            isi = berkas.read(BATAS_BACA)
    except OSError:
        return None
    return _kolom_geojson(isi) or _kolom_gpkg(isi)


def _profil(jenis: str, kolom: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Daftar kemungkinan susunan kolom wajib untuk satu jenis unggahan."""
    if jenis == "peta":
        return [(*KOLOM_PETA, *KOLOM_PETA_TAMBAHAN)]
    if jenis == "master":
        return [KOLOM_TITIK]
    if jenis != "titik":
        return []
    kumpulan = set(kolom)
    punya_a = _TANDA_A <= kumpulan
    punya_b = _TANDA_B <= kumpulan
    if punya_a and not punya_b:
        return [KOLOM_TITIK]
    if punya_b and not punya_a:
        return [(*KOLOM_TITIK_B, *KOLOM_TITIK_B_TAMBAHAN)]
    # Tidak bisa dibedakan: terima kalau salah satu susunan terpenuhi.
    return [KOLOM_TITIK, (*KOLOM_TITIK_B, *KOLOM_TITIK_B_TAMBAHAN)]


def kurang_kolom(jalur: Path, jenis: str | None) -> tuple[str, ...] | None:
    """Kolom wajib yang belum ada; ``None`` artinya tidak bisa dinilai lebih awal."""
    kolom = kolom_dari_potongan(jalur)
    if kolom is None:
        return None
    profil = _profil(str(jenis or ""), kolom)
    if not profil:
        return None
    kumpulan = set(kolom)
    terbaik = min(profil, key=lambda wajib: len(set(wajib) - kumpulan))
    return tuple(sorted(set(terbaik) - kumpulan))
