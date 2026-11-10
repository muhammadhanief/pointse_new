"""Endpoint modul Komunitas: berbagi error ``dataspasial.bps.go.id/gs`` & solusinya.

Petugas kabupaten/kota maupun admin provinsi dapat:
- Melaporkan pesan error ``.txt`` yang muncul saat unggah ke web GS Pusat
  (baik untuk Peta SLS 2026 S1, Peta SLS 2025 S2, maupun Geotagging),
  beserta solusi awal bila sudah ditemukan;
- Mencari apakah pesan error serupa sudah pernah dialami dan diselesaikan
  kabupaten/kota lain;
- Menekan "+1 Saya mengalami masalah serupa" agar provinsi mengetahui
  seberapa sering error tersebut terjadi;
- Berdiskusi dan menandai balasan sebagai Solusi Terverifikasi;
- Khusus Admin Provinsi: mengangkat topik menjadi calon/rule baru pada
  ``/proses/identifikasi`` (A), ``/proses/pengecekan`` (B), atau
  ``/proses/validasi`` (V).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import aktivitas, auth
from app.db import get_session
from app.layanan import kode_kabupaten
from app.models import (
    KOMUNITAS_KATEGORI_A,
    KOMUNITAS_KATEGORI_B,
    KOMUNITAS_KATEGORI_LAIN,
    KOMUNITAS_KATEGORI_V,
    KOMUNITAS_STATUS_JADI_RULE,
    KOMUNITAS_STATUS_TERBUKA,
    KOMUNITAS_STATUS_TERPECAHKAN,
    KomunitasDukungan,
    KomunitasKomentar,
    KomunitasTopik,
    sekarang,
)
from app.peran import PERAN_ADMIN_PROVINSI
from app.skema import (
    DaftarKomunitasTopikOut,
    KomunitasKomentarMasuk,
    KomunitasKomentarOut,
    KomunitasRuleMasuk,
    KomunitasTopikDetailOut,
    KomunitasTopikMasuk,
    KomunitasTopikOut,
)

router = APIRouter(prefix="/komunitas", tags=["komunitas"])

SEMUA_KATEGORI_KOMUNITAS = (
    KOMUNITAS_KATEGORI_V,
    KOMUNITAS_KATEGORI_A,
    KOMUNITAS_KATEGORI_B,
    KOMUNITAS_KATEGORI_LAIN,
)

SEMUA_STATUS_KOMUNITAS = (
    KOMUNITAS_STATUS_TERBUKA,
    KOMUNITAS_STATUS_TERPECAHKAN,
    KOMUNITAS_STATUS_JADI_RULE,
)

SEMUA_RULE_TARGET = (
    "identifikasi",
    "pengecekan",
    "validasi",
)


def _kdprov_pengguna(pengguna: auth.Pengguna) -> str:
    """Kembalikan kode provinsi pengguna (default '33' bila mode dev `*`)."""
    prov = (pengguna.kdprov or "").strip()
    return "33" if prov in ("", "*") else prov


def _kdkab_pengguna(pengguna: auth.Pengguna) -> str | None:
    """Normalisasi kode kabupaten pengguna ke 4 digit bila ada."""
    if not pengguna.kdkab:
        return None
    return kode_kabupaten(_kdprov_pengguna(pengguna), pengguna.kdkab)


def _nama_peran(pengguna: auth.Pengguna) -> str:
    return (
        pengguna.peran.nama
        if hasattr(pengguna.peran, "nama")
        else str(pengguna.peran)
    )


def _format_topik(
    topik: KomunitasTopik, *, didukung_saya: bool = False
) -> KomunitasTopikOut:
    return KomunitasTopikOut(
        id=topik.id,
        kdprov=topik.kdprov,
        kdkab=topik.kdkab,
        kategori=topik.kategori,
        judul=topik.judul,
        error_txt=topik.error_txt,
        deskripsi=topik.deskripsi,
        solusi_awal=topik.solusi_awal,
        status=topik.status,
        solusi_komentar_id=topik.solusi_komentar_id,
        rule_target=topik.rule_target,
        rule_catatan=topik.rule_catatan,
        rule_oleh=topik.rule_oleh,
        rule_pada=topik.rule_pada,
        jumlah_komentar=topik.jumlah_komentar,
        jumlah_dukungan=topik.jumlah_dukungan,
        didukung_saya=didukung_saya,
        oleh=topik.nama,
        username=topik.username,
        peran=topik.peran,
        created_at=topik.created_at,
        updated_at=topik.updated_at,
    )


def _format_komentar(komentar: KomunitasKomentar) -> KomunitasKomentarOut:
    return KomunitasKomentarOut(
        id=komentar.id,
        topik_id=komentar.topik_id,
        kdprov=komentar.kdprov,
        kdkab=komentar.kdkab,
        isi=komentar.isi,
        adalah_solusi=bool(komentar.adalah_solusi),
        oleh=komentar.nama,
        username=komentar.username,
        peran=komentar.peran,
        created_at=komentar.created_at,
    )


@router.get("/topik", response_model=DaftarKomunitasTopikOut)
def daftar_topik_komunitas(
    kategori: str | None = Query(None, description="peta_2026_s1/peta_2025_s2/geotagging/lainnya"),
    status: str | None = Query(None, description="terbuka/terpecahkan/jadi_rule"),
    rule_target: str | None = Query(None, description="identifikasi/pengecekan/validasi"),
    q: str | None = Query(None, description="kata kunci judul, deskripsi, atau potongan error txt"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> DaftarKomunitasTopikOut:
    """Daftar topik diskusi komunitas beserta ringkasan hitungan status."""
    kdprov = _kdprov_pengguna(pengguna)
    saring_prov = [KomunitasTopik.kdprov == kdprov]

    # Hitung rekap per status untuk seluruh provinsi ini
    hitungan_status: dict[str, int] = {}
    for st, jml in sesi.execute(
        select(KomunitasTopik.status, func.count())
        .where(*saring_prov)
        .group_by(KomunitasTopik.status)
    ):
        hitungan_status[str(st)] = int(jml)

    saring = list(saring_prov)
    if kategori:
        kat = kategori.strip().lower()
        if kat not in SEMUA_KATEGORI_KOMUNITAS:
            raise HTTPException(status_code=422, detail=f"kategori tidak dikenal: {kategori}")
        saring.append(KomunitasTopik.kategori == kat)
    if status:
        st_bersih = status.strip().lower()
        if st_bersih not in SEMUA_STATUS_KOMUNITAS:
            raise HTTPException(status_code=422, detail=f"status tidak dikenal: {status}")
        saring.append(KomunitasTopik.status == st_bersih)
    if rule_target:
        rt = rule_target.strip().lower()
        if rt not in SEMUA_RULE_TARGET:
            raise HTTPException(
                status_code=422, detail=f"rule_target tidak dikenal: {rule_target}"
            )
        saring.append(KomunitasTopik.rule_target == rt)
    if q and q.strip():
        pola = f"%{q.strip()}%"
        saring.append(
            or_(
                KomunitasTopik.judul.ilike(pola),
                KomunitasTopik.error_txt.ilike(pola),
                KomunitasTopik.deskripsi.ilike(pola),
                KomunitasTopik.solusi_awal.ilike(pola),
                KomunitasTopik.nama.ilike(pola),
                KomunitasTopik.kdkab.ilike(pola),
            )
        )

    total = int(
        sesi.scalar(select(func.count()).select_from(KomunitasTopik).where(*saring)) or 0
    )
    daftar = list(
        sesi.scalars(
            select(KomunitasTopik)
            .where(*saring)
            .order_by(KomunitasTopik.updated_at.desc(), KomunitasTopik.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )

    didukung_ids: set[int] = set()
    if daftar:
        didukung_ids = set(
            sesi.scalars(
                select(KomunitasDukungan.topik_id).where(
                    KomunitasDukungan.topik_id.in_([t.id for t in daftar]),
                    KomunitasDukungan.sub == pengguna.sub,
                )
            )
        )

    return DaftarKomunitasTopikOut(
        total=total,
        terbuka=hitungan_status.get(KOMUNITAS_STATUS_TERBUKA, 0),
        terpecahkan=hitungan_status.get(KOMUNITAS_STATUS_TERPECAHKAN, 0),
        jadi_rule=hitungan_status.get(KOMUNITAS_STATUS_JADI_RULE, 0),
        baris=[
            _format_topik(satu, didukung_saya=satu.id in didukung_ids)
            for satu in daftar
        ],
    )


@router.post("/topik", response_model=KomunitasTopikDetailOut, status_code=201)
def buat_topik_komunitas(
    permintaan: KomunitasTopikMasuk,
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> KomunitasTopikDetailOut:
    """Buat topik baru untuk berbagi error GS Pusat dan solusinya."""
    kategori = permintaan.kategori.strip().lower()
    if kategori not in SEMUA_KATEGORI_KOMUNITAS:
        raise HTTPException(
            status_code=422,
            detail=f"kategori harus salah satu dari {', '.join(SEMUA_KATEGORI_KOMUNITAS)}",
        )
    judul = permintaan.judul.strip()
    deskripsi = permintaan.deskripsi.strip()
    if not judul or not deskripsi:
        raise HTTPException(status_code=422, detail="judul dan deskripsi wajib diisi")

    error_txt = (permintaan.error_txt or "").strip() or None
    solusi_awal = (permintaan.solusi_awal or "").strip() or None
    status_awal = (
        KOMUNITAS_STATUS_TERPECAHKAN if solusi_awal else KOMUNITAS_STATUS_TERBUKA
    )

    waktu = sekarang()
    kdprov = _kdprov_pengguna(pengguna)
    kdkab = _kdkab_pengguna(pengguna)
    topik = KomunitasTopik(
        kdprov=kdprov,
        kdkab=kdkab,
        kategori=kategori,
        judul=judul,
        error_txt=error_txt,
        deskripsi=deskripsi,
        solusi_awal=solusi_awal,
        status=status_awal,
        jumlah_komentar=0,
        jumlah_dukungan=1,
        sub=pengguna.sub,
        username=pengguna.username,
        nama=pengguna.nama,
        nip=getattr(pengguna, "nip", None),
        peran=_nama_peran(pengguna),
        created_at=waktu,
        updated_at=waktu,
    )
    sesi.add(topik)
    sesi.flush()

    sesi.add(
        KomunitasDukungan(
            topik_id=topik.id,
            sub=pengguna.sub,
            nama=pengguna.nama,
            kdkab=kdkab,
            created_at=waktu,
        )
    )
    sesi.commit()
    sesi.refresh(topik)

    aktivitas.catat(
        sesi,
        pengguna,
        aksi="buat_topik_komunitas",
        objek="komunitas",
        objek_id=topik.id,
        detail=f"[{kategori}] {judul[:80]}",
    )
    dasar = _format_topik(topik, didukung_saya=True)
    return KomunitasTopikDetailOut(**dasar.model_dump(), komentar=[])


@router.get("/topik/{topik_id}", response_model=KomunitasTopikDetailOut)
def detail_topik_komunitas(
    topik_id: int,
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> KomunitasTopikDetailOut:
    """Ambil detail satu topik beserta daftar balasan/solusinya."""
    topik = sesi.get(KomunitasTopik, topik_id)
    if topik is None or topik.kdprov != _kdprov_pengguna(pengguna):
        raise HTTPException(status_code=404, detail="topik tidak ditemukan")

    didukung = (
        sesi.scalar(
            select(func.count())
            .select_from(KomunitasDukungan)
            .where(
                KomunitasDukungan.topik_id == topik.id,
                KomunitasDukungan.sub == pengguna.sub,
            )
        )
        or 0
    ) > 0
    komentar = list(
        sesi.scalars(
            select(KomunitasKomentar)
            .where(KomunitasKomentar.topik_id == topik.id)
            .order_by(
                KomunitasKomentar.adalah_solusi.desc(),
                KomunitasKomentar.created_at.asc(),
                KomunitasKomentar.id.asc(),
            )
        )
    )
    dasar = _format_topik(topik, didukung_saya=didukung)
    return KomunitasTopikDetailOut(
        **dasar.model_dump(),
        komentar=[_format_komentar(k) for k in komentar],
    )


@router.post("/topik/{topik_id}/komentar", response_model=KomunitasTopikDetailOut)
def tambah_komentar_komunitas(
    topik_id: int,
    permintaan: KomunitasKomentarMasuk,
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> KomunitasTopikDetailOut:
    """Tambahkan komentar atau solusi pada topik Komunitas."""
    topik = sesi.get(KomunitasTopik, topik_id)
    if topik is None or topik.kdprov != _kdprov_pengguna(pengguna):
        raise HTTPException(status_code=404, detail="topik tidak ditemukan")

    isi = permintaan.isi.strip()
    if not isi:
        raise HTTPException(status_code=422, detail="isi komentar wajib diisi")

    waktu = sekarang()
    boleh_tandai_solusi = (
        pengguna.sub == topik.sub or _nama_peran(pengguna) == PERAN_ADMIN_PROVINSI
    )
    jadikan_solusi = bool(permintaan.tandai_sebagai_solusi and boleh_tandai_solusi)

    if jadikan_solusi:
        for lama in sesi.scalars(
            select(KomunitasKomentar).where(KomunitasKomentar.topik_id == topik.id)
        ):
            lama.adalah_solusi = 0

    komentar = KomunitasKomentar(
        topik_id=topik.id,
        kdprov=_kdprov_pengguna(pengguna),
        kdkab=_kdkab_pengguna(pengguna),
        isi=isi,
        adalah_solusi=1 if jadikan_solusi else 0,
        sub=pengguna.sub,
        username=pengguna.username,
        nama=pengguna.nama,
        nip=getattr(pengguna, "nip", None),
        peran=_nama_peran(pengguna),
        created_at=waktu,
    )
    sesi.add(komentar)
    sesi.flush()

    topik.jumlah_komentar = int(
        sesi.scalar(
            select(func.count())
            .select_from(KomunitasKomentar)
            .where(KomunitasKomentar.topik_id == topik.id)
        )
        or 0
    )
    if jadikan_solusi:
        topik.solusi_komentar_id = komentar.id
        if topik.status == KOMUNITAS_STATUS_TERBUKA:
            topik.status = KOMUNITAS_STATUS_TERPECAHKAN
    topik.updated_at = waktu
    sesi.commit()

    return detail_topik_komunitas(topik_id, sesi=sesi, pengguna=pengguna)


@router.post(
    "/topik/{topik_id}/komentar/{komentar_id}/solusi",
    response_model=KomunitasTopikDetailOut,
)
def tandai_solusi_komunitas(
    topik_id: int,
    komentar_id: int,
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> KomunitasTopikDetailOut:
    """Tandai atau batalkan satu komentar sebagai Solusi Terverifikasi.

    Hanya pembuat topik atau Admin Provinsi yang dapat menandai solusi.
    """
    topik = sesi.get(KomunitasTopik, topik_id)
    if topik is None or topik.kdprov != _kdprov_pengguna(pengguna):
        raise HTTPException(status_code=404, detail="topik tidak ditemukan")
    if pengguna.sub != topik.sub and _nama_peran(pengguna) != PERAN_ADMIN_PROVINSI:
        raise HTTPException(
            status_code=403,
            detail="hanya pembuat topik atau Admin Provinsi yang dapat menandai solusi",
        )
    target = sesi.get(KomunitasKomentar, komentar_id)
    if target is None or target.topik_id != topik.id:
        raise HTTPException(status_code=404, detail="komentar tidak ditemukan")

    sedang_solusi = bool(target.adalah_solusi)
    for k in sesi.scalars(
        select(KomunitasKomentar).where(KomunitasKomentar.topik_id == topik.id)
    ):
        k.adalah_solusi = 0

    if sedang_solusi:
        topik.solusi_komentar_id = None
        if topik.status == KOMUNITAS_STATUS_TERPECAHKAN and not topik.solusi_awal:
            topik.status = KOMUNITAS_STATUS_TERBUKA
    else:
        target.adalah_solusi = 1
        topik.solusi_komentar_id = target.id
        if topik.status == KOMUNITAS_STATUS_TERBUKA:
            topik.status = KOMUNITAS_STATUS_TERPECAHKAN

    topik.updated_at = sekarang()
    sesi.commit()
    return detail_topik_komunitas(topik_id, sesi=sesi, pengguna=pengguna)


@router.post("/topik/{topik_id}/dukungan", response_model=KomunitasTopikDetailOut)
def toggle_dukungan_komunitas(
    topik_id: int,
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> KomunitasTopikDetailOut:
    """Tambah/batalkan tanda '+1 Saya mengalami masalah serupa'."""
    topik = sesi.get(KomunitasTopik, topik_id)
    if topik is None or topik.kdprov != _kdprov_pengguna(pengguna):
        raise HTTPException(status_code=404, detail="topik tidak ditemukan")

    ada = sesi.scalar(
        select(KomunitasDukungan).where(
            KomunitasDukungan.topik_id == topik.id,
            KomunitasDukungan.sub == pengguna.sub,
        )
    )
    if ada is not None:
        sesi.delete(ada)
    else:
        sesi.add(
            KomunitasDukungan(
                topik_id=topik.id,
                sub=pengguna.sub,
                nama=pengguna.nama,
                kdkab=_kdkab_pengguna(pengguna),
                created_at=sekarang(),
            )
        )
    sesi.flush()
    topik.jumlah_dukungan = int(
        sesi.scalar(
            select(func.count())
            .select_from(KomunitasDukungan)
            .where(KomunitasDukungan.topik_id == topik.id)
        )
        or 0
    )
    sesi.commit()
    return detail_topik_komunitas(topik_id, sesi=sesi, pengguna=pengguna)


@router.post("/topik/{topik_id}/rule", response_model=KomunitasTopikDetailOut)
def atur_rule_komunitas(
    topik_id: int,
    permintaan: KomunitasRuleMasuk,
    sesi: Session = Depends(get_session),
    pengguna: auth.Pengguna = Depends(auth.pengguna_saat_ini),
) -> KomunitasTopikDetailOut:
    """Khusus Admin Provinsi: ubah status topik dan tetapkan target rule PointSE."""
    auth.pastikan_peran(pengguna, PERAN_ADMIN_PROVINSI)
    topik = sesi.get(KomunitasTopik, topik_id)
    if topik is None or topik.kdprov != _kdprov_pengguna(pengguna):
        raise HTTPException(status_code=404, detail="topik tidak ditemukan")

    status = permintaan.status.strip().lower()
    if status not in SEMUA_STATUS_KOMUNITAS:
        raise HTTPException(
            status_code=422,
            detail=f"status harus salah satu dari {', '.join(SEMUA_STATUS_KOMUNITAS)}",
        )
    rule_target = (permintaan.rule_target or "").strip().lower() or None
    if rule_target is not None and rule_target not in SEMUA_RULE_TARGET:
        raise HTTPException(
            status_code=422,
            detail=f"rule_target harus salah satu dari {', '.join(SEMUA_RULE_TARGET)}",
        )
    if status == KOMUNITAS_STATUS_JADI_RULE and not rule_target:
        raise HTTPException(
            status_code=422,
            detail="pilih modul target rule (identifikasi, pengecekan, atau validasi)",
        )

    waktu = sekarang()
    topik.status = status
    topik.rule_target = rule_target
    topik.rule_catatan = (permintaan.rule_catatan or "").strip() or None
    if rule_target or status == KOMUNITAS_STATUS_JADI_RULE:
        topik.rule_oleh = pengguna.nama
        topik.rule_pada = waktu
    else:
        topik.rule_oleh = None
        topik.rule_pada = None
    topik.updated_at = waktu
    sesi.commit()

    aktivitas.catat(
        sesi,
        pengguna,
        aksi="atur_rule_komunitas",
        objek="komunitas",
        objek_id=topik.id,
        detail=f"status={status} rule_target={rule_target or '-'}",
    )
    return detail_topik_komunitas(topik_id, sesi=sesi, pengguna=pengguna)
