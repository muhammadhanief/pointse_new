import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { RiwayatWorkspace } from "@/components/proses/riwayat";

export const metadata: Metadata = {
  title: "Riwayat upload",
};

export default function RiwayatPage() {
  return (
    <div className="space-y-field">
      <PageHeader
        judul="Riwayat upload"
        deskripsi="Pantau status unggahan peta SLS/SubSLS dan titik hasil perbaikan."
      />
      <RiwayatWorkspace />
    </div>
  );
}
