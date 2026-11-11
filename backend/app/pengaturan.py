"""Pengaturan aplikasi (key-value) yang dapat diubah admin provinsi.

Modul ini sengaja sangat ringan: hanya membaca/menulis tabel ``pengaturan``
lewat SQLAlchemy, tanpa impor pustaka spasial, sehingga aman dipakai proses API.

Satu pengaturan yang dipakai saat ini:

- :data:`app.models.KUNCI_LUAS_MIN_BATAS` (``rekonsiliasi_batas_luas_min_m2``):
  ambang luas minimum temuan Gap/Overlap dalam m2. Nilai ``0`` berarti semua
  temuan yang dinyatakan mesin GEOS/QGIS ikut dicatat (identik dengan
  Topology Checker QGIS 3.44 pada layer gabungan), sedangkan nilai lebih besar
  (mis. ``1e-6`` = 1 mm2) membuang temuan mikroskopis akibat selisih desimal
  koordinat.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KUNCI_LUAS_MIN_BATAS, Pengaturan, sekarang

#: Ambang luas minimum bawaan (m2): tanpa filter, sama dengan Topology Checker QGIS.
LUAS_MIN_BATAS_BAWAAN: float = 0.0


def baca_nilai(sesi: Session, kunci: str) -> str | None:
    """Ambil nilai pengaturan mentah; ``None`` bila belum pernah disimpan."""
    baris = sesi.get(Pengaturan, kunci)
    if baris is None:
        return None
    return baris.nilai


def tulis_nilai(
    sesi: Session, kunci: str, nilai: str, oleh: str | None = None
) -> None:
    """Simpan (upsert) satu pengaturan; pemanggil yang melakukan commit."""
    baris = sesi.get(Pengaturan, kunci)
    if baris is None:
        sesi.add(Pengaturan(kunci=kunci, nilai=nilai, updated_by=oleh))
        return
    baris.nilai = nilai
    baris.updated_by = oleh
    baris.updated_at = sekarang()


def baca_luas_min_batas(sesi: Session) -> float:
    """Ambang luas minimum Gap/Overlap yang berlaku (m2).

    Nilai kosong, tidak valid, atau negatif dianggap :data:`LUAS_MIN_BATAS_BAWAAN`.
    Bila tabel ``pengaturan`` belum ada (migrasi 0027 belum dijalankan), nilai
    bawaan dipakai supaya job Validasi SLS tetap berjalan.
    """
    if not ada_tabel_pengaturan(sesi):
        return LUAS_MIN_BATAS_BAWAAN
    mentah = baca_nilai(sesi, KUNCI_LUAS_MIN_BATAS)
    if mentah is None:
        return LUAS_MIN_BATAS_BAWAAN
    try:
        nilai = float(mentah.replace(",", "."))
    except (TypeError, ValueError):
        return LUAS_MIN_BATAS_BAWAAN
    if nilai != nilai or nilai < 0:  # NaN atau negatif
        return LUAS_MIN_BATAS_BAWAAN
    return nilai


def tulis_luas_min_batas(
    sesi: Session, nilai: float, oleh: str | None = None
) -> float:
    """Simpan ambang luas minimum; mengembalikan nilai yang benar-benar disimpan."""
    if nilai != nilai or nilai < 0:  # NaN atau negatif
        nilai = LUAS_MIN_BATAS_BAWAAN
    tulis_nilai(sesi, KUNCI_LUAS_MIN_BATAS, repr(float(nilai)), oleh=oleh)
    return float(nilai)


def ada_tabel_pengaturan(sesi: Session) -> bool:
    """Apakah tabel ``pengaturan`` sudah ada (migrasi 0027 sudah dijalankan)."""
    from sqlalchemy import inspect

    return inspect(sesi.get_bind()).has_table(Pengaturan.__tablename__)


def ambil_semua(sesi: Session) -> dict[str, str]:
    """Semua pengaturan sebagai kamus (untuk ditampilkan di halaman admin)."""
    hasil: dict[str, str] = {}
    for baris in sesi.scalars(select(Pengaturan)).all():
        hasil[baris.kunci] = baris.nilai
    return hasil