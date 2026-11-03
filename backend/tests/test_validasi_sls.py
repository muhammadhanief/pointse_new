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
    assert "duplikat: GAGAL (2 idsls ganda; contoh: A, B)" in pesan
    assert "unmatch_peta=1" in pesan and "unmatch_master=1" in pesan
    assert "contoh: A" in pesan and "contoh: C" in pesan


def test_normalisasi_idsls() -> None:
    """Strip + buang .0 ala Excel + kosong -> None."""
    assert validasi_sls.normalisasi_idsls(" 33020100010001 ") == "33020100010001"
    assert validasi_sls.normalisasi_idsls(33020100010001.0) == "33020100010001"
    assert validasi_sls.normalisasi_idsls("") is None
    assert validasi_sls.normalisasi_idsls(None) is None
