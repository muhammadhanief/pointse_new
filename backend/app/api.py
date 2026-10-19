"""Endpoint API pointse (T3): unggah/antre, status, hasil, dan rekap progres.

Catatan alur: unggah berkas **langsung membuat** baris ``runs`` berstatus
``menunggu``; worker (proses terpisah, lihat :mod:`app.worker`) yang mengambil
dan menjalankannya. Belum ada autentikasi (menyusul di T4).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app import layanan
from app.config import Settings, get_settings
from app.db import get_session
from app.layanan import Dasar, KesalahanUnggahan, Tingkat
from app.models import DASAR_TUGAS, TIPE_A, TIPE_B, Run
from app.skema import DaftarRunOut, HasilOut, RekapOut, RunDetailOut, RunOut

router = APIRouter()


def _simpan_unggahan(berkas: UploadFile, dir_run: Path, awalan: str) -> Path:
    """Tulis satu berkas unggahan ke folder job; kembalikan path-nya.

    Nama berkas dibersihkan dari komponen path, lalu diberi awalan (``titik_`` /
    ``peta_``) supaya dua berkas dengan nama sama tidak saling menimpa.
    """
    nama = Path(berkas.filename or "").name
    if not nama:
        raise HTTPException(status_code=422, detail=f"berkas {awalan} tidak punya nama")
    tujuan = dir_run / f"{awalan}_{nama}"
    layanan.simpan_berkas(berkas.file, tujuan)
    return tujuan


@router.post("/runs", response_model=RunOut, status_code=201)
def unggah_run(
    tipe: str = Form(..., description=f"'{TIPE_A}' (identifikasi titik) atau '{TIPE_B}'"),
    titik: UploadFile = File(..., description="Berkas titik (GPKG/GeoJSON)"),
    peta: UploadFile = File(..., description="Berkas peta batas wilkerstat (GPKG/GeoJSON)"),
    user: str | None = Form(None, description="Nama pengguna (sementara dari form, belum SSO)"),
    layer_titik: str | None = Form(None, description="Nama layer berkas titik (wajib untuk GPKG banyak layer)"),
    layer_peta: str | None = Form(None, description="Nama layer berkas peta"),
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
) -> Run:
    """Unggah berkas masukan dan antrekan job (status ``menunggu``)."""
    tipe_bersih = (tipe or "").strip().upper()
    if tipe_bersih not in (TIPE_A, TIPE_B):
        raise HTTPException(
            status_code=422, detail=f"tipe harus '{TIPE_A}' atau '{TIPE_B}', bukan '{tipe}'"
        )

    dir_run = Path(setelan.dir_unggahan) / uuid.uuid4().hex
    try:
        berkas_input = _simpan_unggahan(titik, dir_run, "titik")
        berkas_peta = _simpan_unggahan(peta, dir_run, "peta")
        info = layanan.periksa_unggahan(
            tipe_bersih, berkas_input, berkas_peta, layer_titik, layer_peta
        )
        run = layanan.buat_run(
            sesi,
            tipe=tipe_bersih,
            info=info,
            user=user,
            nama_input=Path(titik.filename or berkas_input.name).name,
            nama_peta=Path(peta.filename or berkas_peta.name).name,
            berkas_input=berkas_input,
            berkas_peta=berkas_peta,
        )
    except KesalahanUnggahan as galat:
        shutil.rmtree(dir_run, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(galat)) from galat
    except Exception:
        shutil.rmtree(dir_run, ignore_errors=True)
        raise

    return run


@router.get("/runs", response_model=DaftarRunOut)
def daftar_run(
    tipe: str | None = Query(None, description=f"'{TIPE_A}' atau '{TIPE_B}'"),
    status: str | None = Query(None, description="menunggu/jalan/sukses/gagal/digantikan"),
    kdkab: str | None = Query(None, description="Kode kabupaten/kota, mis. 3307"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sesi: Session = Depends(get_session),
) -> DaftarRunOut:
    """Daftar job terbaru lebih dulu (dengan penyaring dan paging)."""
    total, baris = layanan.daftar_run(
        sesi,
        tipe=tipe.strip().upper() if tipe else None,
        status=status,
        kdkab=kdkab,
        limit=limit,
        offset=offset,
    )
    return DaftarRunOut(total=total, baris=[RunOut.model_validate(baris) for baris in baris])


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def status_run(run_id: int, sesi: Session = Depends(get_session)) -> RunDetailOut:
    """Status satu job: status, waktu, pesan galat, jumlah hasil tersimpan."""
    run = layanan.ambil_run(sesi, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"job {run_id} tidak ditemukan")
    return RunDetailOut(
        **RunOut.model_validate(run).model_dump(),
        jumlah_tersimpan=layanan.jumlah_tersimpan(sesi, run_id),
    )


@router.get("/runs/{run_id}/hasil", response_model=HasilOut)
def hasil_run(
    run_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sesi: Session = Depends(get_session),
) -> HasilOut:
    """Baris hasil titik untuk satu job (paging, urut seperti keluaran Proses)."""
    if layanan.ambil_run(sesi, run_id) is None:
        raise HTTPException(status_code=404, detail=f"job {run_id} tidak ditemukan")
    total, baris = layanan.hasil_run(sesi, run_id, limit=limit, offset=offset)
    return HasilOut(run_id=run_id, total=total, limit=limit, offset=offset, baris=baris)


@router.get("/runs/{run_id}/rekap", response_model=RekapOut)
def rekap_run(
    run_id: int,
    tingkat: Tingkat = Query("kabupaten", description="kabupaten/kecamatan/desa/sls/subsls"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' (wilayah penugasan) atau 'posisi'"),
    sesi: Session = Depends(get_session),
) -> RekapOut:
    """Rekap progres per wilayah dari snapshot ``rekap_subsls`` (default dasar ``tugas``).

    Tiap baris memuat ``belum``, ``ditindak_posisi_benar``, ``ditindak_posisi_salah``,
    ``benar_awal``, ``digeser``, ``tanpa_wilayah``, dan ``persen_progres`` (kosong bila
    belum ada titik yang belum/ditindak). Baris ``wilayah_id`` NULL dibalas sebagai
    kategori "(tanpa wilayah)" di urutan terakhir.
    """
    if layanan.ambil_run(sesi, run_id) is None:
        raise HTTPException(status_code=404, detail=f"job {run_id} tidak ditemukan")
    return RekapOut.model_validate(layanan.rekap_run(sesi, run_id, tingkat, dasar))
