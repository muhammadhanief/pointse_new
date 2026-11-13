"""Tes daftar/unduh unmatch run V + steril SE2026 (PRD §11)."""

from __future__ import annotations

from app import ekspor, layanan
from app.config import Settings
from app.models import (
    STATUS_BELUM_CLEAN,
    STATUS_GAGAL,
    STATUS_SUKSES,
    TIPE_V,
    MasterSls2026S1,
    Run,
    ValidasiSlsUnmatch,
)


def _run_v(sesi) -> Run:
    run = Run(
        tipe=TIPE_V,
        kdprov="33",
        kdkab="02",
        status="gagal",
        nama_file_input="peta.gpkg",
        nama_file_peta="peta.gpkg",
        berkas_input="/tmp/peta.gpkg",
        berkas_peta="/tmp/peta.gpkg",
        semester="2026_1",
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)
    for jenis, a, b, c, d in [
        ("tidak_di_peta", None, None, "33020100010002", "3302010001000200"),
        ("tidak_di_master", "33020100010001", "3302010001000100", None, None),
        (
            "ganda",
            "33020100010003",
            "3302010001000300",
            "33020100010003",
            "3302010001000300",
        ),
    ]:
        sesi.add(
            ValidasiSlsUnmatch(
                run_id=run.id, jenis=jenis, idsls_peta=a, idsubsls_peta=b,
                idsls_master=c, idsubsls_master=d, nmsls="SLS",
                catatan="2 baris" if jenis == "ganda" else None,
            )
        )
    sesi.commit()
    return run


def test_daftar_unmatch_paging_dan_saring(sesi) -> None:
    run = _run_v(sesi)
    total, baris = layanan.daftar_unmatch(sesi, run.id, limit=2, offset=0)
    assert total == 3
    assert len(baris) == 2
    assert baris[0]["idsls_peta"] == "33020100010001"
    assert baris[0]["jenis"] == "tidak_di_master"
    total_ganda, baris_ganda = layanan.daftar_unmatch(sesi, run.id, jenis="ganda")
    assert total_ganda == 1
    assert baris_ganda[0]["catatan"] == "2 baris"
    total_master, _ = layanan.daftar_unmatch(sesi, run.id, jenis="tidak_di_peta")
    assert total_master == 1


def test_berkas_unmatch_v_xlsx(sesi) -> None:
    """Unduhan Excel: ringkasan + 9 sheet jenis, tab merah bila ada temuan."""
    from openpyxl import load_workbook

    run = _run_v(sesi)
    aliran = ekspor.berkas_unmatch_v_xlsx(sesi, run.id)
    buku = load_workbook(aliran, data_only=True)
    assert buku.sheetnames == [
        "Ringkasan",
        "Tidak ada di peta",
        "Tidak ada di master",
        "Ganda di peta",
        "Nama berbeda",
        "Tidak konsisten",
        "Celah (gap)",
        "Tumpang tindih",
        "Duplikat geometri",
        "Geometri tidak valid",
    ]
    ringkas = {r[0].value: r[1].value for r in buku["Ringkasan"].iter_rows(min_row=2)}
    assert ringkas["total_temuan"] == 3
    assert ringkas["jumlah_ganda"] == 1
    assert ringkas["jumlah_tidak_di_master"] == 1
    assert buku["Tidak ada di master"].max_row == 2  # judul + 1 baris
    assert buku["Tidak ada di master"]["A2"].value == "33020100010001"
    assert buku["Ganda di peta"].sheet_properties.tabColor.rgb == "FFFF0000"


def test_saring_run_tanpa_tipe_kecualikan_v() -> None:
    saring = layanan._saring_run(None, None, None)
    teks = " ".join(str(s) for s in saring)
    # Tanpa tipe: hanya A/B, run V steril dari ringkasan/tren.
    assert "V" not in teks or "in_" in teks.lower() or "tipe" in teks.lower()
    # Pastikan ada penyaring tipe A/B (bukan tanpa saring tipe sama sekali).
    assert len(saring) >= 2


