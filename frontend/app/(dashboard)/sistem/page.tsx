import type { Metadata } from "next";

import { PERAN_ADMIN_PROVINSI, labelWilayah } from "@/lib/auth/peran";
import { wajibSesi } from "@/lib/auth/session";
import { StatusSistem } from "@/components/sistem/status-sistem";
import {
  EmptyState,
  PageHeader,
  Panel,
  TautanAksi,
} from "@/components/dashboard/ui";

export const metadata: Metadata = {
  title: "Status sistem",
};

// Halaman membaca sesi di server; izinkan render memblokir tanpa validasi
// instant navigation (lihat layout dashboard).
export const instant = false;

export default async function StatusSistemPage() {
  const sesi = await wajibSesi();
  const admin = sesi.peran === PERAN_ADMIN_PROVINSI;

  if (!admin) {
    return (
      <div className="space-y-field">
        <PageHeader
          judul="Status sistem"
          deskripsi="Pemantauan worker, antrean, dan pemakaian server."
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
            Status worker dan server hanya ditampilkan untuk admin provinsi.
          </EmptyState>
        </Panel>
      </div>
    );
  }

  return (
    <div className="space-y-field">
      <PageHeader
        judul="Status sistem"
        deskripsi="Pantau worker, antrean job, RAM, CPU, dan disk server. Halaman ini hanya membaca status; tidak mengubah job atau konfigurasi."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Admin Provinsi</p>
            <p className="mt-1 text-xs">
              {labelWilayah(sesi.kdprov, sesi.kdkab)}
            </p>
          </div>
        }
      />
      <StatusSistem />
    </div>
  );
}
