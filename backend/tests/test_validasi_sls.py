"""Tes mesin validasi peta SLS 2026 Semester 1 (tipe run V, PRD §11).

Hanya menguji fungsi murni (skema/duplikat/matching + pesan); I/O Excel/peta
diuji manual karena butuh berkas besar.
"""

from __future__ import annotations

from app import validasi_sls


def _kolom_lengkap() -> list[str]:
    return list(validasi_sls.KOLOM_PETA_V)


def test_skema_lolos_17_kolom() -> None:
    """17 kolom lengkap tanpa pelanggaran panjang = lolos."""
    hasil = validasi_sls.periksa_skema(_kolom_lengkap(), {})
    assert hasil.lolos
    assert not hasil.kolom_hilang


def test_skema_gagal_kolom_hilang() -> None:
    """Satu kolom hilang = blok skema gagal."""
    kolom = [nama for nama in _kolom_lengkap() if nama != "posisi"]
    hasil = validasi_sls.periksa_skema(kolom, {})
    assert not hasil.lolos
    assert hasil.kolom_hilang == ["posisi"]


def test_skema_gagal_panjang_data() -> None:
    """Nilai melebihi panjang tabel = temuan skema."""
    hasil = validasi_sls.periksa_skema(
        _kolom_lengkap(), {"idsls": ["330201000100011"]},  # 15 digit > 14
    )
    assert not hasil.lolos
    assert hasil.temuan and hasil.temuan[0].kolom == "idsls"


def test_duplikat_ditemukan() -> None:
    """idsls ganda terdaftar dengan contoh."""
    hasil = validasi_sls.periksa_duplikat(["33020100010001", "33020100010001", "33020100010002"])
    assert not hasil.lolos
    assert hasil.jumlah_ganda == 1
    assert hasil.contoh == ["33020100010001"]


def test_duplikat_bersih() -> None:
    """idsls unik = lolos."""
    hasil = validasi_sls.periksa_duplikat(["33020100010001", "33020100010002"])
    assert hasil.lolos


def test_matching_dua_arah() -> None:
    """idsls hanya di satu sisi masuk daftar unmatch yang benar."""
    peta = {"A": "SLS A", "B": "SLS B"}
    master = {"B": "SLS B", "C": "SLS C"}
    hasil = validasi_sls.cocokkan(peta, master)
    assert not hasil.lolos
    assert [(satu.idsls, satu.alasan) for satu in hasil.unmatch_peta] == [
        ("A", validasi_sls.ALASAN_TIDAK_DI_MASTER)
    ]
    assert [(satu.idsls, satu.alasan) for satu in hasil.unmatch_master] == [
        ("C", validasi_sls.ALASAN_TIDAK_DI_PETA)
    ]


def test_matching_duplikat_wajib_unmatch() -> None:
    """idsls ganda di peta tetap unmatch walau ada di master (aturan count!=1)."""
    peta = {"A": "SLS A"}
    master = {"A": "SLS A"}
    hasil = validasi_sls.cocokkan(peta, master, {"A"})
    assert not hasil.lolos
    assert hasil.unmatch_peta and hasil.unmatch_peta[0].alasan == validasi_sls.ALASAN_DUPLIKAT


def test_matching_cocok_semua() -> None:
    """Himpunan sama = lolos."""
    peta = {"A": "SLS A"}
    hasil = validasi_sls.cocokkan(peta, {"A": "SLS A"})
    assert hasil.lolos


def test_pesan_tiga_blok() -> None:
    """Pesan memuat ringkasan skema/duplikat/matching + contoh."""
    skema = validasi_sls.HasilSkema(lolos=True)
    duplikat = validasi_sls.HasilDuplikat(lolos=False, jumlah_ganda=2, contoh=["A", "B"])
    matching = validasi_sls.HasilMatching(
        lolos=False,
        unmatch_peta=[validasi_sls.BarisUnmatch("peta", "A", "SLS A", "tidak_di_master")],
        unmatch_master=[validasi_sls.BarisUnmatch("master", "C", "SLS C", "tidak_di_peta")],
    )
    lolos, pesan = validasi_sls.rangkum_pesan(skema, duplikat, matching)
    assert not lolos
    assert "skema: OK" in pesan
    assert "duplikat: GAGAL (2 idsubsls ganda; contoh: A, B)" in pesan
    assert "unmatch_peta=1" in pesan and "unmatch_master=1" in pesan
    assert "contoh: A" in pesan and "contoh: C" in pesan


def test_normalisasi_idsls() -> None:
    """Strip + buang .0 ala Excel + kosong -> None."""
    assert validasi_sls.normalisasi_idsls(" 33020100010001 ") == "33020100010001"
    assert validasi_sls.normalisasi_idsls(33020100010001.0) == "33020100010001"
    assert validasi_sls.normalisasi_idsls("") is None
    assert validasi_sls.normalisasi_idsls(None) is None


def test_matching_subsls_dua_arah() -> None:
    """Selisih komposisi SubSLS terdeteksi walau himpunan idsls-nya sama."""
    peta = {"3302010001000100": "SLS A", "3302010001000101": "SLS A"}
    master = {"3302010001000101": "SLS A", "3302010001000102": "SLS A"}
    hasil = validasi_sls.cocokkan(peta, master)
    assert not hasil.lolos
    assert [satu.idsls for satu in hasil.unmatch_peta] == ["3302010001000100"]
    assert [satu.idsls for satu in hasil.unmatch_master] == ["3302010001000102"]


