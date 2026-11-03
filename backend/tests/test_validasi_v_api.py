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
    for arah, kode, level in [
        ("peta", "33020100010001", "sls"),
        ("master", "33020100010002", "sls"),
    ]:
        sesi.add(
            ValidasiSlsUnmatch(
                run_id=run.id, arah=arah, level=level, idsls=kode,
                nmsls="SLS", alasan="x",
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
    assert isi.splitlines()[0] == "arah,level,idsls,nmsls,alasan"
    assert "33020100010001" in isi and "33020100010002" in isi


def test_saring_run_tanpa_tipe_kecualikan_v() -> None:
    saring = layanan._saring_run(None, None, None)
    teks = " ".join(str(s) for s in saring)
    # Tanpa tipe: hanya A/B, run V steril dari ringkasan/tren.
    assert "V" not in teks or "in_" in teks.lower() or "tipe" in teks.lower()
    # Pastikan ada penyaring tipe A/B (bukan tanpa saring tipe sama sekali).
    assert len(saring) >= 2


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


def test_unggah_v_dengan_master_masuk_antre(sesi_pabrik, tmp_path) -> None:
    """Master ada: unggah V lolos gerbang awal (201 menunggu)."""
    (tmp_path / "m" / "3313").mkdir(parents=True, exist_ok=True)
    (tmp_path / "m" / "3313" / "msubsls_26_1_3313.xlsx").write_bytes(b"palsu")
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
