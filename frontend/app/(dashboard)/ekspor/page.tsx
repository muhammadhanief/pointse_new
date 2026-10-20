import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { EksporClient } from "@/components/ekspor/ekspor-client";

export const metadata: Metadata = {
  title: "Ekspor",
};

export default function EksporPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        judul="Ekspor hasil"
        deskripsi="Unduh berkas untuk diedit di QGIS atau diolah lebih lanjut. Ekspor per job memakai hasil job yang sudah sukses."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Hanya job sukses</p>
            <p className="mt-0.5 text-xs">CSV dan GPKG sesuai ketersediaan.</p>
          </div>
        }
      />
      <EksporClient />
    </div>
  );
}
