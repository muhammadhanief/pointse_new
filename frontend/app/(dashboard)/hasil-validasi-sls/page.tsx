import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProgresValidasi } from "@/components/proses/progres-validasi";

export const metadata: Metadata = {
  title: "Hasil Validasi SLS 2026 Semester 1",
};

export default function HasilValidasiPage() {
  return (
    <div className="space-y-field">
      <PageHeader
        judul="Hasil Validasi SLS 2026 Semester 1"
        deskripsi="Run validasi terakhir tiap kabupaten/kota beserta temuan yang belum diperbaiki."
      />
      <ProgresValidasi />
    </div>
  );
}
