import type { Metadata } from "next";

import { PERAN_ADMIN_PROVINSI, labelWilayah } from "@/lib/auth/peran";
import { wajibSesi } from "@/lib/auth/session";
import { PenggunaAktifClient } from "@/components/pengguna/pengguna-aktif";
import {
  EmptyState,
  PageHeader,
  Panel,
  TautanAksi,
} from "@/components/dashboard/ui";

export const metadata: Metadata = {
  title: "Pengguna aktif",
};

// Halaman membaca sesi di server; izinkan render memblokir tanpa validasi
// instant navigation (lihat layout dashboard).
export const instant = false;

export default async function PenggunaAktifPage() {
  const sesi = await wajibSesi();
  const admin = sesi.peran === PERAN_ADMIN_PROVINSI;

  if (!admin) {
    return (
      <div className="space-y-field">
        <PageHeader
          judul="Pengguna aktif"
          deskripsi="Pemantauan pengguna yang masuk ke PointSE."
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
            Daftar pengguna dan status kehadirannya hanya ditampilkan untuk admin
            provinsi.
          </EmptyState>
        </Panel>
      </div>
    );
  }

  return (
    <div className="space-y-field">
      <PageHeader
        judul="Pengguna aktif"
        deskripsi="Pantau pengguna yang masuk ke PointSE di provinsi Anda. Status online berasal dari heartbeat dashboard dan diperbarui otomatis."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Admin Provinsi</p>
            <p className="mt-1 text-xs">
              {labelWilayah(sesi.kdprov, sesi.kdkab)}
            </p>
          </div>
        }
      />
      <PenggunaAktifClient />
    </div>
  );
}
