import type { Metadata } from "next";
import Link from "next/link";

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
      <p className="px-1 text-sm text-muted">
        Lihat ringkasan per kabupaten/kota di{" "}
        <Link
          href="/hasil-validasi-sls"
          className="font-medium text-brand underline-offset-4 hover:underline"
        >
          Hasil Validasi SLS
        </Link>
        .
      </p>
    </div>
  );
}
