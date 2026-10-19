"""Pemetaan kode unit SSO BPS (``org``) ke peran aplikasi.

SSO BPS (lihat ``docs/Panduan SSO Client.pdf``) mengembalikan atribut ``org``
berupa kode unit organisasi. Untuk sementara disepakati bentuk 4 digit:

- ``3300`` -> admin provinsi (2 digit terakhir ``00``);
- ``3307`` -> petugas kabupaten/kota (2 digit pertama provinsi, 2 digit terakhir
  kabupaten/kota).

Modul ini murni fungsi; penegakan otorisasi di endpoint menunggu T4 (SSO).
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


def peran_dari_org(org: str) -> Peran:
    """Turunkan peran dari kode unit SSO 4 digit.

    ``3300`` = admin provinsi, ``3307`` = petugas kabupaten/kota. Nilai selain
    4 digit ditolak supaya kesalahan konfigurasi SSO tidak diam-diam memberi
    akses wilayah yang salah.
    """
    bersih = str(org or "").strip()
    if len(bersih) != 4 or not bersih.isdigit():
        raise ValueError(f"kode org SSO harus 4 digit, bukan '{org}'")

    kdprov = bersih[:2]
    if bersih[2:] == "00":
        return Peran(nama=PERAN_ADMIN_PROVINSI, kdprov=kdprov, kdkab=None)
    return Peran(nama=PERAN_PETUGAS_KABKOT, kdprov=kdprov, kdkab=bersih)
