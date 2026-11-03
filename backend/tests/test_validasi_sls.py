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


def test_banding_pasangan_cocok_semua_lolos() -> None:
    """Himpunan pasangan sama persis = lolos."""
    peta = {("A", "A01"): "SLS A"}
    hasil = validasi_sls.bandingkan(peta, {("A", "A01"): "SLS A"})
    assert hasil.lolos
    assert hasil.temuan == []


def test_banding_dua_arah_sisi_terisi() -> None:
    """Sisi yang hilang dibiarkan kosong sesuai arah temuan."""
    peta = {("A", "A01"): "SLS A", ("B", "B01"): "SLS B"}
    master = {("B", "B01"): "SLS B", ("C", "C01"): "SLS C"}
    hasil = validasi_sls.bandingkan(peta, master)
    assert not hasil.lolos
    assert len(hasil.temuan) == 2
    assert hasil.temuan[0].jenis == validasi_sls.JENIS_TIDAK_DI_MASTER
    assert (hasil.temuan[0].idsls_peta, hasil.temuan[0].idsubsls_peta) == ("A", "A01")
    assert hasil.temuan[0].idsls_master is None
    assert hasil.temuan[1].jenis == validasi_sls.JENIS_TIDAK_DI_PETA
    assert (hasil.temuan[1].idsls_master, hasil.temuan[1].idsubsls_master) == ("C", "C01")
    assert hasil.temuan[1].idsls_peta is None


def test_banding_kode_16_digit_di_idsls_tetap_tidak_di_master() -> None:
    """Kode subsls di kolom idsls = salah pengisi: tetap tidak_di_master + catatan."""
    peta = {("3312090005003801", "3312090005003801"): "BATU LOR"}
    master = {("33120900050038", "3312090005003801"): "BATU LOR"}
    hasil = validasi_sls.bandingkan(peta, master, {("3312090005003801", "3312090005003801"): 1})
    assert not hasil.lolos
    assert len(hasil.temuan) == 2
    salah = hasil.temuan[0]
    assert salah.jenis == validasi_sls.JENIS_TIDAK_DI_MASTER
    assert salah.idsls_master is None
    assert salah.catatan == "kolom idsls bukan kode SLS 14 digit"
    assert hasil.temuan[1].jenis == validasi_sls.JENIS_TIDAK_DI_PETA


def test_banding_ganda_satu_baris() -> None:
    """Pasangan ganda yang cocok + yang asing masing-masing satu baris."""
    pasang = ("A", "A01")
    asing = ("B", "B02")
    peta = {pasang: "SLS A", asing: "SLS B"}
    master = {pasang: "SLS A"}
    hitung = {pasang: 2, asing: 1}
    hasil = validasi_sls.bandingkan(peta, master, hitung)
    assert not hasil.lolos
    assert [(s.jenis, s.idsls_peta) for s in hasil.temuan] == [
        (validasi_sls.JENIS_GANDA, "A"),
        (validasi_sls.JENIS_TIDAK_DI_MASTER, "B"),
    ]
    assert hasil.temuan[0].catatan == "2 baris"


def test_banding_ganda_tak_dikenal_tetap_satu_baris() -> None:
    """Pasangan ganda yang asing tidak dobel baris (satu temuan + catatan)."""
    pasang = ("33020100010001", "3302010001000199")
    hasil = validasi_sls.bandingkan(
        {pasang: "SLS B"}, {}, {pasang: 3},
    )
    assert not hasil.lolos
    assert len(hasil.temuan) == 1
    assert hasil.temuan[0].jenis == validasi_sls.JENIS_TIDAK_DI_MASTER
    assert hasil.temuan[0].catatan == "ganda di peta (3 baris)"


def test_pesan_tiga_blok() -> None:
    """Pesan memuat ringkasan skema/duplikat/matching + contoh."""
    skema = validasi_sls.HasilSkema(lolos=True)
    duplikat = validasi_sls.HasilDuplikat(lolos=False, jumlah_ganda=2, contoh=["A|X", "B|Y"])
    matching = validasi_sls.HasilMatching(
        lolos=False,
        temuan=[
            validasi_sls.BarisUnmatch(
                jenis=validasi_sls.JENIS_TIDAK_DI_MASTER,
                idsls_peta="A", idsubsls_peta="A01",
                idsls_master=None, idsubsls_master=None, nmsls="SLS A",
            ),
            validasi_sls.BarisUnmatch(
                jenis=validasi_sls.JENIS_TIDAK_DI_PETA,
                idsls_peta=None, idsubsls_peta=None,
                idsls_master="C", idsubsls_master="C01", nmsls="SLS C",
            ),
        ],
    )
    lolos, pesan = validasi_sls.rangkum_pesan(skema, duplikat, matching)
    assert not lolos
    assert "Validasi Kelengkapan Atribut: Sukses" in pesan
    assert "Validasi Duplikat: Gagal" in pesan and "2 pasangan ganda" in pesan
    assert "tidak ada di peta=1" in pesan and "tidak ada di master=1" in pesan
    assert "Contoh tidak ada di peta: C01." in pesan
    assert "Contoh tidak ada di master: A01." in pesan
    assert pesan.rstrip().endswith("lalu unggah ulang.")


