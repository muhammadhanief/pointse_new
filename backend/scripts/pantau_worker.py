"""Pantau status worker Proses A/B langsung dari terminal.

Skrip ini hanya **membaca** basis data, daftar proses, dan log worker; tidak
mengubah data. Cocok dipakai di server AlmaLinux supaya operator tidak perlu
menjalankan query/``ps``/``journalctl`` berulang kali.

Contoh dari folder ``backend``::

    .venv/bin/python scripts/pantau_worker.py
    .venv/bin/python scripts/pantau_worker.py --sekali
    .venv/bin/python scripts/pantau_worker.py --interval 5
    .venv/bin/python scripts/pantau_worker.py --job 7 --sekali

Tekan ``Ctrl-C`` untuk berhenti. Tanpa ``--log``, skrip menebak lokasi log dari
folder induk ``DIR_UNGGAHAN``; log utama service ada di
``journalctl -u pointse-worker``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

AKAR_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR_BACKEND))

from app.config import Settings, get_settings  # noqa: E402
from app.db import get_sessionmaker  # noqa: E402
from app.kunci import KunciBerkas, jalur_kunci  # noqa: E402
from app.models import (  # noqa: E402
    STATUS_GAGAL,
    STATUS_JALAN,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    Run,
    sekarang,
)

#: Warna ANSI sederhana.
MERAH = "31"
KUNING = "33"
HIJAU = "32"
CYAN = "36"


@dataclass(frozen=True)
class ProsesWorker:
    """Satu baris proses ``app.worker`` dari keluaran ``ps``."""

    pid: int
    etime: str
    cpu: str
    mem: str
    rss_mb: float | None
    args: str


def warna(teks: str, kode: str, aktif: bool) -> str:
    """Bungkus ``teks`` dengan kode warna ANSI bila ``aktif``."""
    return f"\033[{kode}m{teks}\033[0m" if aktif else teks


def format_durasi(delta: timedelta | None) -> str:
    """Durasi ringkas untuk tampilan, mis. ``4m 12s`` atau ``1j 02m``."""
    if delta is None:
        return "-"
    detik = max(0, int(delta.total_seconds()))
    jam, sisa = divmod(detik, 3600)
    menit, detik = divmod(sisa, 60)
    if jam:
        return f"{jam}j {menit:02d}m"
    if menit:
        return f"{menit}m {detik:02d}s"
    return f"{detik}s"


def format_angka(nilai: int | None) -> str:
    """Angka ribuan dengan titik (gaya Indonesia); ``-`` kalau kosong."""
    if nilai is None:
        return "-"
    return f"{nilai:,}".replace(",", ".")


def waktu_lokal(nilai: datetime | None, pola: str = "%d %b %H:%M:%S") -> str:
    """Waktu UTC dari basis data ditampilkan di zona waktu server."""
    if nilai is None:
        return "-"
    return nilai.replace(tzinfo=UTC).astimezone().strftime(pola)


def urai_baris_ps(keluaran: str) -> list[ProsesWorker]:
    """Saring keluaran ``ps`` menjadi daftar proses ``app.worker``.

    Format masukan: ``pid etime cpu mem rss args`` (lihat :func:`cari_proses_worker`).
    Proses skrip pemantau sendiri dan perintah lain yang menyebut ``app.worker``
    di luar nama proses tidak diikutkan.
    """
    hasil: list[ProsesWorker] = []
    for baris in keluaran.splitlines():
        bagian = baris.split(None, 5)
        if len(bagian) < 6:
            continue
        pid, etime, cpu, mem, rss, args = bagian
        if "app.worker" not in args or "pantau_worker" in args:
            continue
        # Hanya proses Python; baris seperti ``grep app.worker`` bukan worker.
        if not Path(args.split()[0]).name.lower().startswith("python"):
            continue
        try:
            nomor_pid = int(pid)
        except ValueError:
            continue
        try:
            rss_mb = float(rss) / 1024
        except ValueError:
            rss_mb = None
        hasil.append(
            ProsesWorker(
                pid=nomor_pid,
                etime=etime,
                cpu=cpu,
                mem=mem,
                rss_mb=rss_mb,
                args=args,
            )
        )
    return hasil


def cari_proses_worker() -> list[ProsesWorker]:
    """Cari proses ``python -m app.worker`` lewat ``ps`` (kosong di Windows)."""
    if shutil.which("ps") is None:
        return []
    perintah = ["ps", "-eww", "-o", "pid=,etime=,pcpu=,pmem=,rss=,args="]
    try:
        keluaran = subprocess.run(
            perintah,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return urai_baris_ps(keluaran.stdout)


def baca_ekor(berkas: Path, jumlah: int, maks_byte: int = 256 * 1024) -> list[str]:
    """Baca ``jumlah`` baris terakhir berkas log tanpa memuat seluruhnya."""
    if jumlah <= 0 or not berkas.is_file():
        return []
    with berkas.open("rb") as berkas_isi:
        berkas_isi.seek(0, 2)
        ukuran = berkas_isi.tell()
        mulai = max(0, ukuran - maks_byte)
        berkas_isi.seek(mulai)
        data = berkas_isi.read()
    baris = data.decode("utf-8", errors="replace").splitlines()
    if mulai > 0 and baris:
        # Baris pertama bisa terpotong; buang supaya tidak menyesatkan.
        baris = baris[1:]
    return baris[-jumlah:]


def ambil_status(
    sesi: Session,
) -> tuple[list[Run], dict[str, int], list[Run]]:
    """Ambil job aktif/antre, hitungan per status, dan beberapa job terakhir."""
    aktif = list(
        sesi.scalars(
            select(Run)
            .where(Run.status.in_([STATUS_JALAN, STATUS_MENUNGGU]))
            .order_by(Run.id)
        )
    )
    hitungan = {
        str(status): int(jumlah)
        for status, jumlah in sesi.execute(
            select(Run.status, func.count()).group_by(Run.status)
        )
    }
    selesai = list(
        sesi.scalars(
            select(Run)
            .where(Run.status.in_([STATUS_SUKSES, STATUS_GAGAL]))
            .order_by(Run.id.desc())
            .limit(3)
        )
    )
    return aktif, hitungan, selesai


def kunci_worker(
    sesi: Session, setelan: Settings | None = None
) -> str | None:
    """Jalur berkas flock yang dipegang worker, atau ``None`` bila bebas.

    Di SQLite/tes pemeriksaan dilewati karena tidak ada worker produksi.
    """
    if sesi.get_bind().dialect.name not in ("mysql", "mariadb"):
        return None
    setelan = setelan or get_settings()
    jalur = jalur_kunci(setelan)
    kunci = KunciBerkas(jalur)
    if kunci.ambil():
        kunci.lepas()
        return None
    return str(jalur)


def umur_heartbeat(run: Run) -> timedelta | None:
    """Selisih waktu sekarang dengan heartbeat/start job (UTC)."""
    acuan = run.heartbeat_at or run.started_at or run.created_at
    return None if acuan is None else sekarang() - acuan


def tampilkan(
    setelan: Settings,
    sesi: Session,
    *,
    log_path: Path,
    baris_log: int,
    pakai_warna: bool,
    batas_heartbeat: int,
    batas_mandek: int,
    hanya_job: int | None,
    riwayat: dict[int, tuple[int, float]],
) -> dict[int, tuple[int, float]]:
    """Cetak satu layar pantauan; kembalikan riwayat progres yang diperbarui."""
    aktif, hitungan, selesai = ambil_status(sesi)
    if hanya_job is not None:
        aktif = [run for run in aktif if run.id == hanya_job]
        selesai = [run for run in selesai if run.id == hanya_job]
        if not aktif and not selesai:
            # Job lama yang tidak masuk 3 job terakhir tetap bisa dipantau.
            satu = sesi.get(Run, hanya_job)
            if satu is not None:
                if satu.status in (STATUS_JALAN, STATUS_MENUNGGU):
                    aktif = [satu]
                else:
                    selesai = [satu]
    proses = cari_proses_worker()
    kunci = kunci_worker(sesi)

    sekarang_lokal = datetime.now().astimezone()
    print("=" * 100)
    print(
        f"POINTSE | PANTAU WORKER  |  {sekarang_lokal:%d %b %Y %H:%M:%S %Z}  |  "
        f"DB {setelan.db_name}@{setelan.db_host}"
    )
    print(f"Log worker: {log_path}")
    print("=" * 100)

    # --- Job aktif dan antre ---
    print("\nJOB AKTIF / ANTRE")
    if aktif:
        print(
            f"  {'id':>4}  {'tipe':<4} {'wilayah':<8} {'status':<9} "
            f"{'mulai':<9} {'heartbeat':<9} {'umur':<8} {'baris':>10}  pesan"
        )
        print("  " + "-" * 96)
        for run in aktif:
            umur = umur_heartbeat(run) if run.status == STATUS_JALAN else None
            status = warna(
                f"{run.status:<9}",
                KUNING if run.status == STATUS_JALAN else CYAN,
                pakai_warna,
            )
            print(
                f"  {run.id:>4}  {run.tipe:<4} {run.kdprov}/{run.kdkab:<5} {status} "
                f"{waktu_lokal(run.started_at, '%H:%M:%S'):<9} "
                f"{waktu_lokal(run.heartbeat_at, '%H:%M:%S'):<9} "
                f"{format_durasi(umur):<8} {format_angka(run.jumlah_baris):>10}  "
                f"{(run.pesan or '')[:40]}"
            )
    else:
        print("  (tidak ada job menunggu/jalan)")

    # --- Job terakhir yang sudah selesai ---
    if selesai:
        print("\nJOB TERAKHIR SELESAI")
        for run in selesai:
            status = warna(
                f"{run.status:<9}",
                HIJAU if run.status == STATUS_SUKSES else MERAH,
                pakai_warna,
            )
            print(
                f"  {run.id:>4}  {run.tipe:<4} {run.kdprov}/{run.kdkab:<5} {status} "
                f"selesai {waktu_lokal(run.finished_at)}  "
                f"baris {format_angka(run.jumlah_baris)}  "
                f"tanpa wilayah {format_angka(run.jumlah_tanpa_wilayah)}"
            )

    # --- Proses worker ---
    print("\nPROSES WORKER")
    if proses:
        for satu in proses:
            rss = "-" if satu.rss_mb is None else f"{satu.rss_mb:,.0f} MB"
            print(
                f"  PID {satu.pid:<8} etime {satu.etime:<10} CPU {satu.cpu:>5}%  "
                f"RSS {rss:<10} {satu.args}"
            )
    else:
        print("  (tidak ada proses app.worker)")
    print(
        "  flock worker: "
        + (f"dipegang ({kunci})" if kunci is not None else "tidak dipegang")
    )

    # --- Peringatan ---
    peringatan: list[tuple[str, str]] = []
    ada_jalan = [run for run in aktif if run.status == STATUS_JALAN]
    for run in ada_jalan:
        umur = umur_heartbeat(run)
        if umur is not None and umur > timedelta(minutes=setelan.job_timeout_menit):
            peringatan.append(
                (
                    MERAH,
                    f"job {run.id}: heartbeat {format_durasi(umur)} > "
                    f"JOB_TIMEOUT_MENIT={setelan.job_timeout_menit}; akan ditandai gagal",
                )
            )
        elif umur is not None and umur > timedelta(seconds=batas_heartbeat):
            peringatan.append(
                (
                    KUNING,
                    f"job {run.id}: heartbeat {format_durasi(umur)}; "
                    "tunggu batch berikutnya, jangan buka worker kedua",
                )
            )
        if not proses and kunci is None:
            peringatan.append(
                (
                    MERAH,
                    f"job {run.id}: status jalan tetapi tidak ada proses worker "
                    "maupun flock",
                )
            )
    if proses and not ada_jalan:
        peringatan.append(
            (CYAN, "proses worker hidup tetapi belum ada job berstatus jalan")
        )
    if not proses and kunci is not None:
        peringatan.append(
            (
                KUNING,
                "flock masih dipegang tetapi proses worker tidak terlihat "
                "(bisa jadi proses milik pengguna lain)",
            )
        )

    # --- Progres baris tersimpan ---
    id_aktif = {run.id for run in ada_jalan}
    for run in ada_jalan:
        baris_kini = int(run.jumlah_baris or 0)
        lama = riwayat.get(run.id)
        if lama is None:
            riwayat[run.id] = (baris_kini, time.monotonic())
            continue
        baris_lama, waktu_lama = lama
        jeda = timedelta(seconds=time.monotonic() - waktu_lama)
        if baris_kini > baris_lama:
            peringatan.append(
                (
                    HIJAU,
                    f"job {run.id}: +{format_angka(baris_kini - baris_lama)} baris "
                    f"dalam {format_durasi(jeda)}",
                )
            )
            riwayat[run.id] = (baris_kini, time.monotonic())
        elif time.monotonic() - waktu_lama > batas_mandek:
            peringatan.append(
                (
                    KUNING,
                    f"job {run.id}: baris tersimpan tidak bertambah selama "
                    f"{format_durasi(jeda)} (proses masih hidup: "
                    f"{'ya' if proses else 'tidak'})",
                )
            )
    for nomor in list(riwayat):
        if nomor not in id_aktif:
            del riwayat[nomor]

    print("\nSTATUS")
    if peringatan:
        for kode, pesan in peringatan:
            print("  " + warna("[!] " + pesan, kode, pakai_warna))
    else:
        print("  " + warna("[ok] tidak ada peringatan", HIJAU, pakai_warna))
    print(
        "  antre: "
        f"menunggu={hitungan.get(STATUS_MENUNGGU, 0)}  "
        f"jalan={hitungan.get(STATUS_JALAN, 0)}  "
        f"sukses={hitungan.get(STATUS_SUKSES, 0)}  "
        f"gagal={hitungan.get(STATUS_GAGAL, 0)}"
    )

    # --- Log terakhir ---
    if baris_log > 0:
        print(f"\nLOG TERAKHIR ({log_path})")
        ekor = baca_ekor(log_path, baris_log)
        if ekor:
            for baris in ekor:
                print("  " + baris[:160])
        else:
            print("  (log kosong atau belum ada)")

    print("=" * 100)
    return riwayat


def main(argv: list[str] | None = None) -> int:
    """Baca argumen lalu jalankan pemantauan (berulang sampai Ctrl-C)."""
    parser = argparse.ArgumentParser(
        prog="python scripts/pantau_worker.py",
        description="Pantau job worker Proses A/B tanpa query/ps/tail manual.",
    )
    parser.add_argument(
        "--sekali",
        action="store_true",
        help="cetak sekali lalu keluar (tanpa refresh)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="jeda refresh dalam detik (default 5)",
    )
    parser.add_argument("--job", type=int, default=None, help="hanya tampilkan job id ini")
    parser.add_argument("--log", type=Path, default=None, help="path berkas worker.log")
    parser.add_argument(
        "--baris-log",
        type=int,
        default=8,
        help="jumlah baris log terakhir yang ditampilkan (0 = nonaktif)",
    )
    parser.add_argument(
        "--tanpa-warna",
        action="store_true",
        help="matikan warna ANSI (otomatis saat output bukan terminal)",
    )
    parser.add_argument(
        "--batas-heartbeat",
        type=int,
        default=120,
        help="detik sebelum heartbeat dianggap lambat (default 120)",
    )
    parser.add_argument(
        "--batas-mandek",
        type=int,
        default=300,
        help="detik tanpa penambahan baris sebelum diperingatkan (default 300)",
    )
    argumen = parser.parse_args(argv)

    setelan = get_settings()
    log_path = (
        argumen.log
        if argumen.log is not None
        else Path(setelan.dir_unggahan).resolve().parent / "worker.log"
    )
    pakai_warna = not argumen.tanpa_warna and sys.stdout.isatty()
    riwayat: dict[int, tuple[int, float]] = {}

    try:
        while True:
            if not argumen.sekali and sys.stdout.isatty():
                print("\033[H\033[J", end="")
            try:
                with get_sessionmaker()() as sesi:
                    riwayat = tampilkan(
                        setelan,
                        sesi,
                        log_path=log_path,
                        baris_log=max(0, argumen.baris_log),
                        pakai_warna=pakai_warna,
                        batas_heartbeat=argumen.batas_heartbeat,
                        batas_mandek=argumen.batas_mandek,
                        hanya_job=argumen.job,
                        riwayat=riwayat,
                    )
            except SQLAlchemyError as galat:
                print(f"gagal membaca basis data: {galat}")
            if argumen.sekali:
                break
            time.sleep(max(1.0, argumen.interval))
    except KeyboardInterrupt:
        print("\nberhenti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
