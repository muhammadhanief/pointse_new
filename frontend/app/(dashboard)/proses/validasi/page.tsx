import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProsesWorkspace } from "@/components/proses/workspace";

export const metadata: Metadata = {
  title: "3. Validasi Peta SLS/SubSLS 2026 Semester 1",
};

export default function ValidasiPage() {
  return (
    <div className="space-y-field">
      <PageHeader judul="3. Validasi Peta SLS/SubSLS 2026 Semester 1" />
      <ProsesWorkspace tipe="V" />
    </div>
  );
}
