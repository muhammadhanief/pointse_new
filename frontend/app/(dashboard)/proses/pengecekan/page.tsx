import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProsesWorkspace } from "@/components/proses/workspace";

export const metadata: Metadata = {
  title: "2. Pengecekan Titik",
};

export default function PengecekanPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        judul="2. Pengecekan Titik"
        deskripsi="Pilih hasil 1. Identifikasi Titik sebagai sumber peta, lalu unggah GPKG yang sudah diedit di QGIS."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Status otomatis</p>
            <p className="mt-0.5 text-xs">Diperbarui setiap 5 detik.</p>
          </div>
        }
      />
      <ProsesWorkspace tipe="B" />
    </div>
  );
}
