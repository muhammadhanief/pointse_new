import type { Metadata } from "next";

import { PERAN_ADMIN_PROVINSI, labelWilayah } from "@/lib/auth/peran";
import { wajibSesi } from "@/lib/auth/session";
import { MasterClient } from "@/components/master/master-client";
import {
  EmptyState,
  PageHeader,
  Panel,
  TautanAksi,
} from "@/components/dashboard/ui";

export const metadata: Metadata = {
  title: "Master geotag",
};

// Halaman membaca sesi di server; izinkan render memblokir tanpa validasi
// instant navigation (lihat layout dashboard).
export const instant = false;

export default async function MasterGeotagPage() {
  const sesi = await wajibSesi();
  const admin = sesi.peran === PERAN_ADMIN_PROVINSI;

  if (!admin) {
    return (
      <div className="space-y-8">
        <PageHeader
          judul="Master geotag"
          deskripsi="Master geotag disiapkan admin provinsi untuk setiap kabupaten/kota."
        />
        <Panel judul="Akses terbatas">
          <EmptyState
            judul="Halaman ini hanya untuk admin provinsi"
            aksi={
              <TautanAksi href="/" varian="sekunder">
                Kembali ke beranda
              </TautanAksi>
            }
          >
            Petugas kabupaten/kota memakai master yang sudah disiapkan. Hubungi
            admin provinsi bila master untuk wilayah kerja Anda belum ada.
          </EmptyState>
        </Panel>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader
        judul="Master geotag"
        deskripsi="Simpan geotag asli per kabupaten/kota. Versi lama tetap disimpan karena masih dirujuk proses yang sudah berjalan."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Admin Provinsi</p>
            <p className="mt-0.5 text-xs">
              {labelWilayah(sesi.kdprov, sesi.kdkab)}
            </p>
          </div>
        }
      />

      <MasterClient kdprov={sesi.kdprov} />

      <Panel
        judul="Pemeriksaan berkas"
        deskripsi="Aturan ini dipakai saat master diunggah agar kode wilayah tidak tercampur."
      >
        <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-muted marker:text-muted">
          <li>Kode wilayah harus empat digit dan diawali kode provinsi.</li>
          <li>
            Semua <span className="font-mono text-xs">level_6_full_code</span>{" "}
            harus milik kabupaten/kota yang sama.
          </li>
          <li>
            Berkas ditolak bila tidak ada satu pun kode yang bisa diverifikasi.
          </li>
          <li>
            Versi lama tidak dihapus karena masih dipakai run 1. Identifikasi
            Titik sebelumnya.
          </li>
        </ul>
      </Panel>
    </div>
  );
}
