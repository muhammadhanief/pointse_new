"""Endpoint API pointse (T3): unggah/antre, status, hasil, dan rekap progres.

Catatan alur: unggah berkas **langsung membuat** baris ``runs`` berstatus
``menunggu``; worker (proses terpisah, lihat :mod:`app.worker`) yang mengambil
dan menjalankannya. Belum ada autentikasi (menyusul di T4).

Kunci wilayah di seluruh endpoint adalah (``kdprov``, ``kdkab``); ``tanggal_data``
(tanggal data, default tanggal unggah) dipisah dari ``created_at`` (waktu unggah).
"""

from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app import layanan
from app.config import Settings, get_settings
from app.db import get_session
from app.layanan import (
    Dasar,
    DetailTidakTersedia,
    KesalahanPerubahan,
    KesalahanUnggahan,
    Tingkat,
)
from app.models import DASAR_TUGAS, TIPE_A, TIPE_B, Run
from app.skema import (
    DaftarRunOut,
    HasilOut,
    PerubahanOut,
    RekapDetailOut,
    RekapOut,
    RingkasanOut,
    RunDetailOut,
    RunOut,
    TrenOut,
)

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


def _ambil_run(sesi: Session, run_id: int) -> Run:
    """Ambil run atau balas 404."""
    run = layanan.ambil_run(sesi, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"job {run_id} tidak ditemukan")
    return run


@router.post("/runs", response_model=RunOut, status_code=201)
def unggah_run(
    tipe: str = Form(..., description=f"'{TIPE_A}' (identifikasi titik) atau '{TIPE_B}'"),
    titik: UploadFile = File(..., description="Berkas titik (GPKG/GeoJSON)"),
    peta: UploadFile = File(..., description="Berkas peta batas wilkerstat (GPKG/GeoJSON)"),
    user: str | None = Form(None, description="Nama pengguna (sementara dari form, belum SSO)"),
    tanggal_data: date | None = Form(None, description="Tanggal data (default: tanggal unggah)"),
    layer_titik: str | None = Form(None, description="Nama layer berkas titik (wajib untuk GPKG banyak layer)"),
    layer_peta: str | None = Form(None, description="Nama layer berkas peta"),
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
) -> Run:
    """Unggah berkas masukan dan antrekan job (status ``menunggu``).

    Job lama untuk kabupaten/kota+tipe yang sama **tidak** dihapus/ditandai: semua
    job antre dikerjakan berurutan oleh worker.
    """
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
            tanggal_data=tanggal_data,
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
    status: str | None = Query(None, description="menunggu/jalan/sukses/gagal"),
    kdprov: str | None = Query(None, description="Kode provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Kode kabupaten/kota, mis. 07"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sesi: Session = Depends(get_session),
) -> DaftarRunOut:
    """Daftar job terbaru lebih dulu (dengan penyaring dan paging)."""
    total, baris = layanan.daftar_run(
        sesi,
        tipe=tipe.strip().upper() if tipe else None,
        status=status,
        kdprov=kdprov,
        kdkab=kdkab,
        limit=limit,
        offset=offset,
    )
    return DaftarRunOut(total=total, baris=[RunOut.model_validate(baris) for baris in baris])