def test_matching_subsls_duplikat_tetap_unmatch() -> None:
    """idsubsls ganda tetap unmatch walau ada di master."""
    kode = "3302010001000100"
    hasil = validasi_sls.cocokkan({kode: "SLS A"}, {kode: "SLS A"}, {kode})
    assert not hasil.lolos
    assert hasil.unmatch_peta and hasil.unmatch_peta[0].alasan == validasi_sls.ALASAN_DUPLIKAT


def test_baris_unmatch_membawa_level() -> None:
    """Baris SubSLS bertanda level subsls, baris SLS bertanda sls."""
    hasil = validasi_sls.cocokkan({"A": "x"}, {"B": "x"}, level="subsls")
    assert [satu.level for satu in hasil.unmatch_peta] == ["subsls"]
    assert [satu.level for satu in hasil.unmatch_master] == ["subsls"]
    hasil_sls = validasi_sls.cocokkan({"A": "x"}, {"B": "x"})
    assert [satu.level for satu in hasil_sls.unmatch_peta] == ["sls"]


def test_pesan_memuat_hitungan_subsls() -> None:
    """Pesan menyebut hitungan SubSLS hanya bila ada temuan SubSLS."""
    skema = validasi_sls.HasilSkema(lolos=True)
    duplikat = validasi_sls.HasilDuplikat(
        lolos=False, jumlah_ganda=2, contoh=["B", "C"],
    )
    matching = validasi_sls.HasilMatching(
        lolos=False,
        unmatch_peta=[validasi_sls.BarisUnmatch("peta", "A", "SLS A", "tidak_di_master")],
        unmatch_master=[],
        unmatch_sub_peta=[
            validasi_sls.BarisUnmatch("peta", "B", "SLS B", "tidak_di_master")
        ],
        unmatch_sub_master=[],
    )
    lolos, pesan = validasi_sls.rangkum_pesan(skema, duplikat, matching)
    assert not lolos
    assert "2 idsubsls ganda" in pesan
    assert "unmatch_sub_peta=1" in pesan and "unmatch_sub_master=0" in pesan


def _tulis_master_xlsx(jalur, baris) -> None:
    """Tulis master msubsls mini (kolom idsubsls + nmsls)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["idsubsls", "nmsls"])
    for subsls, nmsls in baris:
        ws.append([subsls, nmsls])
    wb.save(str(jalur))


def _tulis_peta_geojson(jalur, baris) -> None:
    """Tulis peta mini (17 kolom V + geometri titik)."""
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.GeoDataFrame(
        [
            {
                "kdprov": "33", "kdkab": "12", "kdkec": "010", "kddesa": "001",
                "kdsls": "0001", "kdsubsls": "01", "idsls": subsls[:14],
                "idsubsls": subsls, "nmprov": "x", "nmkab": "x", "nmkec": "x",
                "nmdesa": "x", "nmsls": nmsls, "rw_dki": "x", "tingkat": 1,
                "nm_gedung": "x", "posisi": "x",
            }
            for subsls, nmsls in baris
        ],
        geometry=[Point(110.0, -7.0)] * len(baris),
        crs="EPSG:4326",
    )
    gdf.to_file(str(jalur), driver="GeoJSON")


def _siapkan_master(tmp_path, kode, baris) -> None:
    akar = tmp_path / "m" / kode
    akar.mkdir(parents=True, exist_ok=True)
    _tulis_master_xlsx(akar / f"msubsls_26_1_{kode}.xlsx", baris)


def test_berkas_split_subsls_sesuai_master_lolos(tmp_path) -> None:
    """SLS yang sama di banyak baris bukan duplikat bila subsls-nya beda dan cocok."""
    _siapkan_master(
        tmp_path, "3312",
        [("3312010001000100", "SLS A"), ("3312010001000101", "SLS A")],
    )
    peta = tmp_path / "peta.geojson"
    _tulis_peta_geojson(
        peta, [("3312010001000100", "SLS A"), ("3312010001000101", "SLS A")]
    )
    hasil = validasi_sls.validasi_berkas(peta, None, tmp_path / "m", "3312")
    assert hasil.lolos, hasil.pesan
    assert "duplikat: OK" in hasil.pesan


def test_berkas_subsls_ganda_dan_beda_komposisi_gagal(tmp_path) -> None:
    """Pasangan idsls+idsubsls sama = duplikat; selisih komposisi = unmatch SubSLS."""
    _siapkan_master(
        tmp_path, "3312",
        [("3312010001000100", "SLS A"), ("3312010001000101", "SLS A")],
    )
    peta = tmp_path / "peta.geojson"
    _tulis_peta_geojson(
        peta,
        [
            ("3312010001000100", "SLS A"),
            ("3312010001000100", "SLS A"),  # ganda persis
            ("3312010001000102", "SLS A"),  # tidak di master
        ],
    )
    hasil = validasi_sls.validasi_berkas(peta, None, tmp_path / "m", "3312")
    assert not hasil.lolos
    assert "1 idsubsls ganda" in hasil.pesan
    assert "unmatch_sub_peta=2" in hasil.pesan  # ganda + tidak di master
    assert "unmatch_sub_master=1" in hasil.pesan
