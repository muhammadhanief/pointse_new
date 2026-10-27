"""Unggahan berpotongan (resumable) untuk berkas besar.

Proxy pusat membatasi body request 128 MiB, jadi berkas besar dikirim sebagai
beberapa potongan ``application/octet-stream``. Setiap potongan ditulis langsung
ke disk, di-hash, lalu disusun berurutan saat ``selesai``. Sesi disimpan di
``data/unggahan/_sementara/<id>`` agar bisa dilanjutkan setelah koneksi putus.

Endpoint lama ``POST /unggahan`` (satu body) tetap tersedia untuk kompatibilitas
dan berkas kecil.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.requests import ClientDisconnect

from app import auth, periksa_awal
from app.config import Settings, get_settings
from app.skema import (
    PotonganOut,
    UnggahanMulaiIn,
    UnggahanMulaiOut,
    UnggahanOut,
    UnggahanStatusOut,
)

router = APIRouter()

_POLA_ID = re.compile(r"^[0-9a-f]{32}$")
_POLA_SHA = re.compile(r"^[0-9a-f]{64}$")
_NAMA_CADANGAN = {"meta.json", "meta.json.tmp"}
_PANJANG_NAMA_MAKS = 180
_BLOK_SALIN = 1024 * 1024


def _akar_sementara(setelan: Settings) -> Path:
    return Path(setelan.dir_unggahan) / "_sementara"


def _akar_selesai(setelan: Settings) -> Path:
    return Path(setelan.dir_unggahan) / "_unggahan"


def _folder(id_unggah: str, akar: Path) -> Path:
    if not _POLA_ID.fullmatch(id_unggah):
        raise HTTPException(status_code=404, detail="unggahan tidak ditemukan")
    return akar / id_unggah


def _baca_json(jalur: Path) -> dict[str, Any]:
    try:
        data = json.loads(jalur.read_text(encoding="utf-8"))
    except (OSError, ValueError) as galat:
        raise HTTPException(status_code=404, detail="unggahan tidak ditemukan") from galat
    if not isinstance(data, dict):
        raise HTTPException(status_code=409, detail="metadata unggahan rusak")
    return data


def _baca_meta(folder: Path) -> dict[str, Any]:
    return _baca_json(folder / "meta.json")


def _tulis_json(folder: Path, nama: str, data: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    sementara = folder / f".{nama}.{uuid.uuid4().hex}.tmp"
    sementara.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(sementara, folder / nama)


def _tulis_meta(folder: Path, meta: dict[str, Any]) -> None:
    _tulis_json(folder, "meta.json", meta)


def _sentuh(folder: Path) -> None:
    """Perbarui mtime folder agar pembersihan tidak menghapus sesi aktif."""
    try:
        os.utime(folder, None)
    except OSError:
        pass


def _nama_aman(nama: str) -> str:
    mentah = (nama or "").replace("\\", "/")
    if "\x00" in mentah:
        raise HTTPException(status_code=422, detail="nama berkas tidak valid")
    bersih = Path(mentah).name.strip()
    if (
        not bersih
        or bersih in {".", ".."}
        or len(bersih) > _PANJANG_NAMA_MAKS
        or bersih.casefold() in _NAMA_CADANGAN
    ):
        raise HTTPException(status_code=422, detail="nama berkas tidak valid")
    return bersih


def _bersihkan(setelan: Settings) -> None:
    """Hapus unggahan sementara/selesai yang melewati batas kedaluwarsa."""
    batas = time.time() - setelan.unggah_kedaluwarsa_jam * 3600
    for akar in (_akar_sementara(setelan), _akar_selesai(setelan)):
        if not akar.exists():
            continue
        try:
            daftar = list(akar.iterdir())
        except OSError:
            continue
        for folder in daftar:
            if not folder.is_dir():
                continue
            try:
                if folder.stat().st_mtime < batas:
                    shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                continue


def _pastikan_pemilik(meta: dict[str, Any], pengguna: auth.Pengguna) -> None:
    if meta.get("pengguna") != pengguna.sub:
        raise HTTPException(
            status_code=403, detail="unggahan ini milik pengguna lain"
        )


def _jumlah_potongan(ukuran: int, ukuran_potongan: int) -> int:
    return max(1, math.ceil(ukuran / ukuran_potongan))


def _ukuran_potongan_harapan(meta: dict[str, Any], nomor: int) -> int:
    total = int(meta["jumlah_potongan"])
    ukuran = int(meta["ukuran"])
    potongan = int(meta["ukuran_potongan"])
    if nomor < 1 or nomor > total:
        raise HTTPException(status_code=422, detail="nomor potongan di luar rentang")
    if nomor < total:
        return potongan
    return ukuran - potongan * (total - 1)


def _folder_potongan(folder: Path) -> Path:
    return folder / "potongan"


def _berkas_potongan(folder: Path, nomor: int) -> Path:
    return _folder_potongan(folder) / f"{nomor:06d}.part"


def _berkas_sidecar(folder: Path, nomor: int) -> Path:
    return _folder_potongan(folder) / f"{nomor:06d}.json"


def _daftar_potongan(folder: Path, total: int) -> list[int]:
    hasil: list[int] = []
    for nomor in range(1, total + 1):
        berkas = _berkas_potongan(folder, nomor)
        sidecar = _berkas_sidecar(folder, nomor)
        if not berkas.is_file() or not sidecar.is_file():
            continue
        try:
            isi = json.loads(sidecar.read_text(encoding="utf-8"))
            if int(isi.get("ukuran", -1)) != berkas.stat().st_size:
                continue
        except (OSError, ValueError, TypeError):
            continue
        hasil.append(nomor)
    return hasil


def _meta_final(id_unggah: str, setelan: Settings) -> tuple[Path, dict[str, Any]] | None:
    folder = _folder(id_unggah, _akar_selesai(setelan))
    if not (folder / "meta.json").is_file():
        return None
    return folder, _baca_meta(folder)


def _ke_out(meta: dict[str, Any]) -> UnggahanOut:
    try:
        sha256 = str(meta["sha256"])
    except KeyError as galat:
        raise HTTPException(status_code=409, detail="metadata unggahan rusak") from galat
    return UnggahanOut(
        unggahan_id=str(meta["id"]),
        nama=str(meta["nama"]),
        ukuran=int(meta["ukuran"]),
        sha256=sha256,
        jenis=str(meta["jenis"]),
    )


def _ke_status(
    meta: dict[str, Any],
    setelan: Settings,
    diterima: list[int],
    *,
    selesai: bool = False,
) -> UnggahanStatusOut:
    return UnggahanStatusOut(
        unggahan_id=str(meta["id"]),
        nama=str(meta["nama"]),
        ukuran=int(meta["ukuran"]),
        jenis=str(meta["jenis"]),
        ukuran_potongan=int(
            meta.get("ukuran_potongan") or setelan.unggah_potongan_bytes
        ),
        jumlah_potongan=int(meta.get("jumlah_potongan") or 1),
        potongan_diterima=diterima,
        selesai=selesai,
        sha256=str(meta["sha256"]) if meta.get("sha256") else None,
    )


def ambil_berkas(
    id_unggah: str,
    jenis: str,
    pengguna: auth.Pengguna,
    setelan: Settings,
) -> tuple[Path, dict[str, Any]]:
    """Ambil berkas final yang sudah selesai diunggah."""
    folder = _folder(id_unggah, _akar_selesai(setelan))
    meta = _baca_meta(folder)
    _pastikan_pemilik(meta, pengguna)
    if meta.get("jenis") != jenis:
        raise HTTPException(
            status_code=422,
            detail=f"unggahan ini berjenis {meta.get('jenis')}, bukan {jenis}",
        )
    berkas = folder / str(meta.get("berkas") or "")
    if not berkas.is_file() or berkas.stat().st_size != int(meta["ukuran"]):
        raise HTTPException(
            status_code=409, detail="berkas unggahan sudah tidak tersedia"
        )
    return berkas, meta


def hapus_unggahan(id_unggah: str, setelan: Settings) -> None:
    """Hapus unggahan yang sudah dipakai membuat run/master."""
    for akar in (_akar_sementara(setelan), _akar_selesai(setelan)):
        try:
            shutil.rmtree(_folder(id_unggah, akar), ignore_errors=True)
        except HTTPException:
            return


def _tolak_kolom_kurang(jalur: Path, folder: Path, meta: dict[str, Any]) -> None:
    """Batalkan sesi unggahan kalau potongan awal sudah jelas kurang kolom.

    Berkas bisa ratusan MB; menunggu seluruh potongan terkirim hanya untuk
    ditolak saat ``POST /runs`` membuang waktu pengguna. Potongan pertama sudah
    memuat skema (GeoPackage) atau fitur pertama (GeoJSON), jadi cukup dari situ.
    Sesi dihapus supaya sisa potongan tidak menumpuk di disk.
    """
    jenis = str(meta.get("jenis") or "")
    kurang = periksa_awal.kurang_kolom(jalur, jenis)
    if not kurang:
        return
    shutil.rmtree(folder, ignore_errors=True)
    raise HTTPException(
        status_code=422,
        detail=(
            f"berkas {jenis or 'unggahan'} tidak punya kolom wajib "
            f"({', '.join(kurang)}); unggahan dihentikan di potongan pertama "
            "agar tidak menunggu seluruh berkas terkirim"
        ),
    )


async def _simpan_potongan(
    request: Request,
    folder: Path,
    meta: dict[str, Any],
    nomor: int,
    setelan: Settings,
) -> PotonganOut:
    """Terima satu potongan; hash dan ukuran harus cocok. Idempoten."""
    tipe_konten = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipe_konten != "application/octet-stream":
        raise HTTPException(
            status_code=415,
            detail="Content-Type potongan harus application/octet-stream",
        )

    sha_dikirim = (request.headers.get("x-sha256") or "").strip().lower()
    if not _POLA_SHA.fullmatch(sha_dikirim):
        raise HTTPException(
            status_code=422,
            detail="header X-Sha256 wajib berisi 64 karakter heksadesimal",
        )

    harapan = _ukuran_potongan_harapan(meta, nomor)
    panjang_header = request.headers.get("content-length")
    if panjang_header is not None:
        try:
            panjang = int(panjang_header)
        except ValueError as galat:
            raise HTTPException(status_code=422, detail="content-length tidak valid") from galat
        if panjang != harapan:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"ukuran potongan {nomor} harus {harapan} byte, "
                    f"bukan {panjang} byte"
                ),
            )

    folder_potongan = _folder_potongan(folder)
    folder_potongan.mkdir(parents=True, exist_ok=True)
    tujuan = _berkas_potongan(folder, nomor)
    sidecar = _berkas_sidecar(folder, nomor)
    sementara = folder_potongan / f".{nomor:06d}.{uuid.uuid4().hex}.tmp"
    hash_sha = hashlib.sha256()
    ukuran = 0

    try:
        with sementara.open("wb") as keluar:
            async for blok in request.stream():
                if not blok:
                    continue
                ukuran += len(blok)
                if ukuran > harapan:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"potongan {nomor} melebihi ukuran {harapan} byte"
                        ),
                    )
                hash_sha.update(blok)
                keluar.write(blok)

        if ukuran != harapan:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"potongan {nomor} terputus: diterima {ukuran} dari "
                    f"{harapan} byte"
                ),
            )
        sha_hasil = hash_sha.hexdigest()
        if sha_hasil != sha_dikirim:
            raise HTTPException(
                status_code=422,
                detail="sha256 potongan tidak cocok",
            )

        if tujuan.is_file() and sidecar.is_file():
            try:
                lama = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                lama = {}
            if (
                int(lama.get("ukuran", -1)) == ukuran
                and lama.get("sha256") == sha_hasil
            ):
                sementara.unlink(missing_ok=True)
                _sentuh(folder)
                return PotonganOut(
                    unggahan_id=str(meta["id"]),
                    potongan=nomor,
                    ukuran=ukuran,
                )
            raise HTTPException(
                status_code=409,
                detail=f"potongan {nomor} sudah diterima dengan isi berbeda",
            )

        os.replace(sementara, tujuan)
        _tulis_json(
            folder_potongan,
            sidecar.name,
            {"ukuran": ukuran, "sha256": sha_hasil},
        )
        if nomor == 1:
            # Berkas ratusan MB: periksa kelengkapan kolom dari potongan awal
            # supaya pengguna tidak menunggu seluruh berkas terkirim dulu.
            _tolak_kolom_kurang(tujuan, folder, meta)
        _sentuh(folder)
        return PotonganOut(
            unggahan_id=str(meta["id"]),
            potongan=nomor,
            ukuran=ukuran,
        )
    except ClientDisconnect as galat:
        sementara.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"potongan {nomor} terputus",
        ) from galat
    except Exception:
        sementara.unlink(missing_ok=True)
        raise


def _selesai_unggahan(
    folder: Path,
    meta: dict[str, Any],
    setelan: Settings,
) -> UnggahanOut:
    """Susun potongan berurutan, hapus tiap potongan setelah disalin."""
    total = int(meta["jumlah_potongan"])
    diterima = set(_daftar_potongan(folder, total))
    hilang = [nomor for nomor in range(1, total + 1) if nomor not in diterima]
    if hilang:
        raise HTTPException(
            status_code=409,
            detail=f"potongan belum lengkap: {', '.join(map(str, hilang))}",
        )

    # Sesi yang dimulai sebelum pemeriksaan potongan pertama ada (mis. lanjutan
    # setelah deploy) tetap ditolak di sini, sebelum berkas disusun.
    _tolak_kolom_kurang(_berkas_potongan(folder, 1), folder, meta)

    hasil = folder / "hasil"
    hash_sha = hashlib.sha256()
    ukuran = 0
    try:
        with hasil.open("wb") as keluar:
            for nomor in range(1, total + 1):
                bagian = _berkas_potongan(folder, nomor)
                sidecar = _berkas_sidecar(folder, nomor)
                harapan = _ukuran_potongan_harapan(meta, nomor)
                hash_bagian = hashlib.sha256()
                ukuran_bagian = 0
                with bagian.open("rb") as masuk:
                    while True:
                        blok = masuk.read(_BLOK_SALIN)
                        if not blok:
                            break
                        ukuran_bagian += len(blok)
                        ukuran += len(blok)
                        hash_bagian.update(blok)
                        hash_sha.update(blok)
                        keluar.write(blok)
                if ukuran_bagian != harapan:
                    raise HTTPException(
                        status_code=409,
                        detail=f"potongan {nomor} tidak utuh",
                    )
                try:
                    isi_sidecar = json.loads(sidecar.read_text(encoding="utf-8"))
                except (OSError, ValueError) as galat:
                    raise HTTPException(
                        status_code=409,
                        detail=f"metadata potongan {nomor} rusak",
                    ) from galat
                if isi_sidecar.get("sha256") != hash_bagian.hexdigest():
                    raise HTTPException(
                        status_code=409,
                        detail=f"sha256 potongan {nomor} tidak cocok",
                    )
                # Hapus setelah disalin supaya ruang tidak dobel.
                bagian.unlink(missing_ok=True)
                sidecar.unlink(missing_ok=True)

        if ukuran != int(meta["ukuran"]):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"ukuran gabungan {ukuran} tidak sama dengan "
                    f"{meta['ukuran']} byte"
                ),
            )
        sha256 = hash_sha.hexdigest()

        folder_final = _folder(str(meta["id"]), _akar_selesai(setelan))
        folder_final.mkdir(parents=True, exist_ok=True)
        tujuan = folder_final / str(meta["nama"])
        os.replace(hasil, tujuan)
        final_meta = {
            **meta,
            "berkas": str(meta["nama"]),
            "sha256": sha256,
        }
        _tulis_meta(folder_final, final_meta)
        shutil.rmtree(folder, ignore_errors=True)
        return _ke_out(final_meta)
    except Exception:
        hasil.unlink(missing_ok=True)
        raise


@router.post("/unggahan/mulai", response_model=UnggahanMulaiOut, status_code=201)
def mulai_unggahan(
    data: UnggahanMulaiIn,
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> UnggahanMulaiOut:
    """Buat sesi unggahan berpotongan baru."""
    if data.ukuran < 1:
        raise HTTPException(status_code=422, detail="ukuran berkas harus lebih dari 0")
    if (
        setelan.unggah_maks_bytes > 0
        and data.ukuran > setelan.unggah_maks_bytes
    ):
        raise HTTPException(
            status_code=413,
            detail=(
                f"berkas terlalu besar; maksimal {setelan.unggah_maks_bytes} byte"
            ),
        )

    nama_aman = _nama_aman(data.nama)
    _bersihkan(setelan)
    id_unggah = uuid.uuid4().hex
    ukuran_potongan = setelan.unggah_potongan_bytes
    jumlah_potongan = _jumlah_potongan(data.ukuran, ukuran_potongan)
    folder = _akar_sementara(setelan) / id_unggah
    folder.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": id_unggah,
        "nama": nama_aman,
        "ukuran": data.ukuran,
        "jenis": data.jenis,
        "pengguna": pengguna.sub,
        "berkas": nama_aman,
        "dibuat": time.time(),
        "ukuran_potongan": ukuran_potongan,
        "jumlah_potongan": jumlah_potongan,
    }
    _tulis_meta(folder, meta)
    return UnggahanMulaiOut(
        unggahan_id=id_unggah,
        nama=nama_aman,
        ukuran=data.ukuran,
        jenis=data.jenis,
        ukuran_potongan=ukuran_potongan,
        jumlah_potongan=jumlah_potongan,
    )


@router.get("/unggahan/{id_unggah}", response_model=UnggahanStatusOut)
def status_unggahan(
    id_unggah: str,
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> UnggahanStatusOut:
    """Status sesi: daftar potongan yang sudah diterima untuk melanjutkan."""
    final = _meta_final(id_unggah, setelan)
    if final is not None:
        _, meta = final
        _pastikan_pemilik(meta, pengguna)
        return _ke_status(meta, setelan, [], selesai=True)

    folder = _folder(id_unggah, _akar_sementara(setelan))
    meta = _baca_meta(folder)
    _pastikan_pemilik(meta, pengguna)
    diterima = _daftar_potongan(folder, int(meta["jumlah_potongan"]))
    return _ke_status(meta, setelan, diterima)


@router.post(
    "/unggahan/{id_unggah}/potongan/{nomor}",
    response_model=PotonganOut,
)
async def unggah_potongan(
    request: Request,
    id_unggah: str,
    nomor: int,
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> PotonganOut:
    """Terima satu potongan body mentah; aman dikirim ulang."""
    folder = _folder(id_unggah, _akar_sementara(setelan))
    meta = _baca_meta(folder)
    _pastikan_pemilik(meta, pengguna)
    return await _simpan_potongan(request, folder, meta, nomor, setelan)


@router.post("/unggahan/{id_unggah}/selesai", response_model=UnggahanOut)
def selesaikan_unggahan(
    id_unggah: str,
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> UnggahanOut:
    """Gabungkan semua potongan menjadi berkas final."""
    final = _meta_final(id_unggah, setelan)
    if final is not None:
        folder_final, meta = final
        _pastikan_pemilik(meta, pengguna)
        # Sisa folder sementara (misalnya proses sebelumnya terhenti setelah
        # pemindahan) tidak diperlukan lagi.
        shutil.rmtree(
            _folder(id_unggah, _akar_sementara(setelan)),
            ignore_errors=True,
        )
        return _ke_out(meta)

    folder = _folder(id_unggah, _akar_sementara(setelan))
    meta = _baca_meta(folder)
    _pastikan_pemilik(meta, pengguna)
    return _selesai_unggahan(folder, meta, setelan)


@router.post("/unggahan", response_model=UnggahanOut, status_code=201)
async def unggah_berkas(
    request: Request,
    jenis: Literal["master", "peta", "titik"] = Query(...),
    nama: str = Query(...),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> UnggahanOut:
    """Endpoint lama: terima satu berkas sebagai body mentah.

    Dipertahankan untuk berkas kecil dan kompatibilitas; frontend sekarang
    memakai alur berpotongan di atas.
    """
    tipe_konten = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipe_konten != "application/octet-stream":
        raise HTTPException(
            status_code=415,
            detail="Content-Type harus application/octet-stream",
        )

    nama_aman = _nama_aman(nama)
    panjang_diharapkan: int | None = None
    panjang_header = request.headers.get("content-length")
    if panjang_header is not None:
        try:
            panjang_diharapkan = int(panjang_header)
        except ValueError as galat:
            raise HTTPException(
                status_code=422, detail="content-length tidak valid"
            ) from galat
        if panjang_diharapkan < 0:
            raise HTTPException(status_code=422, detail="content-length tidak valid")
        if (
            setelan.unggah_maks_bytes > 0
            and panjang_diharapkan > setelan.unggah_maks_bytes
        ):
            raise HTTPException(
                status_code=413,
                detail=(
                    f"berkas terlalu besar; maksimal "
                    f"{setelan.unggah_maks_bytes} byte"
                ),
            )

    _bersihkan(setelan)
    id_unggah = uuid.uuid4().hex
    folder_sementara = _akar_sementara(setelan) / id_unggah
    folder_sementara.mkdir(parents=True, exist_ok=True)
    jalur_sementara = folder_sementara / ".part"
    hash_sha = hashlib.sha256()
    ukuran = 0
    folder_selesai: Path | None = None

    try:
        with jalur_sementara.open("wb") as keluar:
            async for blok in request.stream():
                if not blok:
                    continue
                ukuran += len(blok)
                if (
                    setelan.unggah_maks_bytes > 0
                    and ukuran > setelan.unggah_maks_bytes
                ):
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"berkas terlalu besar; maksimal "
                            f"{setelan.unggah_maks_bytes} byte"
                        ),
                    )
                hash_sha.update(blok)
                keluar.write(blok)
        if ukuran < 1:
            raise HTTPException(status_code=422, detail="berkas kosong")
        if panjang_diharapkan is not None and ukuran != panjang_diharapkan:
            raise HTTPException(
                status_code=400,
                detail=(
                    "body unggahan terputus: diterima "
                    f"{ukuran} dari {panjang_diharapkan} byte"
                ),
            )

        sha256 = hash_sha.hexdigest()
        folder_selesai = _akar_selesai(setelan) / id_unggah
        folder_selesai.mkdir(parents=True, exist_ok=True)
        tujuan = folder_selesai / nama_aman
        os.replace(jalur_sementara, tujuan)
        meta = {
            "id": id_unggah,
            "nama": nama_aman,
            "ukuran": ukuran,
            "sha256": sha256,
            "jenis": jenis,
            "pengguna": pengguna.sub,
            "berkas": nama_aman,
            "dibuat": time.time(),
        }
        _tulis_meta(folder_selesai, meta)
    except ClientDisconnect as galat:
        shutil.rmtree(folder_sementara, ignore_errors=True)
        if folder_selesai is not None:
            shutil.rmtree(folder_selesai, ignore_errors=True)
        raise HTTPException(status_code=400, detail="body unggahan terputus") from galat
    except Exception:
        shutil.rmtree(folder_sementara, ignore_errors=True)
        if folder_selesai is not None:
            shutil.rmtree(folder_selesai, ignore_errors=True)
        raise

    shutil.rmtree(folder_sementara, ignore_errors=True)
    return UnggahanOut(
        unggahan_id=id_unggah,
        nama=nama_aman,
        ukuran=ukuran,
        sha256=sha256,
        jenis=jenis,
    )
