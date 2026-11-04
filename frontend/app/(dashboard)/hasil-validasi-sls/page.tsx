import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { ProgresValidasi } from "@/components/proses/progres-validasi";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Hasil Validasi SLS 2026 Semester 1",
};

// Halaman membaca sesi di server (untuk daftar kabupaten sesuai peran);
// izinkan render memblokir tanpa validasi instant navigation.
export const instant = false;

export default async function HasilValidasiPage() {
  const sesi = await wajibSesi();

  return (
    <div className="space-y-field">
      <PageHeader
        judul="Hasil Validasi SLS 2026 Semester 1"
        deskripsi="Run validasi terakhir tiap kabupaten/kota beserta temuan yang belum diperbaiki."
      />
      <ProgresValidasi
        kdprov={sesi.kdprov}
        kdkab={sesi.kdkab}
        peran={sesi.peran}
      />
    </div>
  );
}
