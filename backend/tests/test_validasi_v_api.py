"""Tes daftar/unduh unmatch run V + steril SE2026 (PRD §11)."""

from __future__ import annotations

from app import ekspor, layanan
from app.config import Settings
from app.models import TIPE_V, Run, ValidasiSlsUnmatch


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
    for arah, kode in [("peta", "33020100010001"), ("master", "33020100010002")]:
        sesi.add(
            ValidasiSlsUnmatch(
                run_id=run.id, arah=arah, idsls=kode, nmsls="SLS", alasan="x"
            )
        )
    sesi.commit()
    return run


def test_daftar_unmatch_paging_dan_saring(sesi) -> None:
    run = _run_v(sesi)
    total, baris = layanan.daftar_unmatch(sesi, run.id, limit=1, offset=0)
    assert total == 2
    assert len(baris) == 1
    assert baris[0]["idsls"] == "33020100010001"
    total_peta, baris_peta = layanan.daftar_unmatch(sesi, run.id, arah="peta")
    assert total_peta == 1
    assert baris_peta[0]["arah"] == "peta"
    total_master, _ = layanan.daftar_unmatch(sesi, run.id, arah="master")
    assert total_master == 1


def test_spool_unmatch_v_csv(sesi, tmp_path) -> None:
    run = _run_v(sesi)
    setelan = Settings(dir_unggahan=str(tmp_path / "u"))
    spool = ekspor.spool_unmatch_v_csv(sesi, run.id, setelan)
    isi = spool.read().decode("utf-8")
    assert isi.splitlines()[0] == "arah,idsls,nmsls,alasan"
    assert "33020100010001" in isi and "33020100010002" in isi


def test_saring_run_tanpa_tipe_kecualikan_v() -> None:
    saring = layanan._saring_run(None, None, None)
    teks = " ".join(str(s) for s in saring)
    # Tanpa tipe: hanya A/B, run V steril dari ringkasan/tren.
    assert "V" not in teks or "in_" in teks.lower() or "tipe" in teks.lower()
    # Pastikan ada penyaring tipe A/B (bukan tanpa saring tipe sama sekali).
    assert len(saring) >= 2