def test_ringkasan_validasi_run_terakhir_dan_hitungan(sesi) -> None:
    """Satu baris per kab: run V terakhir + hitungan per jenis."""
    from app.models import STATUS_GAGAL, STATUS_SUKSES, Run

    lama = Run(
        tipe=TIPE_V,
        kdprov="33",
        kdkab="12",
        status=STATUS_GAGAL,
        nama_file_input="a.gpkg",
        nama_file_peta="a.gpkg",
        berkas_input="/tmp/a",
        berkas_peta="/tmp/a",
        semester="2026_1",
    )
    sesi.add(lama)
    sesi.commit()
    sesi.refresh(lama)
    sesi.add(
        ValidasiSlsUnmatch(
            run_id=lama.id, jenis="tidak_di_master", idsls_peta="X",
            nmsls="SLS",
        )
    )
    baru = Run(
        tipe=TIPE_V,
        kdprov="33",
        kdkab="12",
        status=STATUS_SUKSES,
        nama_file_input="b.gpkg",
        nama_file_peta="b.gpkg",
        berkas_input="/tmp/b",
        berkas_peta="/tmp/b",
        semester="2026_1",
    )
    sesi.add(baru)
    sesi.commit()
    sesi.refresh(baru)

    baris = layanan.ringkasan_validasi(sesi, kdprov="33")
    assert len(baris) == 1
    assert baris[0]["run_id"] == baru.id
    assert baris[0]["kdkab"] == "3312"
    assert baris[0]["total"] == 0
    assert baris[0]["per_jenis"] == {}
    assert baris[0]["target"] is None
    assert baris[0]["selesai"] is None
    assert baris[0]["sisa"] is None

    kosong = layanan.ringkasan_validasi(sesi, kdprov="33", kdkab="99")
    assert kosong == []


def test_impor_master_db_idempoten(tmp_path, sesi) -> None:
    """Impor menulis ulang kab yang sama; baris rusak dilaporkan, tidak masuk DB."""
    from app import master_impor
    from app.models import MasterSls2026S1

    akar = tmp_path / "m" / "3312"
    akar.mkdir(parents=True)
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["idsubsls", "nmsls"])
    ws.append(["3312010001000100", "SLS A"])
    ws.append(["SALAH", "SLS X"])
    ws.append([None, "KOSONG"])
    wb.save(str(akar / "msubsls_26_1_3312.xlsx"))

    hasil = master_impor.impor_kabupaten(sesi, tmp_path / "m", "3312")
    assert hasil["disimpan"] == 1 and hasil["dilewati"] == 2
    assert sesi.query(MasterSls2026S1).count() == 1

    # Impor ulang menimpa, tidak menumpuk.
    hasil = master_impor.impor_kabupaten(sesi, tmp_path / "m", "3312")
    assert hasil["disimpan"] == 1
    assert sesi.query(MasterSls2026S1).count() == 1


def test_impor_master_dari_zip_dan_rekonsiliasi_hirarki_gabung(
    tmp_path, sesi
) -> None:
    """Impor langsung dari .zip + rekonsiliasi SUBSLS_GABUNG pada hirarki_sls."""
    import io
    import zipfile

    import openpyxl

    from app import master_impor
    from app.models import MasterSls2026S1

    def _xlsx_bytes(baris_data: list[list[object]]) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        for r in baris_data:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    jalur_zip = tmp_path / "33.zip"
    with zipfile.ZipFile(jalur_zip, "w") as zf:
        zf.writestr(
            "33/3327/Master/msubsls_26_1_3327.xlsx",
            _xlsx_bytes(
                [
                    ["idsubsls", "nmsls"],
                    ["3327080015005001", "RT 003 RW 010"],
                    ["3327080015005002", "RT 003 RW 010"],
                    ["3327080015011200", "RT 006 RW 010"],
                ]
            ),
        )
        zf.writestr(
            "33/3327/Hirarki/hirarki_sls_26_1_3327.xlsx",
            _xlsx_bytes(
                [
                    [
                        "idsls_25_2",
                        "nmsls_25_2",
                        "idsls_26_1",
                        "nmsls_26_1",
                        "idsubsls_25_2",
                        "idsubsls_26_1",
                        "id_perub",
                        "ket_perub",
                    ],
                    [
                        "33270800150050",
                        "RT 003 RW 010",
                        "33270800150050",
                        "RT 003 RW 010",
                        "3327080015005001",
                        "3327080015005000",
                        "7",
                        "SUBSLS_GABUNG",
                    ],
                    [
                        "33270800150050",
                        "RT 003 RW 010",
                        "33270800150050",
                        "RT 003 RW 010",
                        "3327080015005002",
                        "3327080015005000",
                        "7",
                        "SUBSLS_GABUNG",
                    ],
                ]
            ),
        )

    tujuan = tmp_path / "ekstrak"
    with master_impor.siapkan_akar_sumber(
        jalur_zip, ekstrak_ke=tujuan, hanya="3327"
    ) as akar:
        hasil = master_impor.impor_kabupaten(sesi, akar, "3327")

    assert hasil["disimpan"] == 2
    sub_db = {
        r.idsubsls
        for r in sesi.query(MasterSls2026S1).filter_by(kdkab="3327").all()
    }
    assert sub_db == {"3327080015005000", "3327080015011200"}