def test_normalisasi_idsls() -> None:
    """Strip + buang .0 ala Excel + kosong -> None."""
    assert validasi_sls.normalisasi_idsls(" 33020100010001 ") == "33020100010001"
    assert validasi_sls.normalisasi_idsls(33020100010001.0) == "33020100010001"
    assert validasi_sls.normalisasi_idsls("") is None
    assert validasi_sls.normalisasi_idsls(None) is None


def test_banding_kode_16_digit_di_idsls_tetap_tidak_di_master() -> None:
    """Kode subsls di kolom idsls = salah pengisi: tetap tidak_di_master + catatan."""
    peta = {("3312090005003801", "3312090005003801"): "BATU LOR"}
    master = {("33120900050038", "3312090005003801"): "BATU LOR"}
    hasil = validasi_sls.bandingkan(peta, master, {("3312090005003801", "3312090005003801"): 1})
    assert not hasil.lolos
    assert len(hasil.temuan) == 2
    salah = hasil.temuan[0]
    assert salah.jenis == validasi_sls.JENIS_TIDAK_DI_MASTER
    assert salah.idsls_master is None
    assert salah.catatan == "kolom idsls bukan kode SLS 14 digit"
    assert hasil.temuan[1].jenis == validasi_sls.JENIS_TIDAK_DI_PETA


def test_banding_sub_tak_dikenal_satu_baris() -> None:
    """Kode asing di dua kolom: satu temuan tidak_di_master, bukan dua."""
    peta = {("3312090005003800", "3312090005003800"): "BATU LOR"}
    master = {("33120900050038", "3312090005003801"): "BATU LOR"}
    hasil = validasi_sls.bandingkan(peta, master, {("3312090005003800", "3312090005003800"): 1})
    assert not hasil.lolos
    assert len(hasil.temuan) == 2  # 1 tidak_di_master + 1 tidak_di_peta
    assert hasil.temuan[0].jenis == validasi_sls.JENIS_TIDAK_DI_MASTER
    assert hasil.temuan[0].idsls_peta == "3312090005003800"
    assert hasil.temuan[1].jenis == validasi_sls.JENIS_TIDAK_DI_PETA


