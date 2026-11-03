import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProgresValidasi } from "@/components/proses/progres-validasi";

export const metadata: Metadata = {
  title: "Progres validasi SLS 2026 Semester 1",
};

export default function ProgresValidasiPage() {
  return (
    <div className="space-y-field">
      <PageHeader
        judul="Progres validasi SLS 2026 Semester 1"
        deskripsi="Status run validasi terakhir tiap kabupaten/kota beserta temuan yang belum diperbaiki."
      />
      <ProgresValidasi />
    </div>
  );
}