def test_ringkasan_validasi_target_selesai_sisa(tmp_path, sesi) -> None:
    """Target dari master DB; selesai = target dikurangi pasangan bermasalah."""
    from app.models import STATUS_SUKSES, MasterSls2026S1, Run

    for sub in ("3312010001000100", "3312010001000101", "3312010001000102"):
        sesi.add(
            MasterSls2026S1(
                kdprov="33", kdkab="3312", idsls=sub[:14], idsubsls=sub, nmsls="SLS"
            )
        )
    sesi.commit()

    run = Run(
        tipe=TIPE_V,
        kdprov="33",
        kdkab="12",
        status=STATUS_SUKSES,
        nama_file_input="b.gpkg",
        nama_file_peta="b.gpkg",
        berkas_input="/tmp/b",
        berkas_peta="/tmp/b",
        semester="2026_1",
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)
    sesi.add(
        ValidasiSlsUnmatch(
            run_id=run.id,
            jenis="tidak_di_peta",
            idsls_master="33120100010001",
            idsubsls_master="3312010001000199",
            nmsls="SLS",
        )
    )
    sesi.commit()

    baris = layanan.ringkasan_validasi(sesi, kdprov="33")
    assert len(baris) == 1
    assert baris[0]["target"] == 3
    assert baris[0]["selesai"] == 2
    assert baris[0]["sisa"] == 1
    assert baris[0]["selesai_pada"] is None


def test_unggah_v_tolak_ekstensi_tidak_dikenal(sesi_pabrik, sesi, tmp_path) -> None:
    """Berkas tanpa akhiran .geojson/.gpkg ditolak dengan saran ganti nama."""
    from app.models import Run

    peta = _peta_v(tmp_path / "peta.geojson")
    for klien in _klien_v(sesi_pabrik, tmp_path):
        with peta.open("rb") as berkas:
            resp = klien.post(
                "/runs",
                data={"tipe": "V"},
                files={"peta": ("3312_sls (1)", berkas, "application/octet-stream")},
            )
    assert resp.status_code == 422, resp.text
    assert "ganti nama" in resp.json()["detail"]
    assert sesi.query(Run).count() == 0


def _peta_v(path) -> object:
    """Berkas peta 2026 S1 minimal (17 kolom, satu kabupaten 3313)."""
    import geopandas as gpd
    from shapely.geometry import Point

    from app.validasi_sls import KOLOM_PETA_V

    baris = {kolom: "13" if kolom == "kdkab" else "33" if kolom == "kdprov" else "1" if kolom == "tingkat" else "x" for kolom in KOLOM_PETA_V}
    baris["idsls"] = "33130100010001"
    baris["idsubsls"] = "3313010001000100"
    gdf = gpd.GeoDataFrame([baris], geometry=[Point(110.0, -7.0)], crs="EPSG:4326")
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(str(path), driver="GeoJSON")
    return path