@router.get("/ringkasan", response_model=RingkasanOut)
def ringkasan(
    tipe: str | None = Query(None, description=f"'{TIPE_A}' atau '{TIPE_B}'"),
    kdprov: str | None = Query(None, description="Saring satu provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Saring satu kabupaten/kota, mis. 07"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' (wilayah penugasan) atau 'posisi'"),
    sesi: Session = Depends(get_session),
) -> RingkasanOut:
    """Ringkasan provinsi: satu baris per kabupaten/kota (run terakhir tiap tipe).

    Angka dibaca dari ``rekap_kabupaten``; ``belum_ada_upload_tipe_b`` menandai
    kabupaten/kota yang belum pernah menerima unggahan Proses B.
    """
    return RingkasanOut.model_validate(
        layanan.ringkasan(
            sesi,
            tipe=tipe.strip().upper() if tipe else None,
            provinsi=kdprov,
            kdkab=kdkab,
            dasar=dasar,
        )
    )


@router.get("/tren", response_model=TrenOut)
def tren(
    tingkat: str = Query("kabupaten", description="'kabupaten' atau 'provinsi'"),
    tipe: str | None = Query(None, description=f"'{TIPE_A}' atau '{TIPE_B}'"),
    kdprov: str | None = Query(None, description="Saring satu provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Saring satu kabupaten/kota, mis. 07"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' (wilayah penugasan) atau 'posisi'"),
    sesi: Session = Depends(get_session),
) -> TrenOut:
    """Tren progres per ``tanggal_data`` (run sukses terakhir pada tanggal itu)."""
    if tingkat not in ("kabupaten", "provinsi"):
        raise HTTPException(status_code=422, detail="tingkat tren harus 'kabupaten' atau 'provinsi'")
    return TrenOut.model_validate(
        layanan.tren(
            sesi,
            tingkat=tingkat,
            tipe=tipe.strip().upper() if tipe else None,
            provinsi=kdprov,
            kdkab=kdkab,
            dasar=dasar,
        )
    )


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def status_run(run_id: int, sesi: Session = Depends(get_session)) -> RunDetailOut:
    """Status satu job: status, waktu, pesan galat, jumlah hasil tersimpan.

    ``detail_tersedia`` = ``false`` berarti baris ``titik_hasil`` run ini sudah
    dipangkas (angka rekapnya tetap utuh).
    """
    run = _ambil_run(sesi, run_id)
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
    """Baris hasil titik untuk satu job (paging, urut seperti keluaran Proses).

    Yang tersimpan hanya titik yang perlu perhatian; titik yang sudah benar tanpa
    tindakan manual tidak muncul di sini (terhitung di rekap).
    """
    run = _ambil_run(sesi, run_id)
    total, baris = layanan.hasil_run(sesi, run_id, limit=limit, offset=offset)
    return HasilOut(
        run_id=run_id,
        detail_tersedia=bool(run.detail_tersedia),
        total=total,
        limit=limit,
        offset=offset,
        baris=baris,
    )


@router.get("/runs/{run_id}/rekap", response_model=RekapOut | RekapDetailOut)
def rekap_run(
    run_id: int,
    tingkat: Tingkat = Query("kabupaten", description="kabupaten/kecamatan/desa/sls/subsls"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' (wilayah penugasan) atau 'posisi'"),
    sesi: Session = Depends(get_session),
) -> RekapOut | RekapDetailOut:
    """Rekap progres per wilayah (default dasar ``tugas``).

    Tingkat ``kabupaten``/``kecamatan``/``desa`` dibaca dari snapshot
    ``rekap_kabupaten``/``rekap_desa``: tiap baris memuat ``belum``,
    ``ditindak_posisi_benar``, ``ditindak_posisi_salah``, ``benar_awal``, ``digeser``,
    ``tanpa_wilayah``, dan ``persen_progres`` (kosong bila penyebutnya 0). Tingkat
    ``sls``/``subsls`` dihitung saat diminta dari ``titik_hasil`` (hanya ``belum`` dan
    ``ditindak``) dan hanya tersedia untuk run yang detailnya masih disimpan
    (409 bila sudah dipangkas). Baris tanpa wilayah dibalas "(tanpa wilayah)".
    """
    run = _ambil_run(sesi, run_id)
    try:
        rekap = layanan.rekap_run(sesi, run, tingkat, dasar)
    except DetailTidakTersedia as galat:
        raise HTTPException(status_code=409, detail=str(galat)) from galat
    model = RekapOut if tingkat in layanan.TINGKAT_REKAP else RekapDetailOut
    return model.model_validate(rekap)


@router.get("/perubahan", response_model=PerubahanOut)
def perubahan(
    run_awal: int = Query(..., description="Id run pembanding (awal)"),
    run_akhir: int = Query(..., description="Id run yang dibandingkan (akhir)"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' (wilayah penugasan) atau 'posisi'"),
    limit: int = Query(200, ge=1, le=1000, description="Maksimal baris perubahan per titik"),
    offset: int = Query(0, ge=0, description="Offset baris perubahan per titik"),
    sesi: Session = Depends(get_session),
) -> PerubahanOut:
    """Perubahan antara dua run: selisih rekap kabupaten/desa + perubahan per titik.

    Selisih rekap bisa dihitung untuk pasangan run mana pun (keduanya harus sudah
    sukses); perubahan status per titik hanya untuk pasangan **baseline vs run
    sukses terakhir** pada kabupaten/kota+tipe yang sama.
    """
    awal = _ambil_run(sesi, run_awal)
    akhir = _ambil_run(sesi, run_akhir)
    try:
        hasil = layanan.perubahan(
            sesi, run_awal=awal, run_akhir=akhir, dasar=dasar, limit=limit, offset=offset
        )
    except KesalahanPerubahan as galat:
        raise HTTPException(status_code=409, detail=str(galat)) from galat
    return PerubahanOut.model_validate(hasil)
