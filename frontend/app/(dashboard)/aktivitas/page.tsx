import type { Metadata } from "next";

import { PERAN_ADMIN_PROVINSI, labelWilayah } from "@/lib/auth/peran";
import { wajibSesi } from "@/lib/auth/session";
import { LogAktivitasClient } from "@/components/aktivitas/log-aktivitas";
import {
  EmptyState,
  PageHeader,
  Panel,
  TautanAksi,
} from "@/components/dashboard/ui";

export const metadata: Metadata = {
  title: "Log aktivitas",
};

// Halaman membaca sesi di server; izinkan render memblokir tanpa validasi
// instant navigation (lihat layout dashboard).
export const instant = false;

export default async function LogAktivitasPage() {
  const sesi = await wajibSesi();
  const admin = sesi.peran === PERAN_ADMIN_PROVINSI;

  if (!admin) {
    return (
      <div className="space-y-field">
        <PageHeader
          judul="Log aktivitas"
          deskripsi="Rekaman tindakan pengguna PointSE."
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
            Jejak audit tindakan pengguna hanya ditampilkan untuk admin
            provinsi.
          </EmptyState>
        </Panel>
      </div>
    );
  }

  return (
    <div className="space-y-field">
      <PageHeader
        judul="Log aktivitas"
        deskripsi="Lihat siapa yang login, mengunggah peta, titik hasil perbaikan, atau master geotag. Identitas diambil dari sesi SSO."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Admin Provinsi</p>
            <p className="mt-1 text-xs">
              {labelWilayah(sesi.kdprov, sesi.kdkab)}
            </p>
          </div>
        }
      />
      <LogAktivitasClient />
    </div>
  );
}
