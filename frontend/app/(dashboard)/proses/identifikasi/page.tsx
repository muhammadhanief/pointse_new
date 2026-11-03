import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProsesWorkspace } from "@/components/proses/workspace";

export const metadata: Metadata = {
  title: "1. Unggah Peta SLS/SubSLS Final 2025 Semester 2",
};

export default function IdentifikasiPage() {
  return (
    <div className="space-y-field">
      <PageHeader judul="1. Unggah Peta SLS/SubSLS Final 2025 Semester 2" />
      <ProsesWorkspace tipe="A" />
    </div>
  );
}
