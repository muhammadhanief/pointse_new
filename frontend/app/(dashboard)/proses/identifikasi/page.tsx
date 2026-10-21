import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProsesWorkspace } from "@/components/proses/workspace";

export const metadata: Metadata = {
  title: "1. Identifikasi Titik",
};

export default function IdentifikasiPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        judul="1. Identifikasi Titik"
        deskripsi="Unggah peta batas Wilkerstat. Titik dari geotag master dicocokkan ke poligon, lalu flag awal dihitung."
      />
      <ProsesWorkspace tipe="A" />
    </div>
  );
}
