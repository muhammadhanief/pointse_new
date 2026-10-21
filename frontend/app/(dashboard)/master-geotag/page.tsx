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
      <div className="space-y-field">
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
    <div className="space-y-field">
      <PageHeader
        judul="Master geotag"
        deskripsi="Simpan geotag asli per kabupaten/kota. Versi lama tetap disimpan karena masih dirujuk proses yang sudah berjalan."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Admin Provinsi</p>
            <p className="mt-1 text-xs">
              {labelWilayah(sesi.kdprov, sesi.kdkab)}
            </p>
          </div>
        }
      />

      <MasterClient kdprov={sesi.kdprov} />
    </div>
  );
}
