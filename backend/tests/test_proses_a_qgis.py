"""Tes Proses A terhadap output QGIS asli (data uji di ``docs/``).

Dilewati otomatis bila data uji tidak ada, dan ditandai ``slow`` karena
memproses seluruh kabupaten (397 ribu titik).
"""

from __future__ import annotations

import pytest

from app.proses_a import KOLOM_HASIL, proses_a

import qgis_data

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not qgis_data.ada_data_uji(), reason="data uji docs/ tidak tersedia"),
]

# Hasil pengukuran pada data uji kdkab 3307 (lihat scripts/ukur_proses_a.py).
BARIS_OUTPUT_QGIS = 397_364


def test_proses_a_sama_dengan_output_qgis() -> None:
    """Jumlah baris dan semua kolom sama dengan output QGIS, kecuali flag_psls.

    ``flag_psls`` dikecualikan karena di file input ada 79 ``assignment_id``
    ganda: pasangan barisnya identik kecuali ``flag_psls`` (0 vs 1), sehingga
    baris mana yang tersisa setelah penghapusan duplikat tidak bisa ditentukan
    dari data. Selisihnya diuji terpisah di
    ``test_beda_flag_psls_hanya_pada_assignment_id_duplikat``.
    """
    titik = qgis_data.muat_titik()
    peta = qgis_data.muat_peta()
    qgis = qgis_data.muat_output_a()

    hasil = proses_a(titik, peta)
    laporan = qgis_data.bandingkan(hasil, qgis, KOLOM_HASIL)

    assert laporan["baris_hasil"] == laporan["baris_qgis"] == BARIS_OUTPUT_QGIS
    assert laporan["hanya_di_hasil"] == 0, "ada assignment_id yang tidak ada di output QGIS"
    assert laporan["hanya_di_qgis"] == 0, "ada assignment_id QGIS yang tidak dihasilkan"

    beda = {
        kolom: jumlah
        for kolom, jumlah in laporan["beda_per_kolom"].items()  # type: ignore[union-attr]
        if jumlah and kolom != "flag_psls"
    }
    assert not beda, f"kolom yang tidak sama dengan output QGIS: {beda}"


def test_beda_flag_psls_hanya_pada_assignment_id_duplikat() -> None:
    """Selisih flag_psls hanya terjadi pada assignment_id yang ganda di input."""
    titik = qgis_data.muat_titik()
    peta = qgis_data.muat_peta()
    qgis = qgis_data.muat_output_a()

    hasil = proses_a(titik, peta)
    laporan = qgis_data.bandingkan(hasil, qgis, KOLOM_HASIL)

    id_beda = laporan["id_beda_per_kolom"].get("flag_psls")  # type: ignore[union-attr]
    duplikat = set(titik.loc[titik["assignment_id"].duplicated(keep=False), "assignment_id"])

    assert id_beda is not None, "seharusnya ada selisih flag_psls pada data uji ini"
    assert len(id_beda) <= len(duplikat)
    assert set(id_beda) <= duplikat, "ada selisih flag_psls di luar assignment_id duplikat"
    assert laporan["beda_total"] == len(id_beda)  # type: ignore[arg-type]


def test_jumlah_baris_duplikat_dibuang() -> None:
    """Jumlah baris hasil = jumlah titik unik assignment_id (duplikat dibuang)."""
    titik = qgis_data.muat_titik()
    peta = qgis_data.muat_peta()

    hasil = proses_a(titik, peta)

    assert len(hasil) == titik["assignment_id"].nunique()
    assert hasil["assignment_id"].is_unique
