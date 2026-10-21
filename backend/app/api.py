"""Endpoint API pointse (T3): unggah/antre, status, hasil, dan rekap progres.

Catatan alur: unggah berkas **langsung membuat** baris ``runs`` berstatus
``menunggu``; worker (proses terpisah, lihat :mod:`app.worker`) yang mengambil
dan menjalankannya. Sejak T4, seluruh endpoint selain ``/health`` membutuhkan
``Authorization: Bearer`` berisi token sesi dari frontend; wilayah dibatasi
sesuai peran SSO (lihat :mod:`app.auth`).

Kunci wilayah di seluruh endpoint adalah (``kdprov``, ``kdkab``); ``tanggal_data``
(tanggal data, default tanggal unggah) dipisah dari ``created_at`` (waktu unggah).
"""

from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path
from typing import BinaryIO

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app import auth, ekspor, layanan, unggahan
from app.config import Settings, get_settings
from app.db import get_session
from app.layanan import (
    Dasar,
    DetailTidakTersedia,
    KesalahanPerubahan,
    KesalahanUnggahan,
    Tingkat,
)
from app.models import DASAR_TUGAS, STATUS_SUKSES, TIPE_A, TIPE_B, Run
from app.peran import PERAN_ADMIN_PROVINSI
from app.skema import (
    DaftarMasterOut,
    DaftarRunOut,
    HasilOut,
    MasterGeotagOut,
    PerubahanOut,
    ProgresBOut,
    RekapDetailOut,
    RekapOut,
    RingkasanOut,
    RunDetailOut,
    RunOut,
    TabulasiProgresOut,
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
    unggahan_id: str | None = Form(
        None,
        description=(
            "Id unggahan body mentah yang sudah selesai. Proses A memakai unggahan "
            "peta; Proses B memakai unggahan titik."
        ),
    ),
    titik: UploadFile | None = File(
        None,
        description=(
            "Mode pengembangan/berkas kecil. Proses A: kosongkan (geotag master "
            "dipakai otomatis). Proses B: berkas GPKG hasil edit Proses A."
        ),
    ),
    peta: UploadFile | None = File(
        None,
        description=(
            "Mode pengembangan/berkas kecil. Proses A: peta batas wilkerstat. "
            "Proses B: kosongkan (peta diambil dari run A terakhir)."
        ),
    ),
    user: str | None = Form(None, description="Nama pengguna (diabaikan saat SSO aktif)"),
    tanggal_data: date | None = Form(None, description="Tanggal data (default: tanggal unggah)"),
    layer_titik: str | None = Form(None, description="Nama layer berkas titik (wajib untuk GPKG banyak layer)"),
    layer_peta: str | None = Form(None, description="Nama layer berkas peta"),
    sumber_run_a_id: int | None = Form(
        None,
        description=(
            "Proses B: id run Proses A sukses yang petanya dipakai. "
            "Kosongkan untuk memakai run A sukses terakhir."
        ),
    ),
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> Run:
    """Unggah berkas masukan dan antrekan job (status ``menunggu``).

    Dua alur yang didukung:

    - **A baru**: unggah ``peta`` saja; backend mencari geotag master terbaru
      untuk kabupaten/kota itu (ditolak 409 kalau belum ada), lalu membuat job A
      memakai master tersebut. Peta disimpan di folder job seperti biasa.
    - **B baru**: unggah ``titik`` saja (GPKG hasil edit A); backend memakai run A
      sukses terakhir untuk kabupaten/kota itu, atau run A yang disebut
      ``sumber_run_a_id`` bila diisi, menyalin petanya ke folder job B, lalu
      membuat job B.

    Mengirim kedua berkas tetap didukung untuk kompatibilitas (mode manual/uji).
    Job lama untuk kabupaten/kota+tipe yang sama **tidak** dihapus/ditandai: semua
    job antre dikerjakan berurutan oleh worker.
    """
    tipe_bersih = (tipe or "").strip().upper()
    if tipe_bersih not in (TIPE_A, TIPE_B):
        raise HTTPException(
            status_code=422, detail=f"tipe harus '{TIPE_A}' atau '{TIPE_B}', bukan '{tipe}'"
        )
    if unggahan_id and (peta is not None or titik is not None):
        raise HTTPException(
            status_code=422,
            detail="pakai unggahan_id atau berkas multipart, jangan keduanya",
        )
    if tipe_bersih == TIPE_A and peta is None and not unggahan_id:
        raise HTTPException(
            status_code=422, detail="Proses A butuh berkas peta batas wilkerstat"
        )
    if tipe_bersih == TIPE_B and titik is None and not unggahan_id:
        raise HTTPException(
            status_code=422, detail="Proses B butuh berkas titik hasil edit Proses A"
        )

    # Wilayah tetap dibatasi peran: petugas hanya kabupaten/kotanya, admin
    # provinsi boleh menjalankan A/B untuk kabupaten/kota di provinsinya
    # (pengawasan/uji); unggah master tetap khusus admin provinsi.
    # Mode lama masih menerima nama pengunggah dari form; saat SSO aktif, identitas
    # selalu diambil dari token agar tidak bisa dipalsukan.
    # Di mode dev, kolom form lama tetap dipakai agar tes/manual kompatibel.
    # Di production identitas selalu berasal dari token Bearer.
    nama_user = (
        (user or pengguna.nama) if setelan.auth_mode == "dev" else pengguna.nama
    )

    dir_run = Path(setelan.dir_unggahan) / uuid.uuid4().hex
    unggahan_dipakai: str | None = None
    try:
        if tipe_bersih == TIPE_A:
            if unggahan_id:
                sumber_peta, meta_unggah = unggahan.ambil_berkas(
                    unggahan_id, "peta", pengguna, setelan
                )
                nama_peta_asli = str(meta_unggah["nama"])
                dir_run.mkdir(parents=True, exist_ok=True)
                berkas_peta = dir_run / f"peta_{nama_peta_asli}"
                shutil.copy2(sumber_peta, berkas_peta)
                unggahan_dipakai = unggahan_id
            else:
                berkas_peta = _simpan_unggahan(peta, dir_run, "peta")
                nama_peta_asli = Path(peta.filename or berkas_peta.name).name
            if titik is not None:
                # Mode manual/uji: kedua berkas diunggah langsung.
                berkas_input = _simpan_unggahan(titik, dir_run, "titik")
                info = layanan.periksa_unggahan(
                    tipe_bersih, berkas_input, berkas_peta, layer_titik, layer_peta
                )
                auth.pastikan_akses(pengguna, info.kdprov, info.kdkab)
                run = layanan.buat_run(
                    sesi,
                    tipe=tipe_bersih,
                    info=info,
                    user=nama_user,
                    nama_input=Path(titik.filename or berkas_input.name).name,
                    nama_peta=nama_peta_asli,
                    berkas_input=berkas_input,
                    berkas_peta=berkas_peta,
                    tanggal_data=tanggal_data,
                )
            else:
                # Alur baru: peta dari kabkot + geotag master dari provinsi.
                nama_peta, kdprov, kdkab = layanan.periksa_peta(berkas_peta, layer_peta)
                auth.pastikan_akses(pengguna, kdprov, kdkab)
                kode = layanan.kode_kabupaten(kdprov, kdkab)
                master = layanan.master_terbaru(sesi, kode)
                if master is None:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"geotag master untuk kabupaten/kota {kode} belum tersedia; "
                            "minta admin provinsi mengunggahnya lebih dulu"
                        ),
                    )
                info = layanan.InfoUnggahan(
                    kdprov=kdprov,
                    kdkab=kdkab,
                    layer_input=master.layer,
                    layer_peta=nama_peta,
                )
                run = layanan.buat_run(
                    sesi,
                    tipe=tipe_bersih,
                    info=info,
                    user=nama_user,
                    nama_input=master.nama_file,
                    nama_peta=nama_peta_asli,
                    berkas_input=Path(master.berkas),
                    berkas_peta=berkas_peta,
                    tanggal_data=tanggal_data or master.tanggal_data,
                    geotag_master_id=master.id,
                )
        else:
            if unggahan_id:
                sumber_titik, meta_unggah = unggahan.ambil_berkas(
                    unggahan_id, "titik", pengguna, setelan
                )
                nama_input_asli = str(meta_unggah["nama"])
                dir_run.mkdir(parents=True, exist_ok=True)
                berkas_input = dir_run / f"titik_{nama_input_asli}"
                shutil.copy2(sumber_titik, berkas_input)
                unggahan_dipakai = unggahan_id
            else:
                berkas_input = _simpan_unggahan(titik, dir_run, "titik")
                nama_input_asli = Path(titik.filename or berkas_input.name).name
            if peta is not None:
                # Mode manual/uji: peta ikut diunggah.
                berkas_peta = _simpan_unggahan(peta, dir_run, "peta")
                info = layanan.periksa_unggahan(
                    tipe_bersih, berkas_input, berkas_peta, layer_titik, layer_peta
                )
                auth.pastikan_akses(pengguna, info.kdprov, info.kdkab)
                run = layanan.buat_run(
                    sesi,
                    tipe=tipe_bersih,
                    info=info,
                    user=nama_user,
                    nama_input=nama_input_asli,
                    nama_peta=Path(peta.filename or berkas_peta.name).name,
                    berkas_input=berkas_input,
                    berkas_peta=berkas_peta,
                    tanggal_data=tanggal_data,
                )
            else:
                # Alur baru: peta diambil dari run A terakhir, bukan diunggah ulang.
                info_b = layanan.periksa_titik_b(berkas_input, layer_titik)
                auth.pastikan_akses(pengguna, info_b.kdprov, info_b.kdkab)
                if sumber_run_a_id is not None:
                    sumber_a = layanan.ambil_run(sesi, sumber_run_a_id)
                    if sumber_a is None:
                        raise HTTPException(
                            status_code=404,
                            detail=f"run sumber A {sumber_run_a_id} tidak ditemukan",
                        )
                    if sumber_a.tipe != TIPE_A or sumber_a.status != STATUS_SUKSES:
                        raise HTTPException(
                            status_code=422,
                            detail="sumber peta harus run Proses A yang sukses",
                        )
                    auth.pastikan_akses(pengguna, sumber_a.kdprov, sumber_a.kdkab)
                    kode_sumber = layanan.kode_kabupaten(
                        sumber_a.kdprov, sumber_a.kdkab
                    )
                    if kode_sumber != info_b.kode_kabupaten:
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                f"run sumber A {sumber_a.id} berasal dari "
                                f"kabupaten/kota {kode_sumber}, bukan "
                                f"{info_b.kode_kabupaten}"
                            ),
                        )
                else:
                    sumber_a = layanan.run_a_terakhir(
                        sesi, info_b.kdprov, info_b.kode_kabupaten
                    )
                if sumber_a is None:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"belum ada Proses A yang sukses untuk kabupaten/kota "
                            f"{info_b.kode_kabupaten}; jalankan Proses A lebih dulu"
                        ),
                    )
                sumber_peta = Path(sumber_a.berkas_peta)
                if not sumber_peta.exists():
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"berkas peta run A {sumber_a.id} sudah tidak tersedia; "
                            "unggah ulang peta atau jalankan Proses A lagi"
                        ),
                    )
                # Pertahankan nama berkas sumber: layer GeoJSON diturunkan dari
                # nama berkas, jadi prefiks tambahan membuat layer tidak ketemu.
                tujuan_peta = dir_run / sumber_peta.name
                shutil.copy2(sumber_peta, tujuan_peta)
                info = layanan.InfoUnggahan(
                    kdprov=sumber_a.kdprov,
                    kdkab=sumber_a.kdkab,
                    layer_input=info_b.layer,
                    layer_peta=sumber_a.layer_peta,
                )
                run = layanan.buat_run(
                    sesi,
                    tipe=tipe_bersih,
                    info=info,
                    user=nama_user,
                    nama_input=nama_input_asli,
                    nama_peta=sumber_a.nama_file_peta,
                    berkas_input=berkas_input,
                    berkas_peta=tujuan_peta,
                    tanggal_data=tanggal_data,
                    sumber_run_a_id=sumber_a.id,
                )
    except KesalahanUnggahan as galat:
        shutil.rmtree(dir_run, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(galat)) from galat
    except HTTPException:
        shutil.rmtree(dir_run, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(dir_run, ignore_errors=True)
        raise

    if unggahan_dipakai:
        unggahan.hapus_unggahan(unggahan_dipakai, setelan)
    layanan.lengkapi_nomor_urut(sesi, [run])
    return run


@router.post("/geotag-master", response_model=MasterGeotagOut, status_code=201)
def unggah_master_geotag(
    kdprov: str = Form(..., description="Kode provinsi 2 digit, mis. 33"),
    kdkab: str = Form(..., description="Kode kabupaten/kota 4 digit, mis. 3307"),
    titik: UploadFile | None = File(
        None,
        description="Mode pengembangan/berkas kecil: berkas geotag asli kabupaten/kota",
    ),
    unggahan_id: str | None = Form(
        None, description="Id unggahan body mentah berjenis master yang sudah selesai"
    ),
    tanggal_data: date | None = Form(None, description="Tanggal data geotag (default: hari ini)"),
    layer: str | None = Form(None, description="Nama layer berkas geotag"),
    user: str | None = Form(None, description="Nama pengguna (diabaikan saat SSO aktif)"),
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> MasterGeotagOut:
    """Unggah geotag master per kabupaten/kota (admin provinsi).

    Berkas disimpan permanen di ``DIR_MASTER`` (tidak ikut pemangkasan run).
    Setiap unggahan menjadi versi terbaru untuk kabupaten/kota tersebut; run A
    yang sudah dibuat tetap memakai versi yang tercatat di run-nya.
    """
    try:
        kode = layanan.normalisasi_kode_kabupaten(kdprov, kdkab)
    except KesalahanUnggahan as galat:
        raise HTTPException(status_code=422, detail=str(galat)) from galat

    auth.pastikan_peran(pengguna, PERAN_ADMIN_PROVINSI)
    auth.pastikan_akses(pengguna, kode[:2], kode)
    if bool(unggahan_id) == bool(titik):
        raise HTTPException(
            status_code=422,
            detail="isi unggahan_id atau berkas multipart, tepat salah satu",
        )
    # Di mode dev, kolom form lama tetap dipakai agar tes/manual kompatibel.
    # Di production identitas selalu berasal dari token Bearer.
    nama_user = (
        (user or pengguna.nama) if setelan.auth_mode == "dev" else pengguna.nama
    )
    dir_master = Path(setelan.dir_master) / kode / uuid.uuid4().hex
    unggahan_dipakai: str | None = None
    try:
        if unggahan_id:
            sumber, meta_unggah = unggahan.ambil_berkas(
                unggahan_id, "master", pengguna, setelan
            )
            nama_berkas = str(meta_unggah["nama"])
            dir_master.mkdir(parents=True, exist_ok=True)
            berkas = dir_master / f"geotag_{nama_berkas}"
            shutil.copy2(sumber, berkas)
            unggahan_dipakai = unggahan_id
        else:
            berkas = _simpan_unggahan(titik, dir_master, "geotag")
            nama_berkas = Path(titik.filename or berkas.name).name
        info = layanan.periksa_master_geotag(berkas, layer, kode)
        master = layanan.buat_master(
            sesi,
            kdprov=kode[:2],
            kdkab=kode,
            tanggal_data=tanggal_data,
            nama_file=nama_berkas,
            berkas=berkas,
            layer=info.layer,
            jumlah_baris=info.jumlah_baris,
            user=nama_user,
        )
    except KesalahanUnggahan as galat:
        shutil.rmtree(dir_master, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(galat)) from galat
    except Exception:
        shutil.rmtree(dir_master, ignore_errors=True)
        raise

    if unggahan_dipakai:
        unggahan.hapus_unggahan(unggahan_dipakai, setelan)
    layanan.lengkapi_nomor_versi(sesi, [master])
    return MasterGeotagOut.model_validate(master)


@router.get("/geotag-master", response_model=DaftarMasterOut)
def daftar_master_geotag(
    kdprov: str | None = Query(None, description="Kode provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Kode kabupaten/kota 4 digit, mis. 3307"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> DaftarMasterOut:
    """Daftar versi geotag master (terbaru lebih dulu), dibatasi wilayah pengguna."""
    kdprov, kdkab = auth.saring_akses(pengguna, kdprov, kdkab)
    total, baris = layanan.daftar_master(
        sesi, kdprov=kdprov, kdkab=kdkab, limit=limit, offset=offset
    )
    layanan.lengkapi_nomor_versi(sesi, baris)
    return DaftarMasterOut(
        total=total, baris=[MasterGeotagOut.model_validate(satu) for satu in baris]
    )


@router.get("/runs", response_model=DaftarRunOut)
def daftar_run(
    tipe: str | None = Query(None, description=f"'{TIPE_A}' atau '{TIPE_B}'"),
    status: str | None = Query(None, description="menunggu/jalan/sukses/gagal"),
    kdprov: str | None = Query(None, description="Kode provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Kode kabupaten/kota, mis. 07"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> DaftarRunOut:
    """Daftar job terbaru lebih dulu (dengan penyaring dan paging), dibatasi wilayah."""
    kdprov, kdkab = auth.saring_akses(pengguna, kdprov, kdkab)
    total, daftar = layanan.daftar_run(
        sesi,
        tipe=tipe.strip().upper() if tipe else None,
        status=status,
        kdprov=kdprov,
        kdkab=kdkab,
        limit=limit,
        offset=offset,
    )
    layanan.lengkapi_nomor_urut(sesi, daftar)
    return DaftarRunOut(
        total=total, baris=[RunOut.model_validate(satu) for satu in daftar]
    )


@router.get("/ringkasan", response_model=RingkasanOut)
def ringkasan(
    tipe: str | None = Query(None, description=f"'{TIPE_A}' atau '{TIPE_B}'"),
    kdprov: str | None = Query(None, description="Saring satu provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Saring satu kabupaten/kota, mis. 07"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' (wilayah penugasan) atau 'posisi'"),
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> RingkasanOut:
    """Ringkasan provinsi: satu baris per kabupaten/kota (run terakhir tiap tipe).

    Angka dibaca dari ``rekap_kabupaten``; ``belum_ada_upload_tipe_b`` menandai
    kabupaten/kota yang belum pernah menerima unggahan Proses B.
    """
    kdprov, kdkab = auth.saring_akses(pengguna, kdprov, kdkab)
    return RingkasanOut.model_validate(
        layanan.ringkasan(
            sesi,
            tipe=tipe.strip().upper() if tipe else None,
            provinsi=kdprov,
            kdkab=kdkab,
            dasar=dasar,
        )
    )


@router.get("/progres-b", response_model=ProgresBOut)
def progres_b(
    kdprov: str | None = Query(None, description="Kode provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Kode kabupaten/kota, mis. 3307"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' atau 'posisi'"),
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> ProgresBOut:
    """Perjalanan Proses B satu kabupaten/kota terhadap target Proses A pertama."""
    kdprov, kdkab = auth.saring_akses(pengguna, kdprov, kdkab)
    if kdkab is None:
        raise HTTPException(status_code=422, detail="pilih kabupaten/kota untuk melihat progres")
    if kdprov is None:
        kdprov = kdkab[:2]
    return ProgresBOut.model_validate(
        layanan.progres_b(sesi, kdprov=kdprov, kdkab=kdkab, dasar=dasar)
    )


@router.get("/tabulasi-progres", response_model=TabulasiProgresOut)
def tabulasi_progres(
    tingkat: str = Query("kabupaten", description="'kabupaten', 'kecamatan', atau 'desa'"),
    kdprov: str | None = Query(None, description="Kode provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Kode kabupaten/kota, mis. 3307"),
    kdkec: str | None = Query(None, description="Kode kecamatan untuk tingkat desa"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' atau 'posisi'"),
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> TabulasiProgresOut:
    """Tabulasi target A pertama vs sisa B terakhir, satu tingkat per permintaan."""
    kdprov, kdkab = auth.saring_akses(pengguna, kdprov, kdkab)
    if kdprov is None:
        if kdkab:
            kdprov = kdkab[:2]
        else:
            raise HTTPException(status_code=422, detail="kdprov wajib diisi")
    if tingkat != "kabupaten" and kdkab is None:
        raise HTTPException(status_code=422, detail="pilih kabupaten/kota lebih dulu")
    try:
        data = layanan.tabulasi_progres(
            sesi,
            kdprov=kdprov,
            kdkab=kdkab,
            kdkec=kdkec,
            tingkat=tingkat,
            dasar=dasar,
        )
    except layanan.KesalahanPerubahan as galat:
        raise HTTPException(status_code=422, detail=str(galat)) from galat
    return TabulasiProgresOut.model_validate(data)


@router.get("/tren", response_model=TrenOut)
def tren(
    tingkat: str = Query("kabupaten", description="'kabupaten' atau 'provinsi'"),
    tipe: str | None = Query(None, description=f"'{TIPE_A}' atau '{TIPE_B}'"),
    kdprov: str | None = Query(None, description="Saring satu provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Saring satu kabupaten/kota, mis. 07"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' (wilayah penugasan) atau 'posisi'"),
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> TrenOut:
    """Tren progres per ``tanggal_data`` (run sukses terakhir pada tanggal itu)."""
    if tingkat not in ("kabupaten", "provinsi"):
        raise HTTPException(status_code=422, detail="tingkat tren harus 'kabupaten' atau 'provinsi'")
    kdprov, kdkab = auth.saring_akses(pengguna, kdprov, kdkab)
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
def status_run(
    run_id: int,
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> RunDetailOut:
    """Status satu job: status, waktu, pesan galat, jumlah hasil tersimpan.

    ``detail_tersedia`` = ``false`` berarti baris ``titik_hasil`` run ini sudah
    dipangkas (angka rekapnya tetap utuh).
    """
    run = _ambil_run(sesi, run_id)
    auth.pastikan_akses(pengguna, run.kdprov, run.kdkab)
    layanan.lengkapi_nomor_urut(sesi, [run])
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
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> HasilOut:
    """Baris hasil titik untuk satu job (paging, urut seperti keluaran Proses).

    Yang tersimpan hanya titik yang perlu perhatian; titik yang sudah benar tanpa
    tindakan manual tidak muncul di sini (terhitung di rekap).
    """
    run = _ambil_run(sesi, run_id)
    auth.pastikan_akses(pengguna, run.kdprov, run.kdkab)
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
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
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
    auth.pastikan_akses(pengguna, run.kdprov, run.kdkab)
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
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> PerubahanOut:
    """Perubahan antara dua run: selisih rekap kabupaten/desa + perubahan per titik.

    Selisih rekap bisa dihitung untuk pasangan run mana pun (keduanya harus sudah
    sukses); perubahan status per titik hanya untuk pasangan **baseline vs run
    sukses terakhir** pada kabupaten/kota+tipe yang sama.
    """
    awal = _ambil_run(sesi, run_awal)
    akhir = _ambil_run(sesi, run_akhir)
    auth.pastikan_akses(pengguna, awal.kdprov, awal.kdkab)
    auth.pastikan_akses(pengguna, akhir.kdprov, akhir.kdkab)
    try:
        hasil = layanan.perubahan(
            sesi, run_awal=awal, run_akhir=akhir, dasar=dasar, limit=limit, offset=offset
        )
    except KesalahanPerubahan as galat:
        raise HTTPException(status_code=409, detail=str(galat)) from galat
    return PerubahanOut.model_validate(hasil)


# --------------------------------------------------------------------- ekspor


def _kode_unduh(kdprov: str | None, kdkab: str | None) -> str:
    """Prefix 4 digit untuk nama berkas unduhan."""
    if kdkab:
        kode = layanan.kode_kabupaten(kdprov or "", kdkab)
        return kode if len(kode) == 4 else "0000"
    if kdprov:
        return f"{str(kdprov)[:2]}00"
    return "0000"


def _unduhan_csv(spool: BinaryIO, nama: str) -> StreamingResponse:
    """Balas spool CSV sebagai unduhan."""
    return StreamingResponse(
        ekspor.alirkan(spool),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nama}"'},
    )


def _unduhan_gpkg(berkas: Path, nama: str, hapus: bool = False) -> FileResponse:
    """Balas berkas GPKG sebagai unduhan (``hapus`` untuk berkas sementara)."""
    return FileResponse(
        berkas,
        media_type="application/geopackage+sqlite3",
        filename=nama,
        background=BackgroundTask(berkas.unlink, missing_ok=True) if hapus else None,
    )


@router.get("/runs/{run_id}/ekspor/hasil-a.gpkg", response_class=FileResponse)
def ekspor_hasil_a(
    run_id: int,
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> FileResponse:
    """Unduh keluaran Proses A sebagai GPKG (bahan edit di QGIS).

    Kolom dan urutannya sama dengan keluaran model QGIS. Hasil dihitung ulang dari
    berkas mentah run lalu di-cache (hanya beberapa berkas terbaru). Hanya tersedia
    untuk run Proses A yang sukses dan berkas mentahnya masih ada
    (baseline/sukses terakhir); selain itu HTTP 409.
    """
    run = _ambil_run(sesi, run_id)
    auth.pastikan_akses(pengguna, run.kdprov, run.kdkab)
    try:
        berkas = ekspor.berkas_hasil_a(run, setelan)
    except ekspor.EksporTidakTersedia as galat:
        raise HTTPException(status_code=409, detail=str(galat)) from galat
    kode = _kode_unduh(run.kdprov, run.kdkab)
    nomor = layanan.nomor_urut_run(sesi, [run]).get(run.id, run.id)
    return _unduhan_gpkg(
        berkas, f"{kode}_hasil_identifikasi_titik_ke{nomor}.gpkg"
    )


@router.get("/runs/{run_id}/ekspor/hasil-b.gpkg", response_class=FileResponse)
def ekspor_hasil_b(
    run_id: int,
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> FileResponse:
    """Unduh keluaran Proses B penuh sebagai GPKG, sama dengan layer QGIS."""
    run = _ambil_run(sesi, run_id)
    auth.pastikan_akses(pengguna, run.kdprov, run.kdkab)
    try:
        berkas = ekspor.berkas_hasil_b(run, setelan)
    except ekspor.EksporTidakTersedia as galat:
        raise HTTPException(status_code=409, detail=str(galat)) from galat
    kode = _kode_unduh(run.kdprov, run.kdkab)
    nomor = layanan.nomor_urut_run(sesi, [run]).get(run.id, run.id)
    return _unduhan_gpkg(
        berkas, f"{kode}_hasil_pengecekan_titik_ke{nomor}.gpkg"
    )


@router.get("/runs/{run_id}/ekspor/titik.csv", response_class=StreamingResponse)
def ekspor_titik_csv(
    run_id: int,
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> StreamingResponse:
    """Unduh titik perlu tindakan run ini sebagai CSV (dibaca dari ``titik_hasil``)."""
    run = _ambil_run(sesi, run_id)
    auth.pastikan_akses(pengguna, run.kdprov, run.kdkab)
    try:
        spool = ekspor.spool_titik_csv(sesi, run, setelan)
    except ekspor.EksporTidakTersedia as galat:
        raise HTTPException(status_code=409, detail=str(galat)) from galat
    kode = _kode_unduh(run.kdprov, run.kdkab)
    nomor = layanan.nomor_urut_run(sesi, [run]).get(run.id, run.id)
    return _unduhan_csv(
        spool, f"{kode}_titik_perlu_tindakan_ke{nomor}.csv"
    )


@router.get("/runs/{run_id}/ekspor/titik.gpkg", response_class=FileResponse)
def ekspor_titik_gpkg(
    run_id: int,
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> FileResponse:
    """Unduh titik perlu tindakan run ini sebagai GPKG (titik EPSG:4326)."""
    run = _ambil_run(sesi, run_id)
    auth.pastikan_akses(pengguna, run.kdprov, run.kdkab)
    try:
        berkas = ekspor.berkas_titik_gpkg(sesi, run, setelan)
    except ekspor.EksporTidakTersedia as galat:
        raise HTTPException(status_code=409, detail=str(galat)) from galat
    kode = _kode_unduh(run.kdprov, run.kdkab)
    nomor = layanan.nomor_urut_run(sesi, [run]).get(run.id, run.id)
    return _unduhan_gpkg(
        berkas,
        f"{kode}_titik_perlu_tindakan_ke{nomor}.gpkg",
        hapus=True,
    )


@router.get("/ekspor/rekap.csv", response_class=StreamingResponse)
def ekspor_rekap(
    tingkat: str = Query("kabupaten", description="'kabupaten' atau 'desa'"),
    tipe: str | None = Query(None, description=f"'{TIPE_A}' atau '{TIPE_B}'"),
    kdprov: str | None = Query(None, description="Saring satu provinsi, mis. 33"),
    kdkab: str | None = Query(None, description="Saring satu kabupaten/kota, mis. 07"),
    dasar: Dasar = Query(DASAR_TUGAS, description="'tugas' (wilayah penugasan) atau 'posisi'"),
    tanggal_awal: date | None = Query(None, description="Awal rentang tanggal data (termasuk)"),
    tanggal_akhir: date | None = Query(None, description="Akhir rentang tanggal data (termasuk)"),
    sesi: Session = Depends(get_session),
    setelan: Settings = Depends(get_settings),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> StreamingResponse:
    """Unduh rekap kabupaten/desa sebagai CSV.

    Satu baris per run per wilayah (semua run dalam rentang ``tanggal_data``),
    dengan kolom hitungan yang sama seperti endpoint rekap. Kategori tanpa wilayah
    dibalas kode kosong dan nama "(tanpa wilayah)".
    """
    tipe_bersih = tipe.strip().upper() if tipe else None
    if tipe_bersih is not None and tipe_bersih not in (TIPE_A, TIPE_B):
        raise HTTPException(
            status_code=422, detail=f"tipe harus '{TIPE_A}' atau '{TIPE_B}', bukan '{tipe}'"
        )
    kdprov, kdkab = auth.saring_akses(pengguna, kdprov, kdkab)
    try:
        spool = ekspor.spool_rekap_csv(
            sesi,
            setelan,
            tingkat=tingkat,
            tipe=tipe_bersih,
            kdprov=kdprov,
            kdkab=kdkab,
            dasar=dasar,
            tanggal_awal=tanggal_awal,
            tanggal_akhir=tanggal_akhir,
        )
    except ekspor.KesalahanSaringan as galat:
        raise HTTPException(status_code=422, detail=str(galat)) from galat
    kode = _kode_unduh(kdprov, kdkab)
    return _unduhan_csv(spool, f"{kode}_rekap_{tingkat}_{dasar}.csv")