def test_pesan_memuat_hitungan_jenis() -> None:
    """Pesan menyebut hitungan per jenis temuan + contoh kode."""
    skema = validasi_sls.HasilSkema(lolos=True)
    duplikat = validasi_sls.HasilDuplikat(lolos=True)
    matching = validasi_sls.HasilMatching(
        lolos=False,
        temuan=[
            validasi_sls.BarisUnmatch(
                jenis=validasi_sls.JENIS_GANDA,
                idsls_peta="B", idsubsls_peta="B01",
                idsls_master="B", idsubsls_master="B01", nmsls="SLS B",
                catatan="2 baris",
            ),
            validasi_sls.BarisUnmatch(
                jenis=validasi_sls.JENIS_TIDAK_DI_MASTER,
                idsls_peta="C02", idsubsls_peta="C02",
                idsls_master=None, idsubsls_master=None, nmsls="SLS C",
                catatan="kolom idsls bukan kode SLS 14 digit",
            ),
        ],
    )
    lolos, pesan = validasi_sls.rangkum_pesan(skema, duplikat, matching)
    assert not lolos
    assert "Validasi Duplikat: Sukses" in pesan
    assert "ganda=1" in pesan and "tidak ada di master=1" in pesan
    assert "Contoh ganda: B01." in pesan
    assert "Contoh tidak ada di master: C02." in pesan


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
    """Tulis peta mini (17 kolom V + geometri titik).

    ``baris`` = daftar ``(idsls, idsubsls, nmsls)``; ``idsls`` boleh beda dari
    induk ``idsubsls`` untuk mensimulasikan kolom salah isi.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.GeoDataFrame(
        [
            {
                "kdprov": "33", "kdkab": "12", "kdkec": "010", "kddesa": "001",
                "kdsls": "0001", "kdsubsls": "01", "idsls": idsls,
                "idsubsls": subsls, "nmprov": "x", "nmkab": "x", "nmkec": "x",
                "nmdesa": "x", "nmsls": nmsls, "rw_dki": "x", "tingkat": 1,
                "nm_gedung": "x", "posisi": "x",
            }
            for idsls, subsls, nmsls in baris
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
        peta,
        [
            ("33120100010001", "3312010001000100", "SLS A"),
            ("33120100010001", "3312010001000101", "SLS A"),
        ],
    )
    hasil = validasi_sls.validasi_berkas(peta, None, tmp_path / "m", "3312")
    assert hasil.lolos, hasil.pesan
    assert "Validasi Duplikat: Sukses" in hasil.pesan


def test_berkas_subsls_ganda_dan_beda_komposisi_gagal(tmp_path) -> None:
    """Pasangan sama = ganda; subsls asing = tidak di master; hilang = tidak di peta."""
    _siapkan_master(
        tmp_path, "3312",
        [("3312010001000100", "SLS A"), ("3312010001000101", "SLS A")],
    )
    peta = tmp_path / "peta.geojson"
    _tulis_peta_geojson(
        peta,
        [
            ("33120100010001", "3312010001000100", "SLS A"),
            ("33120100010001", "3312010001000100", "SLS A"),  # ganda persis
            ("33120100010001", "3312010001000102", "SLS A"),  # tidak di master
        ],
    )
    hasil = validasi_sls.validasi_berkas(peta, None, tmp_path / "m", "3312")
    assert not hasil.lolos
    assert "1 pasangan ganda" in hasil.pesan
    assert "tidak ada di master=1" in hasil.pesan
    assert "tidak ada di peta=1" in hasil.pesan
    assert "ganda=1" in hasil.pesan


def test_berkas_idsls_16_digit_jadi_tidak_di_master(tmp_path) -> None:
    """Kode 16 digit di kolom idsls = salah pengisi: tetap tidak_di_master + catatan."""
    _siapkan_master(
        tmp_path, "3312",
        [("3312010001000100", "SLS A"), ("3312010001000101", "SLS A")],
    )
    peta = tmp_path / "peta.geojson"
    _tulis_peta_geojson(
        peta,
        [
            ("33120100010001", "3312010001000100", "SLS A"),
            ("3312010001000101", "3312010001000101", "SLS A"),  # idsls salah
        ],
    )
    hasil = validasi_sls.validasi_berkas(peta, None, tmp_path / "m", "3312")
    assert not hasil.lolos
    assert "tidak ada di master=1" in hasil.pesan
    assert "tidak ada di peta=1" in hasil.pesan
    temuan = [s for s in hasil.matching.temuan if s.jenis == "tidak_di_master"]
    assert len(temuan) == 1 and temuan[0].catatan == "kolom idsls bukan kode SLS 14 digit"


def test_skema_pindai_melewati_batas_2000_baris() -> None:
    """Pelanggaran di baris >2000 tetap ketahuan + nomor baris dilaporkan."""
    kolom = list(validasi_sls.KOLOM_PETA_V)
    contoh = {nama: ["x"] * 5000 for nama in kolom}
    contoh["nmdesa"][4650 - 1] = "y" * 51
    hasil = validasi_sls.periksa_skema(kolom, contoh)
    assert not hasil.lolos
    temuan = [s for s in hasil.temuan if s.kolom == "nmdesa"]
    assert len(temuan) == 1
    assert "pertama di baris 4650" in temuan[0].masalah


def test_banding_subsls_baru_di_sls_dikenal_diberi_hint_pemekaran() -> None:
    """Subsls asing di bawah induk terdaftar = kemungkinan hasil pemekaran."""
    peta = {
        ("33020100010001", "3302010001000100"): "SLS A",
        ("33020100010001", "3302010001000199"): "SLS A",
    }
    master = {
        ("33020100010001", "3302010001000100"): "SLS A",
        ("33020100010001", "3302010001000101"): "SLS A",
    }
    hitung = {k: 1 for k in peta}
    hasil = validasi_sls.bandingkan(peta, master, hitung)
    assert not hasil.lolos
    asing = [s for s in hasil.temuan if s.jenis == validasi_sls.JENIS_TIDAK_DI_MASTER]
    assert len(asing) == 1
    assert asing[0].idsubsls_peta == "3302010001000199"
    assert asing[0].catatan == "induk terdaftar di master (kemungkinan subsls baru hasil pemekaran)"
    assert any(s.jenis == validasi_sls.JENIS_TIDAK_DI_PETA for s in hasil.temuan)


def test_baca_master_melaporkan_baris_dilewati(caplog, tmp_path) -> None:
    """Baris master malformed dicatat di log, bukan didiamkan."""
    import logging

    _siapkan_master(
        tmp_path, "3312",
        [("3312010001000100", "SLS A"), ("SALAH", "SLS X"), ("", "SLS KOSONG")],
    )
    with caplog.at_level(logging.WARNING, logger="app.validasi_sls"):
        master = validasi_sls.baca_master(tmp_path / "m", "3312")
    assert set(master) == {("33120100010001", "3312010001000100")}
    assert "dilewati" in caplog.text and "SALAH" in caplog.text
