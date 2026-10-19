"""Pemetaan kode unit SSO BPS (``org``) ke peran aplikasi.

SSO BPS (lihat ``docs/Panduan SSO Client.pdf``) mengembalikan atribut ``org``
berupa kode unit organisasi. Panduan SSO memakai contoh 5 digit (``34000``),
sedangkan asumsi awal aplikasi memakai 4 digit (``3300``). Keduanya diterima:

- 5 digit dinormalisasi ke 4 digit dengan membuang digit terakhir (kode sub-unit),
  mis. ``33000`` -> ``3300`` dan ``33070`` -> ``3307``;
- 4 digit dipakai apa adanya.

Setelah normalisasi:

- ``3300`` -> admin provinsi (2 digit terakhir ``00``);
- ``3307`` -> petugas kabupaten/kota (2 digit pertama provinsi, 2 digit terakhir
  kabupaten/kota).
"""

from __future__ import annotations

from dataclasses import dataclass

PERAN_ADMIN_PROVINSI = "admin_provinsi"
PERAN_PETUGAS_KABKOT = "petugas_kabkot"


@dataclass(frozen=True)
class Peran:
    """Peran + wilayah kerja yang diturunkan dari kode unit SSO."""

    nama: str
    kdprov: str
    #: Kode kabupaten/kota 4 digit; ``None`` untuk admin provinsi.
    kdkab: str | None


def kode_org_4_digit(org: str) -> str:
    """Normalisasi ``org`` SSO ke kode unit 4 digit (provinsi + kabupaten/kota)."""
    bersih = str(org or "").strip()
    if not bersih.isdigit() or len(bersih) not in (4, 5):
        raise ValueError(f"kode org SSO harus 4 atau 5 digit, bukan '{org}'")
    return bersih[:4]


def peran_dari_org(org: str) -> Peran:
    """Turunkan peran dari kode unit SSO 4/5 digit.

    ``3300``/``33000`` = admin provinsi, ``3307``/``33070`` = petugas
    kabupaten/kota. Nilai selain 4/5 digit ditolak supaya kesalahan konfigurasi
    SSO tidak diam-diam memberi akses wilayah yang salah.
    """
    bersih = kode_org_4_digit(org)
    kdprov = bersih[:2]
    if bersih[2:] == "00":
        return Peran(nama=PERAN_ADMIN_PROVINSI, kdprov=kdprov, kdkab=None)
    return Peran(nama=PERAN_PETUGAS_KABKOT, kdprov=kdprov, kdkab=bersih)
