"""Status sistem untuk halaman admin: worker, antrean, RAM, CPU, dan disk.

Endpoint ini hanya membaca. Status worker ditentukan oleh berkas ``flock`` yang
sama dengan yang dipakai worker, sedangkan PID dibaca dari berkas ``<lock>.pid``
(lihat :mod:`app.kunci`). Metrik host dibaca dari ``/proc`` di Linux dan dari
Windows API di lingkungan pengembangan Windows; nilai yang tidak tersedia
dikembalikan ``None`` agar UI bisa menampilkan tanda "-".
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.config import Settings, get_settings
from app.db import get_session
from app.kunci import KunciBerkas, baca_pid_kunci, jalur_kunci
from app.models import (
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    WORKER_BERHENTI,
    Run,
    WorkerEvent,
    WorkerHeartbeat,
    sekarang,
)
from app.peran import PERAN_ADMIN_PROVINSI
from app.skema import (
    AntreanOut,
    BackupOut,
    DiskOut,
    JobSistemOut,
    KonfigurasiWorkerOut,
    MemoriOut,
    SistemOut,
    SistemStatusOut,
    WorkerEventOut,
    WorkerHeartbeatOut,
    WorkerOut,
)

router = APIRouter()

_MB = 1024 * 1024
#: Batas peringatan agar admin sempat bertindak sebelum worker kehabisan RAM.
_MIN_RAM_SERVER_MB = 512
_MIN_DISK_MB = 1024


class _MemoriWindows(ctypes.Structure):
    """Struktur ``MEMORYSTATUSEX`` untuk Windows."""

    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _MemoriProsesWindows(ctypes.Structure):
    """Struktur ``PROCESS_MEMORY_COUNTERS`` untuk Windows."""

    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _mb(nilai: int | float | None) -> float | None:
    """Ubah byte ke MB dengan satu angka desimal."""
    return None if nilai is None else round(float(nilai) / _MB, 1)


def _baca_memori_linux() -> MemoriOut:
    """Baca ``/proc/meminfo``; nilai yang hilang dibiarkan ``None``."""
    nilai: dict[str, int] = {}
    try:
        with Path("/proc/meminfo").open(encoding="ascii", errors="ignore") as berkas:
            for baris in berkas:
                bagian = baris.split()
                if len(bagian) >= 2 and bagian[0].endswith(":"):
                    try:
                        nilai[bagian[0][:-1]] = int(bagian[1]) * 1024
                    except ValueError:
                        continue
    except OSError:
        return MemoriOut()

    total = nilai.get("MemTotal")
    tersedia = nilai.get("MemAvailable")
    if tersedia is None and "MemFree" in nilai:
        tersedia = (
            nilai["MemFree"]
            + nilai.get("Buffers", 0)
            + nilai.get("Cached", 0)
        )
    return _susun_memori(
        total=total,
        tersedia=tersedia,
        swap_total=nilai.get("SwapTotal"),
        swap_tersedia=nilai.get("SwapFree"),
    )


def _baca_memori_windows() -> MemoriOut:
    """Baca RAM host lewat ``GlobalMemoryStatusEx``."""
    try:
        status = _MemoriWindows()
        status.dwLength = ctypes.sizeof(status)
        fungsi = ctypes.windll.kernel32.GlobalMemoryStatusEx
        fungsi.argtypes = [ctypes.POINTER(_MemoriWindows)]
        fungsi.restype = ctypes.c_bool
        if not fungsi(ctypes.byref(status)):
            return MemoriOut()
    except (AttributeError, OSError, ValueError):
        return MemoriOut()

    # Page file bukan swap murni; tetap berguna sebagai indikasi pemakaian.
    return _susun_memori(
        total=status.ullTotalPhys,
        tersedia=status.ullAvailPhys,
        swap_total=status.ullTotalPageFile,
        swap_tersedia=status.ullAvailPageFile,
    )


def _susun_memori(
    *,
    total: int | None,
    tersedia: int | None,
    swap_total: int | None,
    swap_tersedia: int | None,
) -> MemoriOut:
    """Hitung nilai turunan memori dalam MB."""
    terpakai = (
        max(0, total - tersedia)
        if total is not None and tersedia is not None
        else None
    )
    swap_terpakai = (
        max(0, swap_total - swap_tersedia)
        if swap_total is not None and swap_tersedia is not None
        else None
    )
    persen = (
        round(terpakai / total * 100, 1)
        if terpakai is not None and total
        else None
    )
    return MemoriOut(
        total_mb=_mb(total),
        tersedia_mb=_mb(tersedia),
        terpakai_mb=_mb(terpakai),
        persen_terpakai=persen,
        swap_total_mb=_mb(swap_total),
        swap_terpakai_mb=_mb(swap_terpakai),
    )


def _baca_memori() -> MemoriOut:
    """Baca memori host sesuai platform."""
    return _baca_memori_windows() if os.name == "nt" else _baca_memori_linux()


def _rss_windows(pid: int) -> float | None:
    """RSS proses Windows lewat ``GetProcessMemoryInfo``."""
    if pid <= 0:
        return None
    proses = None
    try:
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.OpenProcess.argtypes = [
            ctypes.c_ulong,
            ctypes.c_bool,
            ctypes.c_ulong,
        ]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_MemoriProsesWindows),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_bool

        proses = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        if not proses:
            return None
        memori = _MemoriProsesWindows()
        memori.cb = ctypes.sizeof(memori)
        if not psapi.GetProcessMemoryInfo(
            proses, ctypes.byref(memori), memori.cb
        ):
            return None
        return _mb(memori.WorkingSetSize)
    except (AttributeError, OSError, ValueError):
        return None
    finally:
        if proses:
            try:
                ctypes.windll.kernel32.CloseHandle(proses)
            except (AttributeError, OSError):
                pass


def _rss_proses(pid: int | None) -> float | None:
    """RSS proses (MB); ``None`` bila PID kosong atau tidak bisa dibaca."""
    if pid is None or pid <= 0:
        return None
    if os.name == "nt":
        return _rss_windows(pid)
    try:
        bagian = Path(f"/proc/{pid}/statm").read_text(encoding="ascii").split()
        halaman = int(bagian[1])
        ukuran_halaman = os.sysconf("SC_PAGE_SIZE")
        return _mb(halaman * ukuran_halaman)
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def _cari_pid_worker_linux() -> int | None:
    """Cari proses ``python -m app.worker`` di ``/proc`` bila PID lock kosong."""
    try:
        calon = Path("/proc")
        for item in calon.iterdir():
            if not item.name.isdigit():
                continue
            try:
                perintah = (item / "cmdline").read_bytes().replace(b"\0", b" ")
                teks = perintah.decode("utf-8", errors="ignore")
            except OSError:
                continue
            if "app.worker" in teks and "pantau_worker" not in teks:
                return int(item.name)
    except OSError:
        pass
    return None


def _status_worker(setelan: Settings) -> tuple[bool, int | None]:
    """Kembalikan (kunci dipegang, PID worker).

    Pemeriksaan memakai ``flock`` nonblocking; saat kunci bebas, kunci langsung
    dilepas sehingga pemanggilan status tidak menghalangi worker.
    """
    jalur = jalur_kunci(setelan)
    kunci = KunciBerkas(jalur)
    if kunci.ambil(tulis_pid=False):
        kunci.lepas()
        return False, None

    pid = baca_pid_kunci(jalur)
    if pid is None and os.name != "nt":
        pid = _cari_pid_worker_linux()
    return True, pid


def _baca_disk(setelan: Settings) -> DiskOut:
    """Pemakaian disk folder data; fallback ke direktori kerja."""
    jalur = Path(setelan.dir_unggahan).expanduser()
    if not jalur.exists():
        jalur = Path.cwd()
    try:
        pakai = shutil.disk_usage(str(jalur))
    except OSError:
        return DiskOut()
    persen = round(pakai.used / pakai.total * 100, 1) if pakai.total else None
    return DiskOut(
        total_mb=_mb(pakai.total),
        terpakai_mb=_mb(pakai.used),
        tersedia_mb=_mb(pakai.free),
        persen_terpakai=persen,
    )


def _baca_load() -> tuple[float | None, float | None, float | None]:
    """Load average 1/5/15 menit; tidak tersedia di Windows."""
    try:
        satu, lima, lima_belas = os.getloadavg()
        return round(satu, 2), round(lima, 2), round(lima_belas, 2)
    except (AttributeError, OSError):
        return None, None, None


def _job_out(run: Run, waktu: datetime) -> JobSistemOut:
    """Bentuk ringkasan job + umur heartbeat."""
    acuan = run.heartbeat_at or run.started_at
    umur = (
        max(0, int((waktu - acuan).total_seconds()))
        if run.status == STATUS_JALAN and acuan is not None
        else None
    )
    return JobSistemOut(
        id=run.id,
        tipe=run.tipe,
        kdprov=run.kdprov,
        kdkab=run.kdkab,
        user=run.user,
        status=run.status,
        jumlah_baris=run.jumlah_baris,
        jumlah_tanpa_wilayah=run.jumlah_tanpa_wilayah,
        pesan=run.pesan,
        created_at=run.created_at,
        started_at=run.started_at,
        heartbeat_at=run.heartbeat_at,
        finished_at=run.finished_at,
        umur_heartbeat_detik=umur,
    )


def _ambil_antrean(
    sesi: Session, waktu: datetime
) -> tuple[AntreanOut, list[JobSistemOut], JobSistemOut | None]:
    """Ambil hitungan status, job aktif, dan job terakhir."""
    hitungan = {
        str(status): int(jumlah)
        for status, jumlah in sesi.execute(
            select(Run.status, func.count()).group_by(Run.status)
        )
    }
    job_aktif = [
        _job_out(run, waktu)
        for run in sesi.scalars(
            select(Run)
            .where(Run.status == STATUS_JALAN)
            .order_by(Run.id)
            .limit(10)
        )
    ]
    terakhir = sesi.scalars(
        select(Run)
        .where(Run.status.in_([STATUS_SUKSES, STATUS_GAGAL]))
        .order_by(Run.finished_at.desc(), Run.id.desc())
        .limit(1)
    ).first()
    tertua = sesi.scalar(
        select(func.min(Run.created_at)).where(Run.status == STATUS_MENUNGGU)
    )
    total = sum(hitungan.values())
    antrean = AntreanOut(
        menunggu=hitungan.get(STATUS_MENUNGGU, 0),
        jalan=hitungan.get(STATUS_JALAN, 0),
        sukses=hitungan.get(STATUS_SUKSES, 0),
        gagal=hitungan.get(STATUS_GAGAL, 0),
        total=total,
        tertua_menunggu=tertua,
    )
    return antrean, job_aktif, (_job_out(terakhir, waktu) if terakhir else None)


def _baca_heartbeat(
    sesi: Session, waktu: datetime, setelan: Settings
) -> list[WorkerHeartbeatOut]:
    """Ambil heartbeat worker terbaru dan hitung status hidupnya."""
    hasil: list[WorkerHeartbeatOut] = []
    for baris in sesi.scalars(
        select(WorkerHeartbeat)
        .order_by(WorkerHeartbeat.heartbeat_at.desc())
        .limit(20)
    ):
        umur = max(0, int((waktu - baris.heartbeat_at).total_seconds()))
        aktif = (
            baris.status != WORKER_BERHENTI
            and umur <= setelan.worker_heartbeat_timeout_detik
        )
        hasil.append(
            WorkerHeartbeatOut(
                worker_id=baris.worker_id,
                pid=baris.pid,
                run_id=baris.run_id,
                hostname=baris.hostname,
                status=baris.status,
                started_at=baris.started_at,
                heartbeat_at=baris.heartbeat_at,
                umur_heartbeat_detik=umur,
                aktif=aktif,
            )
        )
    return hasil


def _baca_kejadian(sesi: Session, batas: int = 50) -> list[WorkerEventOut]:
    """Ambil riwayat kejadian worker terbaru (terbaru lebih dulu)."""
    return [
        WorkerEventOut(
            id=baris.id,
            worker_id=baris.worker_id,
            run_id=baris.run_id,
            level=baris.level,
            jenis=baris.jenis,
            pesan=baris.pesan,
            created_at=baris.created_at,
        )
        for baris in sesi.scalars(
            select(WorkerEvent).order_by(WorkerEvent.id.desc()).limit(batas)
        )
    ]


def _waktu_status(nilai: object) -> datetime | None:
    """Ubah timestamp ISO-8601 UTC dari status backup menjadi datetime naive."""
    if not isinstance(nilai, str) or not nilai.strip():
        return None
    try:
        hasil = datetime.fromisoformat(nilai.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if hasil.tzinfo is not None:
        hasil = hasil.astimezone(UTC).replace(tzinfo=None)
    return hasil


def _baca_backup(setelan: Settings, waktu: datetime) -> BackupOut:
    """Baca berkas status backup; tidak pernah membocorkan path lengkap."""
    if not setelan.backup_status_file:
        return BackupOut()
    jalur = Path(setelan.backup_status_file).expanduser()
    if not jalur.is_file():
        return BackupOut(dikonfigurasi=True, status="belum_ada")
    try:
        data = json.loads(jalur.read_text(encoding="utf-8"))
    except (OSError, ValueError) as galat:
        return BackupOut(
            dikonfigurasi=True,
            file_ada=True,
            status="tidak_valid",
            pesan=f"Berkas status backup tidak dapat dibaca: {galat}",
        )
    if not isinstance(data, dict):
        return BackupOut(
            dikonfigurasi=True,
            file_ada=True,
            status="tidak_valid",
            pesan="Isi berkas status backup bukan objek JSON.",
        )
    nama = data.get("berkas")
    if isinstance(nama, str) and nama:
        nama = Path(nama).name
    else:
        nama = None
    mulai = _waktu_status(data.get("waktu_mulai"))
    selesai = _waktu_status(data.get("waktu_selesai"))
    acuan = selesai or mulai
    ukuran = data.get("ukuran_bytes")
    if not isinstance(ukuran, int) or isinstance(ukuran, bool) or ukuran < 0:
        ukuran = None
    pesan = data.get("pesan")
    return BackupOut(
        dikonfigurasi=True,
        file_ada=True,
        status=str(data.get("status") or "tidak_valid"),
        waktu_mulai=mulai,
        waktu_selesai=selesai,
        berkas=nama,
        ukuran_bytes=ukuran,
        pesan=str(pesan)[:1000] if pesan else None,
        umur_jam=round((waktu - acuan).total_seconds() / 3600, 1)
        if acuan is not None
        else None,
    )


def _susun_peringatan(
    *,
    worker: WorkerOut,
    antrean: AntreanOut,
    job_aktif: list[JobSistemOut],
    memori: MemoriOut,
    disk: DiskOut,
    setelan: Settings,
    heartbeats: list[WorkerHeartbeatOut],
    backup: BackupOut,
) -> list[str]:
    """Buat peringatan yang langsung bisa ditindaklanjuti admin."""
    peringatan: list[str] = []
    if not worker.aktif and antrean.menunggu > 0:
        peringatan.append(
            f"{antrean.menunggu} job menunggu, tetapi worker tidak aktif."
        )
    if not worker.aktif and antrean.jalan > 0:
        peringatan.append(
            f"{antrean.jalan} job berstatus jalan tanpa proses worker."
        )
    if worker.aktif and worker.pid is None:
        peringatan.append(
            "Kunci worker dipegang, tetapi PID worker tidak dapat dibaca. "
            "Jalankan ulang service worker dengan versi ini agar PID ditulis."
        )

    batas_detik = setelan.job_timeout_menit * 60
    for job in job_aktif:
        umur = job.umur_heartbeat_detik
        if umur is not None and umur > batas_detik:
            peringatan.append(
                f"Job {job.id}: heartbeat {umur} detik, melewati batas "
                f"{setelan.job_timeout_menit} menit."
            )

    if (
        worker.rss_mb is not None
        and setelan.worker_mem_budget_mb > 0
        and worker.rss_mb > setelan.worker_mem_budget_mb
    ):
        peringatan.append(
            f"RAM worker {worker.rss_mb:.0f} MB melebihi anggaran "
            f"{setelan.worker_mem_budget_mb} MB."
        )
    if (
        memori.tersedia_mb is not None
        and memori.tersedia_mb < _MIN_RAM_SERVER_MB
    ):
        peringatan.append(
            f"RAM server tersedia {memori.tersedia_mb:.0f} MB; segera kosongkan "
            "proses atau tambah memori."
        )
    if disk.tersedia_mb is not None and disk.tersedia_mb < _MIN_DISK_MB:
        peringatan.append(
            f"Disk tersedia {disk.tersedia_mb:.0f} MB; unggahan baru bisa gagal."
        )

    aktif_heartbeat = [baris for baris in heartbeats if baris.aktif]
    if worker.aktif and not aktif_heartbeat:
        peringatan.append(
            "Kunci worker dipegang, tetapi belum ada heartbeat worker. "
            "Jalankan ulang service setelah migrasi 0009."
        )
    if not worker.aktif and aktif_heartbeat:
        peringatan.append(
            "Heartbeat worker masih aktif, tetapi kunci worker tidak dipegang; "
            "periksa proses worker yang mungkin menggantung."
        )

    if backup.dikonfigurasi:
        if not backup.file_ada:
            peringatan.append(
                "Status backup belum tersedia. Pastikan cron backup berjalan."
            )
        elif backup.status == "gagal":
            peringatan.append(
                f"Backup terakhir gagal: {backup.pesan or 'tanpa pesan'}."
            )
        elif backup.status == "mulai" and (
            backup.umur_jam is None or backup.umur_jam > 2
        ):
            peringatan.append(
                "Backup berstatus mulai lebih dari 2 jam; proses mungkin macet."
            )
        elif backup.status == "sukses" and (
            backup.umur_jam is None or backup.umur_jam > 26
        ):
            peringatan.append(
                "Backup sukses terakhir lebih dari 26 jam lalu; periksa cron."
            )
        elif backup.status not in ("sukses", "mulai", "belum_ada"):
            peringatan.append(
                f"Status backup tidak dikenali: {backup.status}."
            )
    return peringatan


@router.get("/sistem/status", response_model=SistemStatusOut)
def status_sistem(
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> SistemStatusOut:
    """Status worker, antrean, RAM, CPU, dan disk untuk admin provinsi."""
    auth.pastikan_peran(pengguna, PERAN_ADMIN_PROVINSI)

    waktu = sekarang()
    aktif, pid = _status_worker(setelan)
    worker = WorkerOut(
        aktif=aktif,
        pid=pid,
        rss_mb=_rss_proses(pid) if aktif else None,
        batas_memori_mb=setelan.worker_mem_budget_mb,
        jumlah_proses=1 if aktif else 0,
    )
    antrean, job_aktif, job_terakhir = _ambil_antrean(sesi, waktu)
    heartbeats = _baca_heartbeat(sesi, waktu, setelan)
    kejadian = _baca_kejadian(sesi)
    backup = _baca_backup(setelan, waktu)
    if aktif:
        worker.jumlah_proses = max(1, sum(1 for baris in heartbeats if baris.aktif))
    memori = _baca_memori()
    memori.api_rss_mb = _rss_proses(os.getpid())
    memori.worker_rss_mb = worker.rss_mb
    load_1, load_5, load_15 = _baca_load()
    disk = _baca_disk(setelan)
    sistem = SistemOut(
        hostname=socket.gethostname(),
        cpu=os.cpu_count(),
        load_1=load_1,
        load_5=load_5,
        load_15=load_15,
        memori=memori,
        disk=disk,
    )
    peringatan = _susun_peringatan(
        worker=worker,
        antrean=antrean,
        job_aktif=job_aktif,
        memori=memori,
        disk=disk,
        setelan=setelan,
        heartbeats=heartbeats,
        backup=backup,
    )
    return SistemStatusOut(
        waktu=waktu,
        sistem=sistem,
        worker=worker,
        konfigurasi=KonfigurasiWorkerOut(
            poll_detik=setelan.worker_poll_detik,
            heartbeat_detik=setelan.worker_heartbeat_detik,
            timeout_menit=setelan.job_timeout_menit,
            chunk_titik=setelan.proses_chunk_titik,
            max_workers=setelan.max_workers,
        ),
        antrean=antrean,
        job_aktif=job_aktif,
        job_terakhir=job_terakhir,
        heartbeats=heartbeats,
        kejadian=kejadian,
        backup=backup,
        peringatan=peringatan,
    )
