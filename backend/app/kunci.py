"""Kunci berkas (``fcntl.flock``) untuk satu proses worker.

Produksi AlmaLinux memakai ``fcntl.flock`` agar dua worker (service dan
``--once`` manual) tidak mengambil job bersamaan. Di Windows (lingkungan tes)
dipakai ``msvcrt.locking`` sebagai padanan agar tes tetap dapat dijalankan.

PID pemegang kunci ditulis ke berkas ``<lock>.pid`` untuk halaman Status Sistem;
keaktifan worker tetap ditentukan oleh ``flock``, bukan berkas PID tersebut.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]

from app.config import Settings


class KunciDipegang(RuntimeError):
    """Kunci worker sudah dipegang proses lain."""


def jalur_kunci(setelan: Settings) -> Path:
    """Lokasi berkas kunci worker.

    Nilai ``WORKER_LOCK_FILE`` dipakai bila diisi; kalau tidak, berkas berada di
    induk ``DIR_UNGGAHAN`` supaya tetap di luar folder unggahan.
    """
    if setelan.worker_lock_file.strip():
        return Path(setelan.worker_lock_file).expanduser()
    return Path(setelan.dir_unggahan).expanduser().parent / "worker.lock"


def jalur_pid_kunci(jalur: Path) -> Path:
    """Berkas PID di samping berkas kunci.

    Dipisah dari berkas kunci karena di Windows byte yang dikunci ``msvcrt``
    tidak bisa dibaca proses lain. Berkas ini hanya petunjuk pemantauan.
    """
    return jalur.with_name(f"{jalur.name}.pid")


class KunciBerkas:
    """Kunci eksklusif nonblocking untuk worker/pemantau status."""

    def __init__(self, jalur: Path) -> None:
        self.jalur = jalur
        self._berkas: BinaryIO | None = None

    def ambil(self, *, tulis_pid: bool = True) -> bool:
        """Coba ambil kunci; ``False`` bila sudah dipegang proses lain.

        ``tulis_pid=False`` dipakai pemantau yang hanya ingin memeriksa kunci,
        supaya PID proses API tidak sempat tampil sebagai PID worker.
        """
        self.jalur.parent.mkdir(parents=True, exist_ok=True)
        berkas = self.jalur.open("a+b")
        try:
            if fcntl is not None:
                fcntl.flock(berkas.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt is not None:  # pragma: no cover - Windows
                berkas.seek(0)
                msvcrt.locking(berkas.fileno(), msvcrt.LK_NBLCK, 1)
            self._berkas = berkas
            if tulis_pid:
                self._tulis_pid()
            return True
        except OSError:
            berkas.close()
            return False

    def _tulis_pid(self) -> None:
        """Simpan PID pemegang kunci di berkas ``.pid`` untuk pemantauan.

        Berkas PID bukan bagian dari mekanisme kunci; kegagalan menulisnya
        diabaikan agar worker tetap bisa berjalan.
        """
        try:
            jalur_pid_kunci(self.jalur).write_text(
                f"{os.getpid()}\n", encoding="ascii"
            )
        except OSError:
            pass

    def lepas(self) -> None:
        """Lepas kunci; aman dipanggil bila kunci tidak dipegang."""
        berkas = self._berkas
        if berkas is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(berkas.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows
                berkas.seek(0)
                msvcrt.locking(berkas.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            # Hapus PID sebelum kunci dilepas agar worker baru tidak sempat
            # menulis PID lalu dihapus oleh pemilik lama.
            try:
                jalur_pid_kunci(self.jalur).unlink()
            except OSError:
                pass
            berkas.close()
            self._berkas = None

    def __enter__(self) -> "KunciBerkas":
        if not self.ambil():
            raise KunciDipegang(str(self.jalur))
        return self

    def __exit__(self, *_args: object) -> None:
        self.lepas()


def baca_pid_kunci(jalur: Path) -> int | None:
    """Baca PID pemegang kunci terakhir dari berkas ``.pid``.

    Nilai ini hanya petunjuk untuk pemantauan; keaktifan worker tetap ditentukan
    oleh berhasil/tidaknya ``flock``. PID lama bisa tertinggal setelah worker
    berhenti, jadi pemanggil harus memeriksa kunci terlebih dahulu.
    """
    for sumber in (jalur_pid_kunci(jalur), jalur):
        try:
            isi = sumber.read_text(encoding="ascii", errors="ignore").strip()
        except OSError:
            continue
        baris = isi.splitlines()
        if not baris:
            continue
        try:
            return int(baris[0].strip())
        except ValueError:
            continue
    return None
