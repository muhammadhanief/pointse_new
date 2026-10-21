import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { EksporClient } from "@/components/ekspor/ekspor-client";

export const metadata: Metadata = {
  title: "Ekspor rekap",
};

export default function EksporPage() {
  return (
    <div className="space-y-field">
      <PageHeader
        judul="Ekspor rekap"
        deskripsi="Unduh rekap CSV per tingkat wilayah dan rentang tanggal data. Unduhan hasil per job tersedia di popup detail Riwayat upload."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Rekap periodik</p>
            <p className="mt-1 text-xs">CSV sesuai snapshot.</p>
          </div>
        }
      />
      <EksporClient />
    </div>
  );
}
