"""Isi ulang snapshot ``rekap_subsls`` untuk run A/B terakhir per kabupaten/kota.

Tabel ``rekap_subsls`` (level 6/SubSLS) baru ada setelah banyak run diproses,
jadi run lama tidak punya snapshot dan tabulasi progres per level 6 kosong.
Skrip ini memproses ulang **berkas mentah yang masih tersimpan** untuk run
Proses A sukses terbaru dan run Proses B sukses terbaru setelahnya. Yang
dipertahankan: ``runs.id``, ``runs.tanggal_data``, dan berkas masukan; yang
dihitung ulang: ``titik_hasil``, rekap, dan snapshot level 6.

Urutan wajib A lalu B per kabupaten/kota supaya target B mengikuti A terbaru.

Contoh (dari folder ``backend``)::

    .venv/bin/python scripts/backfill_rekap_subsls.py --dry-run
    .venv/bin/python scripts/backfill_rekap_subsls.py --dry-run --kabupaten 3303

    sudo systemctl stop pointse-worker
    .venv/bin/python scripts/backfill_rekap_subsls.py --kabupaten 3303 --jalankan
    sudo systemctl start pointse-worker

Di server, jalankan sebagai ``pointse`` dan beri ``--env-file`` (jangan
``source`` berkas env di bash: tanda kutip di nilai JSON ikut terbuang)::

    sudo -u pointse .venv/bin/python scripts/backfill_rekap_subsls.py \\
        --env-file /etc/pointse/pointse.env --dry-run --kabupaten 3303

Syarat saat ``--jalankan``:

- cadangkan basis data dan folder unggahan lebih dulu (``deploy/backup.sh``);
  kalau pemrosesan ulang gagal, hasil lama run itu sudah terhapus;
- kunci worker (``worker.lock``) bebas, artinya service worker sudah berhenti;
- tidak ada job lain berstatus ``menunggu``, supaya run yang diproses ulang
  pasti run yang dipilih (bukan job antrean milik pengguna);
- berkas masukan run masih ada di disk (run yang berkasnya sudah dipangkas
  dilewati dan dilaporkan, tidak bisa dibangun ulang).

Skrip ini memakai jalur pemrosesan worker yang sama (``app.worker``), jadi
anggaran memori ``WORKER_MEM_BUDGET_MB`` tetap berlaku.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

AKAR_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR_BACKEND))

from app.config import Settings, get_settings  # noqa: E402
from app.db import get_sessionmaker  # noqa: E402
from app.kunci import KunciBerkas, jalur_kunci  # noqa: E402
from app.models import (  # noqa: E402
    DASAR_POSISI,
    DASAR_TUGAS,
    STATUS_MENUNGGU,
    STATUS_SUKSES,
    TIPE_A,
    TIPE_B,
    RekapKabupaten,
    RekapSubsls,
    Run,
    Wilayah,
)

#: Dua dasar rekap; snapshot diisi untuk keduanya.
DASAR: tuple[str, ...] = (DASAR_TUGAS, DASAR_POSISI)


def muat_env(jalur: str) -> None:
    """Muat berkas environment (``/etc/pointse/pointse.env``) tanpa merusak JSON.

    ``source berkas.env`` di bash membuang tanda kutip di dalam nilai, sehingga
    ``CORS_ORIGINS=["https://..."]`` menjadi ``[https://...]`` dan ditolak
    pydantic-settings. ``python-dotenv`` hanya membuang kutip bila seluruh nilai
    dikutip, jadi JSON tetap utuh. Variabel yang sudah ada tidak ditimpa.
    """
    from dotenv import dotenv_values

    for kunci, nilai in dotenv_values(jalur).items():
        if nilai is not None and kunci not in os.environ:
            os.environ[kunci] = nilai


def kode_kabupaten(run: Run) -> str:
    """Kode kabupaten/kota 4 digit dari satu run (peta bisa menyimpan 2 digit)."""
    kode = str(run.kdkab).strip()
    if len(kode) == 2:
        return f"{run.kdprov}{kode}"
    return kode


def _kandidat_kode(kdprov: str, kdkab: str) -> list[str]:
    """Kode ``kdkab`` yang mungkin tersimpan di ``runs`` (2 atau 4 digit)."""
    kode = str(kdkab).strip()
    kandidat = {kode}
    if len(kode) == 4 and kode.startswith(kdprov):
        kandidat.add(kode[2:])
    return sorted(kandidat)


def pilih_run(
    sesi: Session, kdprov: str, kdkab: str
) -> tuple[Run | None, Run | None]:
    """Run A sukses terbaru dan run B sukses terbaru setelah A (aturan tabulasi)."""
    kandidat = _kandidat_kode(kdprov, kdkab)
    run_a = sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_A,
            Run.status == STATUS_SUKSES,
            Run.kdprov == kdprov,
            Run.kdkab.in_(kandidat),
        )
        .order_by(Run.id.desc())
        .limit(1)
    ).first()
    if run_a is None:
        return None, None
    run_b = sesi.scalars(
        select(Run)
        .where(
            Run.tipe == TIPE_B,
            Run.status == STATUS_SUKSES,
            Run.kdprov == kdprov,
            Run.kdkab.in_(kandidat),
            Run.id > run_a.id,
            or_(Run.sumber_run_a_id.is_(None), Run.sumber_run_a_id == run_a.id),
        )
        .order_by(Run.id.desc())
        .limit(1)
    ).first()
    return run_a, run_b


def jumlah_snapshot(sesi: Session, run_id: int) -> int:
    """Jumlah baris ``rekap_subsls`` satu run (semua dasar)."""
    return int(
        sesi.scalar(
            select(func.count())
            .select_from(RekapSubsls)
            .where(RekapSubsls.run_id == run_id)
        )
        or 0
    )


def berkas_hilang(run: Run) -> list[str]:
    """Berkas masukan run yang sudah tidak ada di disk."""
    hilang: list[str] = []
    for jalur in (run.berkas_input, run.berkas_peta):
        if not jalur:
            hilang.append("(kosong)")
        elif not Path(jalur).is_file():
            hilang.append(jalur)
    return hilang


def nama_kabupaten(sesi: Session, kdprov: str, kdkab: str) -> str | None:
    """Nama kabupaten/kota dari tabel ``wilayah`` (bila ada)."""
    return sesi.scalars(
        select(Wilayah.nmkab)
        .where(
            Wilayah.kdprov == kdprov,
            Wilayah.kdkab.in_(_kandidat_kode(kdprov, kdkab)),
            Wilayah.nmkab.is_not(None),
        )
        .limit(1)
    ).first()


@dataclass
class Rencana:
    """Satu kabupaten/kota yang akan (atau tidak) diproses ulang."""

    kdprov: str
    kdkab: str
    nmkab: str | None
    run_a: Run | None
    run_b: Run | None
    snapshot_a: int = 0
    snapshot_b: int = 0
    hilang_a: list[str] = field(default_factory=list)
    hilang_b: list[str] = field(default_factory=list)
    lewat: str | None = None

    @property
    def diproses(self) -> bool:
        """True kalau kabupaten/kota ini masuk daftar pemrosesan ulang."""
        return self.lewat is None

    @property
    def urutan(self) -> list[Run]:
        """Run yang diproses berurutan: A dulu, lalu B."""
        return [run for run in (self.run_a, self.run_b) if run is not None]


def _kode_filter(kode: str) -> str:
    """Normalisasi argumen ``--kabupaten`` (2 digit dilengkapi provinsi 33)."""
    bersih = kode.strip()
    if not bersih:
        raise ValueError("kode kabupaten kosong")
    if len(bersih) == 2:
        return f"33{bersih}"
    return bersih


def daftar_kabupaten(sesi: Session) -> list[tuple[str, str]]:
    """Semua (kdprov, kdkab 4 digit) yang punya run sukses, unik dan terurut."""
    pasangan: set[tuple[str, str]] = set()
    for kdprov, kdkab in sesi.execute(
        select(Run.kdprov, Run.kdkab)
        .where(Run.status == STATUS_SUKSES)
        .distinct()
    ):
        kode = str(kdkab).strip()
        if len(kode) == 2:
            kode = f"{kdprov}{kode}"
        pasangan.add((str(kdprov), kode))
    return sorted(pasangan)


def susun_rencana(
    sesi: Session,
    *,
    kabupaten: list[str] | None = None,
    paksa: bool = False,
) -> list[Rencana]:
    """Tentukan A/B terakhir per kabupaten/kota dan alasan dilewati.

    ``paksa`` memproses ulang walau snapshot level 6 sudah ada (mis. setelah
    perbaikan rumus). Tanpa ``paksa``, run yang snapshotnya lengkap dilewati.
    """
    saring = {_kode_filter(kode) for kode in kabupaten} if kabupaten else None
    hasil: list[Rencana] = []
    for kdprov, kdkab in daftar_kabupaten(sesi):
        if saring is not None and kdkab not in saring:
            continue
        run_a, run_b = pilih_run(sesi, kdprov, kdkab)
        rencana = Rencana(
            kdprov=kdprov,
            kdkab=kdkab,
            nmkab=nama_kabupaten(sesi, kdprov, kdkab),
            run_a=run_a,
            run_b=run_b,
        )
        if run_a is None:
            rencana.lewat = "tidak ada run Proses A sukses"
            hasil.append(rencana)
            continue
        rencana.snapshot_a = jumlah_snapshot(sesi, run_a.id)
        rencana.hilang_a = berkas_hilang(run_a)
        if run_b is not None:
            rencana.snapshot_b = jumlah_snapshot(sesi, run_b.id)
            rencana.hilang_b = berkas_hilang(run_b)
        if rencana.hilang_a or rencana.hilang_b:
            rencana.lewat = "berkas mentah sudah dipangkas"
        elif run_b is not None and rencana.snapshot_b == 0:
            rencana.lewat = None
        elif rencana.snapshot_a == 0:
            rencana.lewat = None
        elif not paksa:
            rencana.lewat = "snapshot level 6 sudah ada"
        hasil.append(rencana)
    return hasil


def _tanggal(nilai: date | None) -> str:
    """Tanggal ringkas untuk laporan terminal."""
    return nilai.isoformat() if nilai is not None else "-"


def format_rencana(rencana: list[Rencana]) -> list[str]:
    """Baris laporan rencana backfill (aman dicetak ke terminal/log)."""
    baris: list[str] = []
    for satu in rencana:
        a = "-" if satu.run_a is None else f"#{satu.run_a.id} ({_tanggal(satu.run_a.tanggal_data)})"
        b = "-" if satu.run_b is None else f"#{satu.run_b.id} ({_tanggal(satu.run_b.tanggal_data)})"
        status = "PROSES" if satu.diproses else f"LEWAT: {satu.lewat}"
        baris.append(
            f"{satu.kdkab} {satu.nmkab or '?':<20} A={a:<22} "
            f"snapshot A={satu.snapshot_a:<6} B={b:<22} snapshot B={satu.snapshot_b:<6} {status}"
        )
        for jalur in satu.hilang_a:
            baris.append(f"    berkas A hilang: {jalur}")
        for jalur in satu.hilang_b:
            baris.append(f"    berkas B hilang: {jalur}")
    return baris


def antrean_lain(sesi: Session, kecuali: int | None = None) -> list[int]:
    """ID job ``menunggu`` selain run yang sedang diproses."""
    kueri = select(Run.id).where(Run.status == STATUS_MENUNGGU)
    if kecuali is not None:
        kueri = kueri.where(Run.id != kecuali)
    return sorted(int(satu) for satu in sesi.scalars(kueri).all())


def proses_ulang(
    sesi_pabrik: sessionmaker[Session], setelan: Settings, run_id: int
) -> Run:
    """Proses ulang satu run di tempat lewat jalur worker, lalu kembalikan run-nya."""
    from app import worker as modul_worker

    with sesi_pabrik() as sesi:
        run = sesi.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"run {run_id} tidak ditemukan")
        if run.status != STATUS_SUKSES:
            raise RuntimeError(f"run {run_id} berstatus {run.status}, bukan sukses")
        lain = antrean_lain(sesi, kecuali=run_id)
        if lain:
            raise RuntimeError(
                f"masih ada job menunggu {lain}; kosongkan antrean sebelum backfill"
            )
        run.status = STATUS_MENUNGGU
        run.started_at = None
        run.heartbeat_at = None
        run.finished_at = None
        run.pesan = None
        sesi.commit()

    if not modul_worker.proses_satu_job(sesi_pabrik, setelan):
        raise RuntimeError(f"run {run_id} tidak terklaim worker")

    with sesi_pabrik() as sesi:
        run = sesi.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"run {run_id} hilang setelah diproses")
        sesi.refresh(run)
        if run.status != STATUS_SUKSES:
            raise RuntimeError(
                f"run {run_id} gagal diproses ulang: {run.status} {run.pesan or ''}".strip()
            )
        return run


@dataclass
class Verifikasi:
    """Hasil pemeriksaan silang rekap kabupaten vs snapshot level 6."""

    dasar: str
    baris: int
    jumlah_sub: int
    belum_sub: int
    jumlah_kab: int
    belum_kab: int

    @property
    def cocok(self) -> bool:
        """Total snapshot level 6 harus sama dengan rekap kabupaten."""
        return (self.jumlah_sub, self.belum_sub) == (self.jumlah_kab, self.belum_kab)


def verifikasi_run(sesi: Session, run: Run) -> list[Verifikasi]:
    """Bandingkan total ``rekap_subsls`` dengan ``rekap_kabupaten`` satu run."""
    hasil: list[Verifikasi] = []
    for dasar in DASAR:
        baris, jumlah_sub, belum_sub = sesi.execute(
            select(
                func.count(),
                func.coalesce(func.sum(RekapSubsls.jumlah), 0),
                func.coalesce(func.sum(RekapSubsls.belum), 0),
            ).where(RekapSubsls.run_id == run.id, RekapSubsls.dasar == dasar)
        ).one()
        jumlah_kab, belum_kab = sesi.execute(
            select(
                func.coalesce(func.sum(RekapKabupaten.jumlah), 0),
                func.coalesce(func.sum(RekapKabupaten.belum), 0),
            ).where(RekapKabupaten.run_id == run.id, RekapKabupaten.dasar == dasar)
        ).one()
        hasil.append(
            Verifikasi(
                dasar=dasar,
                baris=int(baris),
                jumlah_sub=int(jumlah_sub),
                belum_sub=int(belum_sub),
                jumlah_kab=int(jumlah_kab),
                belum_kab=int(belum_kab),
            )
        )
    return hasil


def format_verifikasi(run: Run, hasil: list[Verifikasi]) -> list[str]:
    """Baris laporan verifikasi satu run."""
    baris = [f"  run #{run.id} ({run.tipe}) sukses: {run.jumlah_baris or 0} titik"]
    for satu in hasil:
        tanda = "cocok" if satu.cocok else "TIDAK COCOK"
        baris.append(
            f"    {satu.dasar:<6} snapshot {satu.baris} baris "
            f"(jumlah {satu.jumlah_sub}, belum {satu.belum_sub}) vs "
            f"kabupaten (jumlah {satu.jumlah_kab}, belum {satu.belum_kab}) -> {tanda}"
        )
    return baris


def ringkas_tabulasi(sesi: Session, kdprov: str, kdkab: str) -> list[str]:
    """Ringkasan angka tabulasi yang dipakai UI (target, selesai, status)."""
    from app import layanan

    keluaran: list[str] = []
    data = layanan.tabulasi_progres(
        sesi, kdprov=kdprov, kdkab=kdkab, tingkat="kabupaten", dasar=DASAR_TUGAS
    )
    for satu in data.get("baris", []):
        if str(satu.get("kode")) != kdkab:
            continue
        keluaran.append(
            f"  tabulasi {kdprov}/{kdkab}: target {satu['target']}, "
            f"selesai {satu['selesai']}, sisa {satu['sisa']}, "
            f"persen {satu['persen']}, status {satu['status']}, "
            f"cakupan {satu['cakupan_ada']}/{satu['cakupan_total']} {satu['cakupan_unit']}"
        )
    return keluaran


def _parse_kabupaten(nilai: list[str] | None) -> list[str] | None:
    """Pecah ``--kabupaten 3303,3304`` menjadi daftar kode."""
    if not nilai:
        return None
    kode: list[str] = []
    for satu in nilai:
        kode.extend(bagian for bagian in satu.replace(";", ",").split(",") if bagian.strip())
    return kode or None


def jalankan(
    setelan: Settings | None = None,
    *,
    kabupaten: list[str] | None = None,
    paksa: bool = False,
    sesi_pabrik: sessionmaker[Session] | None = None,
    log: list[str] | None = None,
) -> int:
    """Proses inti backfill (dipakai CLI dan tes). Kembalikan kode keluar."""
    setelan = setelan or get_settings()
    sesi_pabrik = sesi_pabrik or get_sessionmaker()
    laporan = log if log is not None else []

    def tulis(teks: str) -> None:
        laporan.append(teks)
        print(teks, flush=True)

    with sesi_pabrik() as sesi:
        rencana = susun_rencana(sesi, kabupaten=kabupaten, paksa=paksa)
    for teks in format_rencana(rencana):
        tulis(teks)
    target = [satu for satu in rencana if satu.diproses]
    if not target:
        tulis("tidak ada kabupaten/kota yang perlu diproses ulang")
        return 0

    # Pegang kunci worker selama backfill supaya cron ``worker --once`` tidak
    # mengambil job di tengah proses dan snapshot tidak dihitung dua kali.
    kunci = KunciBerkas(jalur_kunci(setelan))
    if not kunci.ambil():
        tulis(
            f"BATAL: kunci worker {jalur_kunci(setelan)} sedang dipegang; "
            "hentikan dulu service worker"
        )
        return 1

    gagal: list[str] = []
    try:
        for satu in target:
            tulis(f"== {satu.kdkab} {satu.nmkab or ''} ==")
            for run in satu.urutan:
                tulis(f"  proses ulang run #{run.id} ({run.tipe}) ...")
                try:
                    hasil = proses_ulang(sesi_pabrik, setelan, run.id)
                    with sesi_pabrik() as sesi:
                        verifikasi = verifikasi_run(sesi, hasil)
                    for teks in format_verifikasi(hasil, verifikasi):
                        tulis(teks)
                    if not all(item.cocok for item in verifikasi):
                        gagal.append(f"{satu.kdkab} run #{run.id}: total tidak cocok")
                except Exception as galat:  # noqa: BLE001 - lanjutkan kabupaten lain
                    gagal.append(f"{satu.kdkab} run #{run.id}: {galat}")
                    tulis(f"  GAGAL run #{run.id}: {galat}")
            with sesi_pabrik() as sesi:
                for teks in ringkas_tabulasi(sesi, satu.kdprov, satu.kdkab):
                    tulis(teks)
    finally:
        kunci.lepas()

    if gagal:
        tulis("selesai dengan kegagalan:")
        for satu in gagal:
            tulis(f"  - {satu}")
        return 2
    tulis("selesai: semua run yang diproses ulang lolos verifikasi")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Titik masuk CLI."""
    parser = argparse.ArgumentParser(
        description="Isi ulang snapshot rekap level 6 (SubSLS) untuk run A/B terakhir."
    )
    parser.add_argument(
        "--env-file",
        help="berkas environment (mis. /etc/pointse/pointse.env) yang dimuat dulu",
    )
    parser.add_argument(
        "--kabupaten",
        action="append",
        help="batasi ke kode kabupaten/kota (4 digit atau 2 digit), boleh diulang",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="hanya tampilkan rencana, tanpa mengubah data",
    )
    parser.add_argument(
        "--paksa",
        action="store_true",
        help="proses ulang walau snapshot level 6 sudah ada",
    )
    parser.add_argument(
        "--jalankan",
        action="store_true",
        help="benar-benar memproses ulang (tanpa ini hanya laporan)",
    )
    args = parser.parse_args(argv)
    if args.dry_run and args.jalankan:
        parser.error("--dry-run dan --jalankan tidak boleh bersamaan")
    if args.env_file:
        try:
            muat_env(args.env_file)
        except OSError as galat:
            print(f"gagal membaca berkas environment {args.env_file}: {galat}")
            return 1

    kabupaten = _parse_kabupaten(args.kabupaten)
    if args.jalankan:
        return jalankan(kabupaten=kabupaten, paksa=args.paksa)

    try:
        with get_sessionmaker()() as sesi:
            rencana = susun_rencana(sesi, kabupaten=kabupaten, paksa=args.paksa)
    except SQLAlchemyError as galat:
        print(f"gagal membaca basis data: {galat}")
        return 1
    for teks in format_rencana(rencana):
        print(teks)
    perlu = sum(1 for satu in rencana if satu.diproses)
    print(f"{perlu} kabupaten/kota perlu diproses ulang dari {len(rencana)} kandidat")
    print("jalankan ulang dengan --jalankan setelah worker dihentikan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
