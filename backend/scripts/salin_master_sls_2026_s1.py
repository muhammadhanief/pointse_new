"""Salin master Excel SLS 2026 Semester 1 ke folder server + checksum.

Sumber: ``2026 Semester 1/<kdkab>/{Hirarki,Master,Rekap}/*.xlsx`` (per kab
``3300``-``3376``; hanya ``Hirarki`` + ``Master`` yang disalin).
Tujuan: ``data/master-sls-2026-s1/<kdkab>/`` (atau ``DIR_MASTER_SLS_2026_S1``),
dengan berkas ``sha256sums.txt`` per kabupaten + satu rekap global.

Idempoten: berkas yang isinya sama dilewati (banding sha256), yang berubah
ditiban lalu checksum ditulis ulang. ``Rekap`` tidak disalin (arsip lokal).
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path


def sha256(jalur: Path) -> str:
    h = hashlib.sha256()
    with jalur.open("rb") as f:
        for potong in iter(lambda: f.read(1 << 20), b""):
            h.update(potong)
    return h.hexdigest()


def salin_satu(sumber: Path, tujuan_dir: Path) -> tuple[str, bool]:
    tujuan_dir.mkdir(parents=True, exist_ok=True)
    tujuan = tujuan_dir / sumber.name
    if tujuan.exists() and sha256(tujuan) == sha256(sumber):
        return sumber.name, False
    shutil.copy2(sumber, tujuan)
    return sumber.name, True


def main() -> int:
    ap = argparse.ArgumentParser(description="Salin master SLS 2026 S1 ke server")
    ap.add_argument("--sumber", default="2026 Semester 1")
    ap.add_argument("--tujuan", default="data/master-sls-2026-s1")
    ap.add_argument("--kdkab", default="", help="mis. 3302; kosong = semua")
    args = ap.parse_args()

    akar_sumber = Path(args.sumber)
    akar_tujuan = Path(args.tujuan)
    if not akar_sumber.is_dir():
        print(f"sumber tidak ada: {akar_sumber}", file=sys.stderr)
        return 1

    kab_list = (
        [args.kdkab]
        if args.kdkab
        else sorted(p.name for p in akar_sumber.iterdir() if p.is_dir())
    )
    total = disalin = 0
    rekap: list[str] = []
    for kab in kab_list:
        dir_kab = akar_sumber / kab
        berkas = [
            *sorted((dir_kab / "Hirarki").glob("*.xlsx")),
            *sorted((dir_kab / "Master").glob("*.xlsx")),
        ]
        berkas = [b for b in berkas if b.is_file()]
        if not berkas:
            print(f"lewati {kab}: tidak ada Hirarki/Master xlsx")
            continue
        tujuan_kab = akar_tujuan / kab
        baris_sum: list[str] = []
        for satu in berkas:
            nama, berubah = salin_satu(satu, tujuan_kab)
            total += 1
            disalin += 1 if berubah else 0
            baris_sum.append(f"{sha256(tujuan_kab / nama)}  {nama}")
            rekap.append(f"{kab}/{nama}")
        (tujuan_kab / "sha256sums.txt").write_text("\n".join(baris_sum) + "\n")
    print(f"selesai: {total} berkas, {disalin} disalin/diubah")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
