import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { RekonsiliasiBatasClient } from "@/components/rekonsiliasi/rekonsiliasi-batas-client";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Rekonsiliasi Batas Kab/Kota",
};

export const instant = false;

export default async function RekonsiliasiBatasPage({
  searchParams,
}: PageProps<"/rekonsiliasi-batas">) {
  const sesi = await wajibSesi();
  const params = await searchParams;

  return (
    <div className="space-y-field">
      <PageHeader
        judul="Rekonsiliasi Batas Antar-Kabupaten/Kota (2026 S1)"
        deskripsi="Pemeriksaan otomatis celah kosong (gap) dan tumpang tindih (overlap) di sepanjang garis perbatasan antar-kabupaten/kota dari unggahan peta Validasi SLS 2026 Semester 1."
      />
      <RekonsiliasiBatasClient
        kdprov={sesi.kdprov}
        kdkab={sesi.kdkab}
        peran={sesi.peran}
        bukaLayarPenuhAwal={params["layar-penuh"] === "1"}
      />
    </div>
  );
}