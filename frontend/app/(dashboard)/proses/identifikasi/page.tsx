import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProsesWorkspace } from "@/components/proses/workspace";

export const metadata: Metadata = {
  title: "1. Identifikasi Titik",
};

export default function IdentifikasiPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        judul="1. Identifikasi Titik"
        deskripsi="Unggah peta batas Wilkerstat. Titik dari geotag master dicocokkan ke poligon, lalu flag awal dihitung."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Status otomatis</p>
            <p className="mt-0.5 text-xs">Diperbarui setiap 5 detik.</p>
          </div>
        }
      />
      <ProsesWorkspace tipe="A" />
    </div>
  );
}