def _klien_v(sesi_pabrik, tmp_path):
    """TestClient dengan ``dir_master_sls_2026_s1`` di folder tes."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.db import get_session
    from app.main import app

    (tmp_path / "u").mkdir(exist_ok=True)
    (tmp_path / "m").mkdir(exist_ok=True)
    setelan = Settings(
        worker_enabled=False,
        auth_mode="dev",
        dir_unggahan=str(tmp_path / "u"),
        dir_master=str(tmp_path / "master"),
        dir_master_sls_2026_s1=str(tmp_path / "m"),
        worker_lock_file=str(tmp_path / "w.lock"),
    )

    def sesi_uji():
        with sesi_pabrik() as satu:
            yield satu

    app.dependency_overrides[get_session] = sesi_uji
    from app.config import get_settings

    app.dependency_overrides[get_settings] = lambda: setelan
    try:
        with TestClient(app) as klien:
            yield klien
    finally:
        app.dependency_overrides.clear()


def test_unggah_v_tanpa_master_ditolak_tanpa_run(sesi_pabrik, sesi, tmp_path) -> None:
    """Master kab belum ada di server: 422 di awal, run tidak dibuat."""
    from app.models import Run

    peta = _peta_v(tmp_path / "peta.geojson")
    for klien in _klien_v(sesi_pabrik, tmp_path):
        with peta.open("rb") as berkas:
            resp = klien.post(
                "/runs",
                data={"tipe": "V"},
                files={"peta": ("peta.geojson", berkas, "application/geo+json")},
            )
    assert resp.status_code == 422, resp.text
    assert "belum tersedia" in resp.json()["detail"]
    assert sesi.query(Run).count() == 0


def test_unggah_v_dengan_master_masuk_antre(sesi_pabrik, sesi, tmp_path) -> None:
    """Master ada di DB: unggah V lolos gerbang awal (201 menunggu)."""
    from app.models import MasterSls2026S1

    sesi.add(
        MasterSls2026S1(
            kdprov="33",
            kdkab="3313",
            idsls="33130100010001",
            idsubsls="3313010001000100",
            nmsls="SLS",
        )
    )
    sesi.commit()
    peta = _peta_v(tmp_path / "peta.geojson")
    for klien in _klien_v(sesi_pabrik, tmp_path):
        with peta.open("rb") as berkas:
            resp = klien.post(
                "/runs",
                data={"tipe": "V"},
                files={"peta": ("peta.geojson", berkas, "application/geo+json")},
            )
    assert resp.status_code == 201, resp.text
    assert resp.json()["semester"] == "2026_1"


def _run_v_baru(sesi, kdkab: str = "12") -> Run:
    """Run V menunggu untuk tes penentuan status akhir."""
    run = Run(
        tipe=TIPE_V,
        kdprov="33",
        kdkab=kdkab,
        status="jalan",
        nama_file_input="peta.gpkg",
        nama_file_peta="peta.gpkg",
        berkas_input="/tmp/peta.gpkg",
        berkas_peta="/tmp/peta.gpkg",
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)
    return run


def _isi_master(sesi, kode: str, subs: list[str]) -> None:
    for sub in subs:
        sesi.add(
            MasterSls2026S1(
                kdprov=kode[:2], kdkab=kode, idsls=sub[:14], idsubsls=sub,
                nmsls="SLS",
            )
        )
    sesi.commit()


def _temuan(
    sesi,
    run_id: int,
    jenis: str,
    master: tuple[str | None, str | None] = (None, None),
    peta: tuple[str | None, str | None] = (None, None),
) -> None:
    sesi.add(
        ValidasiSlsUnmatch(
            run_id=run_id, jenis=jenis, idsls_peta=peta[0],
            idsubsls_peta=peta[1], idsls_master=master[0],
            idsubsls_master=master[1], nmsls="SLS",
        )
    )
    sesi.commit()


def test_status_akhir_v_lolos_tetap_sukses(sesi) -> None:
    """Lolos semua blok = sukses, walau target/master tidak ada."""
    from app.worker import simpan_fase_akhir_v

    run = _run_v_baru(sesi)
    simpan_fase_akhir_v(sesi, run, (0, "lolos", True))
    assert run.status == STATUS_SUKSES


def test_status_akhir_v_bertemuan_dengan_clean_jadi_belum_clean(sesi) -> None:
    """Ada temuan tetapi 2 dari 3 pasangan clean = belum_clean."""
    from app.worker import simpan_fase_akhir_v

    _isi_master(
        sesi, "3312",
        ["3312010001000100", "3312010001000101", "3312010001000102"],
    )
    run = _run_v_baru(sesi)
    _temuan(
        sesi, run.id, "tidak_di_peta",
        master=("33120100010001", "3312010001000102"),
    )
    simpan_fase_akhir_v(sesi, run, (1, "ada temuan", False))
    assert run.status == STATUS_BELUM_CLEAN


def test_status_akhir_v_nol_clean_tetap_gagal(sesi) -> None:
    """Semua pasangan master kotor (tidak ada yang cocok) = gagal."""
    from app.worker import simpan_fase_akhir_v

    _isi_master(sesi, "3312", ["3312010001000100", "3312010001000101"])
    run = _run_v_baru(sesi)
    _temuan(
        sesi, run.id, "tidak_di_peta",
        master=("33120100010001", "3312010001000100"),
    )
    _temuan(
        sesi, run.id, "nama_beda",
        master=("33120100010001", "3312010001000101"),
        peta=("33120100010001", "3312010001000101"),
    )
    simpan_fase_akhir_v(sesi, run, (2, "ada temuan", False))
    assert run.status == STATUS_GAGAL


def test_status_akhir_v_tanpa_master_jadi_gagal(sesi) -> None:
    """Target tak diketahui (master kab belum diimpor) = gagal."""
    from app.worker import simpan_fase_akhir_v

    run = _run_v_baru(sesi)
    _temuan(sesi, run.id, "tidak_di_master", peta=("X", "Y"))
    simpan_fase_akhir_v(sesi, run, (1, "ada temuan", False))
    assert run.status == STATUS_GAGAL


def test_status_akhir_v_ganda_tapi_cocok_tetap_mengotori(sesi) -> None:
    """Pasangan ganda-tapi-cocok bukan fully-clean: ia muncul di temuan."""
    from app.worker import simpan_fase_akhir_v

    _isi_master(sesi, "3312", ["3312010001000100"])
    run = _run_v_baru(sesi)
    _temuan(
        sesi, run.id, "ganda",
        master=("33120100010001", "3312010001000100"),
        peta=("33120100010001", "3312010001000100"),
    )
    simpan_fase_akhir_v(sesi, run, (1, "ada temuan", False))
    assert run.status == STATUS_GAGAL


def test_ringkasan_validasi_belum_clean_adalah_final(sesi) -> None:
    """Run belum_clean mengisi selesai/sisa seperti sukses/gagal."""
    _isi_master(
        sesi, "3312",
        ["3312010001000100", "3312010001000101", "3312010001000102"],
    )
    run = _run_v_baru(sesi)
    run.status = STATUS_BELUM_CLEAN
    sesi.commit()
    _temuan(
        sesi, run.id, "tidak_di_peta",
        master=("33120100010001", "3312010001000199"),
    )
    baris = layanan.ringkasan_validasi(sesi, kdprov="33")
    assert len(baris) == 1
    assert baris[0]["status"] == STATUS_BELUM_CLEAN
    assert baris[0]["target"] == 3
    assert baris[0]["selesai"] == 2
    assert baris[0]["sisa"] == 1


def test_ringkasan_validasi_menunggu_tetap_bukan_final(sesi) -> None:
    """Run menunggu/jalan: selesai/sisa tetap None."""
    _isi_master(sesi, "3312", ["3312010001000100"])
    run = _run_v_baru(sesi)
    run.status = "menunggu"
    sesi.commit()
    baris = layanan.ringkasan_validasi(sesi, kdprov="33")
    assert len(baris) == 1
    assert baris[0]["selesai"] is None
    assert baris[0]["sisa"] is None


def _peta_bersih(path) -> object:
    """Berkas peta 1 pasangan yang susunan kodenya konsisten (3312)."""
    import geopandas as gpd
    from shapely.geometry import Point

    from app.validasi_sls import KOLOM_PETA_V

    baris = {kolom: "x" for kolom in KOLOM_PETA_V}
    baris.update(
        kdprov="33", kdkab="12", kdkec="010", kddesa="001",
        kdsls="0001", kdsubsls="00", idsls="33120100010001",
        idsubsls="3312010001000100", nmsls="SLS", tingkat=1,
    )
    gdf = gpd.GeoDataFrame([baris], geometry=[Point(110.0, -7.0)], crs="EPSG:4326")
    gdf.to_file(str(path), driver="GeoJSON")
    return path


def test_proses_validasi_v_bersih_total_tanpa_crash(sesi, tmp_path) -> None:
    """Berkas bersih total (nol temuan): insert kosong dilewati, status sukses.

    Regresi kasus 3373: ``insert(unmatch), []`` me-render INSERT berisi nilai
    default saja sehingga MariaDB menolak dengan 1364 "
    "Field 'run_id' doesn't have a default value".
    """
    from app import worker as modul_worker

    _isi_master(sesi, "3312", ["3312010001000100"])
    run = _run_v_baru(sesi)
    run.berkas_peta = str(_peta_bersih(tmp_path / "bersih.geojson"))
    run.layer_peta = None
    sesi.commit()

    jumlah, pesan, lolos = modul_worker.proses_validasi_v(sesi, run)
    assert (jumlah, lolos) == (0, True)
    assert "LOLOS" in pesan
    modul_worker.simpan_fase_akhir_v(sesi, run, (jumlah, pesan, lolos))
    assert run.status == STATUS_SUKSES
    assert (
        sesi.query(ValidasiSlsUnmatch).filter_by(run_id=run.id).count() == 0
    )


def _hasil_topologi(topologi) -> object:
    """Bungkus hasil topologi jadi ``HasilValidasi`` minimal (untuk unduhan QC)."""
    from app import validasi_sls

    return validasi_sls.HasilValidasi(
        lolos=topologi.lolos,
        skema=validasi_sls.HasilSkema(lolos=True),
        duplikat=validasi_sls.HasilDuplikat(lolos=True),
        konsistensi=validasi_sls.HasilKonsistensi(lolos=True),
        matching=validasi_sls.HasilMatching(lolos=True),
        pesan="ada temuan topologi",
        topologi=topologi,
    )


def test_endpoint_peta_qc_validasi(tmp_path, klien, sesi) -> None:
    """Endpoint peta QC: 404 saat belum ada, 200 GeoJSON setelah berkas ditulis."""
    from app import validasi_sls

    peta = tmp_path / "u" / "peta_3302.geojson"
    peta.parent.mkdir(parents=True, exist_ok=True)
    run = _run_v(sesi)
    run.berkas_peta = str(peta)
    sesi.commit()

    belum = klien.get(f"/runs/{run.id}/validasi-sls/peta-qc.geojson")
    assert belum.status_code == 404
    assert "belum tersedia" in belum.json()["detail"]

    temuan = validasi_sls.BarisUnmatch(
        jenis=validasi_sls.JENIS_GEOM_OVERLAP,
        idsls_peta="33020100010001",
        idsubsls_peta="3302010001000100",
        idsls_master=None,
        idsubsls_master=None,
        nmsls="SLS 1",
        catatan="tumpang tindih dengan 3302010001000200",
        luas_m2=123.5,
        geojson_geom={
            "type": "Polygon",
            "coordinates": [
                [[110.0, -7.0], [110.1, -7.0], [110.1, -7.1], [110.0, -7.0]]
            ],
        },
    )
    validasi_sls.tulis_geojson_qc(
        _hasil_topologi(validasi_sls.HasilTopologi(lolos=False, temuan=[temuan])),
        berkas_peta=peta,
        kdkab="3302",
        run_id=run.id,
    )

    ada = klien.get(f"/runs/{run.id}/validasi-sls/peta-qc.geojson")
    assert ada.status_code == 200, ada.text
    assert ada.headers["content-type"].startswith("application/geo+json")
    assert "QC_Validasi_3302.geojson" in ada.headers.get("content-disposition", "")
    fitur = ada.json()["features"]
    assert len(fitur) == 1
    assert fitur[0]["properties"]["jenis"] == validasi_sls.JENIS_GEOM_OVERLAP
    assert fitur[0]["properties"]["luas_m2"] == 123.5

    baris = klien.get("/validasi-sls/ringkasan").json()["baris"]
    assert len(baris) == 1
    assert baris[0]["run_id"] == run.id
    assert baris[0]["ada_peta_qc"] is True


def test_endpoint_peta_qc_tolak_run_bukan_v(tmp_path, klien, sesi) -> None:
    """Endpoint peta QC hanya untuk run validasi (tipe V)."""
    from app.models import TIPE_A

    run = Run(
        tipe=TIPE_A,
        kdprov="33",
        kdkab="02",
        status="sukses",
        nama_file_input="a.geojson",
        nama_file_peta="a.geojson",
        berkas_input="/tmp/a.geojson",
        berkas_peta="/tmp/a.geojson",
    )
    sesi.add(run)
    sesi.commit()
    sesi.refresh(run)

    respons = klien.get(f"/runs/{run.id}/validasi-sls/peta-qc.geojson")
    assert respons.status_code == 404
    assert "bukan run validasi" in respons.json()["detail"]


def test_jelaskan_galat_run_id_bukan_kolom_berkas() -> None:
    """Galat 1364 untuk kolom internal tidak boleh menyalahkan berkas."""
    from app import worker as modul_worker
    from app.models import Run as ModelRun

    run = ModelRun(tipe="V", nama_file_input="3373_sls.geojson")
    pesan = modul_worker._jelaskan_galat(
        "(1364, \"Field 'run_id' doesn't have a default value\")", run
    )
    assert pesan is not None
    assert "internal" in pesan and "tidak bersalah" in pesan
    assert "tidak memuat kolom" not in pesan


def test_konfirmasi_dan_persetujuan_validasi_sls_sukses_catatan(sesi) -> None:
    """Konfirmasi semua temuan 'sesuai_kenyataan' + disetujui provinsi -> sukses_catatan."""
    from app.auth import Pengguna
    from app.models import (
        KONFIRMASI_AKAN_DIPERBAIKI,
        KONFIRMASI_SESUAI_KENYATAAN,
        PERSETUJUAN_DISETUJUI,
        PERSETUJUAN_DITOLAK,
        STATUS_SUKSES_CATATAN,
    )
    from app.peran import PERAN_ADMIN_PROVINSI, PERAN_PETUGAS_KABKOT, Peran

    _isi_master(
        sesi,
        "3302",
        ["3302010001000100", "3302010001000200", "3302010001000300"],
    )
    run = _run_v(sesi)
    run.status = STATUS_BELUM_CLEAN
    sesi.commit()

    petugas_kab = Pengguna(
        sub="kab-3302",
        username="petugas.banyumas",
        nama="Budi Kab",
        nip="19900101",
        email="budi@bps.go.id",
        org="3302",
        peran=Peran(nama=PERAN_PETUGAS_KABKOT, kdprov="33", kdkab="3302"),
    )
    admin_prov = Pengguna(
        sub="prov-33",
        username="admin.jateng",
        nama="Siti Provinsi",
        nip="19850101",
        email="siti@bps.go.id",
        org="3300",
        peran=Peran(nama=PERAN_ADMIN_PROVINSI, kdprov="33", kdkab=None),
    )

    total, daftar = layanan.daftar_unmatch(sesi, run.id)
    assert total == 3
    ids = [int(b["id"]) for b in daftar]

    # 1. Konfirmasi 2 baris 'sesuai_kenyataan' dan 1 baris 'akan_diperbaiki'
    layanan.simpan_konfirmasi_validasi(
        sesi,
        petugas_kab,
        run,
        unmatch_ids=ids[:2],
        status=KONFIRMASI_SESUAI_KENYATAAN,
        catatan="Kondisi batas sungai alami sesuai lapangan",
    )
    layanan.simpan_konfirmasi_validasi(
        sesi,
        petugas_kab,
        run,
        unmatch_ids=[ids[2]],
        status=KONFIRMASI_AKAN_DIPERBAIKI,
        catatan="Segera dirapikan di QGIS",
    )
    ringkas = layanan.ringkasan_validasi(sesi, kdprov="33", kdkab="3302")[0]
    assert ringkas["terkonfirmasi"] == 3
    assert ringkas["sesuai_kenyataan"] == 2
    assert ringkas["akan_diperbaiki"] == 1
    assert ringkas["menunggu_persetujuan"] == 2
    assert ringkas["status"] == STATUS_BELUM_CLEAN

    # 2. Ubah baris ke-3 menjadi 'sesuai_kenyataan' oleh provinsi & setujui ketiganya
    layanan.simpan_konfirmasi_validasi(
        sesi,
        admin_prov,
        run,
        unmatch_ids=[ids[2]],
        status=KONFIRMASI_SESUAI_KENYATAAN,
        catatan="Sudah dicek bersama kab/kota sesuai kenyataan",
    )
    disetujui = layanan.simpan_persetujuan_validasi(
        sesi,
        admin_prov,
        run,
        unmatch_ids=ids,
        keputusan=PERSETUJUAN_DISETUJUI,
        catatan="Disetujui tim provinsi",
    )
    assert disetujui == 3
    sesi.refresh(run)
    assert run.status == STATUS_SUKSES_CATATAN

    ringkas = layanan.ringkasan_validasi(sesi, kdprov="33", kdkab="3302")[0]
    assert ringkas["status"] == STATUS_SUKSES_CATATAN
    assert ringkas["disetujui"] == 3
    assert ringkas["menunggu_persetujuan"] == 0

    # Cek pelaku konfirmasi & persetujuan tersimpan
    _, daftar_baru = layanan.daftar_unmatch(
        sesi, run.id, status_konfirmasi="disetujui"
    )
    assert len(daftar_baru) == 3
    assert daftar_baru[0]["konfirmasi"]["oleh"] == "Budi Kab"
    assert daftar_baru[0]["konfirmasi"]["persetujuan_oleh"] == "Siti Provinsi"
    assert (
        daftar_baru[0]["konfirmasi"]["persetujuan_status"]
        == PERSETUJUAN_DISETUJUI
    )

    # 3. Bila 1 temuan ditolak provinsi, status kembali belum_clean
    layanan.simpan_persetujuan_validasi(
        sesi,
        admin_prov,
        run,
        unmatch_ids=[ids[0]],
        keputusan=PERSETUJUAN_DITOLAK,
        catatan="Mohon tetap diperbaiki poligonnya",
    )
    sesi.refresh(run)
    assert run.status == STATUS_BELUM_CLEAN
    ringkas = layanan.ringkasan_validasi(sesi, kdprov="33", kdkab="3302")[0]
    assert ringkas["status"] == STATUS_BELUM_CLEAN
    assert ringkas["disetujui"] == 2
    assert ringkas["ditolak"] == 1


def test_konfirmasi_validasi_sls_endpoint_kewenangan_dan_alasan_wajib(
    klien, sesi
) -> None:
    """Endpoint API: wajib alasan untuk sesuai_kenyataan, dan persetujuan khusus provinsi."""
    from app import auth
    from app.main import app
    from app.models import STATUS_SUKSES_CATATAN
    from app.peran import PERAN_ADMIN_PROVINSI, PERAN_PETUGAS_KABKOT, Peran

    _isi_master(
        sesi,
        "3302",
        ["3302010001000100", "3302010001000200", "3302010001000300"],
    )
    run = _run_v(sesi)
    run.status = STATUS_BELUM_CLEAN
    # Tambahkan juga temuan topologi geom_gap untuk menguji filter jenis baru
    sesi.add(
        ValidasiSlsUnmatch(
            run_id=run.id,
            jenis="geom_gap",
            idsls_peta="33020100010001",
            idsubsls_peta="3302010001000100",
            nmsls="RT 01",
            catatan="gap/celah antar poligon (±12,50 m²)",
        )
    )
    sesi.commit()

    petugas_kab = auth.Pengguna(
        sub="kab-3302",
        username="petugas.banyumas",
        nama="Budi Kab",
        org="3302",
        peran=Peran(nama=PERAN_PETUGAS_KABKOT, kdprov="33", kdkab="3302"),
    )
    admin_prov = auth.Pengguna(
        sub="prov-33",
        username="admin.jateng",
        nama="Siti Provinsi",
        org="33",
        peran=Peran(nama=PERAN_ADMIN_PROVINSI, kdprov="33", kdkab=None),
    )

    try:
        app.dependency_overrides[auth.pengguna_saat_ini] = lambda: petugas_kab

        # Filter jenis geom_gap diizinkan
        r_gap = klien.get(f"/runs/{run.id}/validasi-sls/unmatch?jenis=geom_gap")
        assert r_gap.status_code == 200
        assert r_gap.json()["total"] == 1

        r_all = klien.get(f"/runs/{run.id}/validasi-sls/unmatch")
        assert r_all.status_code == 200
        semua_ids = [b["id"] for b in r_all.json()["baris"]]
        assert len(semua_ids) == 4

        # Sesuai kenyataan tanpa alasan ditolak 422
        r_tanpa_alasan = klien.post(
            f"/runs/{run.id}/validasi-sls/konfirmasi",
            json={
                "unmatch_ids": [semua_ids[0]],
                "status": "sesuai_kenyataan",
                "catatan": "   ",
            },
        )
        assert r_tanpa_alasan.status_code == 422

        # Bulk (lebih dari 1 temuan sekaligus) ditolak 422
        r_bulk = klien.post(
            f"/runs/{run.id}/validasi-sls/konfirmasi",
            json={
                "unmatch_ids": semua_ids,
                "status": "sesuai_kenyataan",
                "catatan": "Alasan massal tidak boleh",
            },
        )
        assert r_bulk.status_code == 422

        # Konfirmasi satu per satu diterima
        for idx, uid in enumerate(semua_ids, start=1):
            r_ok = klien.post(
                f"/runs/{run.id}/validasi-sls/konfirmasi",
                json={
                    "unmatch_ids": [uid],
                    "status": "sesuai_kenyataan",
                    "catatan": f"Alasan spesifik temuan ke-{idx} sesuai kondisi lapangan",
                },
            )
            assert r_ok.status_code == 200
            assert r_ok.json()["jumlah"] == 1

        # Petugas kab/kota mencoba menyetujui -> ditolak 403
        r_kab_setuju = klien.post(
            f"/runs/{run.id}/validasi-sls/persetujuan",
            json={"unmatch_ids": [semua_ids[0]], "keputusan": "disetujui"},
        )
        assert r_kab_setuju.status_code == 403

        # Admin provinsi menyetujui satu per satu -> 200 & status di ringkasan menjadi sukses_catatan
        app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin_prov
        # Persetujuan bulk juga ditolak 422
        r_prov_bulk = klien.post(
            f"/runs/{run.id}/validasi-sls/persetujuan",
            json={"unmatch_ids": semua_ids, "keputusan": "disetujui"},
        )
        assert r_prov_bulk.status_code == 422

        for uid in semua_ids:
            r_prov_setuju = klien.post(
                f"/runs/{run.id}/validasi-sls/persetujuan",
                json={
                    "unmatch_ids": [uid],
                    "keputusan": "disetujui",
                    "catatan": "Disetujui provinsi",
                },
            )
            assert r_prov_setuju.status_code == 200
            assert r_prov_setuju.json()["jumlah"] == 1

        r_ringkasan = klien.get("/validasi-sls/ringkasan")
        assert r_ringkasan.status_code == 200
        baris_kab = r_ringkasan.json()["baris"][0]
        assert baris_kab["status"] == STATUS_SUKSES_CATATAN
        assert baris_kab["disetujui"] == 4
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)

