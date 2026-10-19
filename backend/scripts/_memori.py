"""Baca pemakaian memori proses (RSS) di Windows tanpa dependensi tambahan.

Dipakai oleh skrip pengukuran di folder ini (``ukur_*.py``). Kalau API-nya tidak
tersedia (bukan Windows), fungsi mengembalikan ``None`` dan pelaporan jadi "n/a".
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class _ProcessMemoryCounters(ctypes.Structure):
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


def memori(metrik: str = "WorkingSetSize") -> float | None:
    """Pemakaian memori proses dalam MB (``WorkingSetSize`` atau puncaknya)."""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        fungsi = kernel32.K32GetProcessMemoryInfo
        fungsi.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD]
        fungsi.restype = wintypes.BOOL

        counter = _ProcessMemoryCounters()
        counter.cb = ctypes.sizeof(_ProcessMemoryCounters)
        proses = kernel32.GetCurrentProcess()
        if not fungsi(proses, ctypes.byref(counter), counter.cb):
            return None
        return getattr(counter, metrik) / 1024 / 1024
    except Exception:  # bukan Windows / API tidak ada
        return None


def mb(nilai: float | None) -> str:
    """Format MB untuk pelaporan."""
    return "n/a" if nilai is None else f"{nilai:,.0f} MB"
