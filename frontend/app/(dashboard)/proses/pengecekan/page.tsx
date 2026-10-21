import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProsesWorkspace } from "@/components/proses/workspace";

export const metadata: Metadata = {
  title: "2. Unggah Titik Hasil Perbaikan",
};

export default function PengecekanPage() {
  return (
    <div className="space-y-field">
      <PageHeader judul="2. Unggah Titik Hasil Perbaikan" />
      <ProsesWorkspace tipe="B" />
    </div>
  );
}
