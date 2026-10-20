"""Uji unggahan 100 MB: aliran body tidak boleh ditahan di memori."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import sys
import tracemalloc
from pathlib import Path
from typing import Any

import pytest

from app import auth
from app.config import Settings
from app.unggahan import unggah_berkas

BLOK = b"x" * (1024 * 1024)
JUMLAH_BLOK = 100


class PermintaanAliran:
    """Request palsu yang mengalirkan body per 1 MB, seperti Request.stream()."""

    headers = {"content-type": "application/octet-stream"}

    async def stream(self):
        for _ in range(JUMLAH_BLOK):
            yield BLOK


def rss_bytes() -> int | None:
    """RSS proses saat ini (Windows/Linux); None bila tidak didukung."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        memori = ProcessMemoryCounters()
        memori.cb = ctypes.sizeof(ProcessMemoryCounters)
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(memori), memori.cb
        ):
            return None
        return int(memori.WorkingSetSize)

    try:
        with open("/proc/self/status", encoding="ascii") as berkas:
            for baris in berkas:
                if baris.startswith("VmRSS:"):
                    return int(baris.split()[1]) * 1024
    except OSError:
        return None
    return None


@pytest.mark.slow
def test_unggah_100mb_tidak_menahan_body(
    setelan: Settings, dir_unggahan: Path
) -> None:
    """SHA-256 sama, berkas 100 MB utuh, dan kenaikan RSS jauh di bawah 100 MB."""
    hash_harapan = hashlib.sha256()
    for _ in range(JUMLAH_BLOK):
        hash_harapan.update(BLOK)

    rss_awal = rss_bytes()
    tracemalloc.start()
    hasil = asyncio.run(
        unggah_berkas(
            request=PermintaanAliran(),  # type: ignore[arg-type]
            jenis="peta",
            nama="besar_100mb.gpkg",
            setelan=setelan,
            pengguna=auth._pengguna_dev(),
        )
    )
    _, puncak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_akhir = rss_bytes()

    assert hasil.ukuran == JUMLAH_BLOK * len(BLOK)
    assert hasil.sha256 == hash_harapan.hexdigest()

    berkas = dir_unggahan / "_unggahan" / hasil.unggahan_id / "besar_100mb.gpkg"
    assert berkas.stat().st_size == hasil.ukuran
    with berkas.open("rb") as masuk:
        hash_berkas = hashlib.sha256()
        while True:
            blok = masuk.read(4 * 1024 * 1024)
            if not blok:
                break
            hash_berkas.update(blok)
    assert hash_berkas.hexdigest() == hasil.sha256

    # Jika endpoint menahan seluruh body, puncak tracemalloc/RSS akan ~100 MB.
    assert puncak < 20 * 1024 * 1024
    if rss_awal is not None and rss_akhir is not None:
        assert rss_akhir - rss_awal < 20 * 1024 * 1024
