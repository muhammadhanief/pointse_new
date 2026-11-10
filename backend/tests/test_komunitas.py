"""Tes API modul Komunitas (berbagi error GS Pusat, diskusi solusi, & target rule)."""

from __future__ import annotations

from app import auth
from app.main import app
from app.peran import PERAN_ADMIN_PROVINSI, PERAN_PETUGAS_KABKOT, Peran


def test_alur_komunitas_error_gs_solusi_dan_rule(klien) -> None:
    """Buat topik error .txt, cari, dukung (+1), balas solusi, dan angkat jadi rule."""
    kab_banyumas = auth.Pengguna(
        sub="kab-3302",
        username="petugas.3302",
        nama="Andi Banyumas",
        org="3302",
        peran=Peran(nama=PERAN_PETUGAS_KABKOT, kdprov="33", kdkab="3302"),
    )
    kab_cilacap = auth.Pengguna(
        sub="kab-3301",
        username="petugas.3301",
        nama="Rina Cilacap",
        org="3301",
        peran=Peran(nama=PERAN_PETUGAS_KABKOT, kdprov="33", kdkab="3301"),
    )
    admin_prov = auth.Pengguna(
        sub="prov-33",
        username="admin.33",
        nama="Siti Provinsi",
        org="33",
        peran=Peran(nama=PERAN_ADMIN_PROVINSI, kdprov="33", kdkab=None),
    )

    try:
        # 1. Petugas Kab Banyumas membuat topik error .txt dari GS Pusat
        app.dependency_overrides[auth.pengguna_saat_ini] = lambda: kab_banyumas
        r_buat = klien.post(
            "/komunitas/topik",
            json={
                "kategori": "peta_2026_s1",
                "judul": "Error GS: Ring Self-Intersection pada idsubsls 3302010001000100",
                "error_txt": "ERROR_GS_099: Polygon ring self-intersection at (109.2341, -7.4123)",
                "deskripsi": "Waktu upload ke dataspasial.bps.go.id/gs ditolak dengan file txt ini.",
                "solusi_awal": None,
            },
        )
        assert r_buat.status_code == 201, r_buat.text
        topik = r_buat.json()
        topik_id = topik["id"]
        assert topik["status"] == "terbuka"
        assert topik["kdkab"] == "3302"
        assert topik["jumlah_dukungan"] == 1
        assert topik["didukung_saya"] is True

        # 2. Petugas Kab Cilacap mencari potongan kode error_txt dan menekan +1 serta memberi solusi
        app.dependency_overrides[auth.pengguna_saat_ini] = lambda: kab_cilacap
        r_cari = klien.get("/komunitas/topik?q=ERROR_GS_099")
        assert r_cari.status_code == 200
        assert r_cari.json()["total"] == 1
        assert r_cari.json()["terbuka"] == 1

        r_dukung = klien.post(f"/komunitas/topik/{topik_id}/dukungan")
        assert r_dukung.status_code == 200
        assert r_dukung.json()["jumlah_dukungan"] == 2
        assert r_dukung.json()["didukung_saya"] is True

        r_komentar = klien.post(
            f"/komunitas/topik/{topik_id}/komentar",
            json={
                "isi": "Di QGIS jalankan Fix Geometries lalu Dissolve berdasarkan idsubsls, langsung lolos di GS.",
                "tandai_sebagai_solusi": False,
            },
        )
        assert r_komentar.status_code == 200
        komentar_id = r_komentar.json()["komentar"][0]["id"]

        # 3. Pembuat topik (Kab Banyumas) menandai komentar Kab Cilacap sebagai Solusi Terverifikasi
        app.dependency_overrides[auth.pengguna_saat_ini] = lambda: kab_banyumas
        r_solusi = klien.post(
            f"/komunitas/topik/{topik_id}/komentar/{komentar_id}/solusi"
        )
        assert r_solusi.status_code == 200
        assert r_solusi.json()["status"] == "terpecahkan"
        assert r_solusi.json()["komentar"][0]["adalah_solusi"] is True

        # 4. Petugas kab/kota tidak boleh mengubah target rule PointSE (403)
        r_rule_kab = klien.post(
            f"/komunitas/topik/{topik_id}/rule",
            json={
                "status": "jadi_rule",
                "rule_target": "validasi",
                "rule_catatan": "Tambahkan cek ring self-intersection",
            },
        )
        assert r_rule_kab.status_code == 403

        # 5. Admin Provinsi mengangkat masalah ini menjadi rule di /proses/validasi
        app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin_prov
        r_rule_prov = klien.post(
            f"/komunitas/topik/{topik_id}/rule",
            json={
                "status": "jadi_rule",
                "rule_target": "validasi",
                "rule_catatan": "Masukkan ke pengecekan geom_invalid di proses/validasi",
            },
        )
        assert r_rule_prov.status_code == 200
        hasil_akhir = r_rule_prov.json()
        assert hasil_akhir["status"] == "jadi_rule"
        assert hasil_akhir["rule_target"] == "validasi"
        assert hasil_akhir["rule_oleh"] == "Siti Provinsi"

        # Filter berdasarkan rule_target
        r_filter_rule = klien.get("/komunitas/topik?rule_target=validasi")
        assert r_filter_rule.status_code == 200
        assert r_filter_rule.json()["total"] == 1
        assert r_filter_rule.json()["jadi_rule"] == 1

        # 6. Pencarian berdasarkan nomor tiket (#0001 / #1)
        r_cari_tiket = klien.get(f"/komunitas/topik?q=%23{topik_id:04d}")
        assert r_cari_tiket.status_code == 200
        assert r_cari_tiket.json()["total"] == 1
        assert r_cari_tiket.json()["baris"][0]["id"] == topik_id

        # 7. Petugas kab/kota tidak boleh menghapus komentar maupun topik (403)
        app.dependency_overrides[auth.pengguna_saat_ini] = lambda: kab_banyumas
        assert (
            klien.delete(
                f"/komunitas/topik/{topik_id}/komentar/{komentar_id}"
            ).status_code
            == 403
        )
        assert klien.delete(f"/komunitas/topik/{topik_id}").status_code == 403

        # 8. Admin Provinsi dapat menghapus komentar dan menghapus topik
        app.dependency_overrides[auth.pengguna_saat_ini] = lambda: admin_prov
        r_hapus_kom = klien.delete(
            f"/komunitas/topik/{topik_id}/komentar/{komentar_id}"
        )
        assert r_hapus_kom.status_code == 200
        assert r_hapus_kom.json()["jumlah_komentar"] == 0

        r_hapus_topik = klien.delete(f"/komunitas/topik/{topik_id}")
        assert r_hapus_topik.status_code == 200
        assert r_hapus_topik.json()["dihapus"] is True
        assert klien.get(f"/komunitas/topik/{topik_id}").status_code == 404
    finally:
        app.dependency_overrides.pop(auth.pengguna_saat_ini, None)
