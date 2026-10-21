import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Shell } from "@/components/dashboard/shell";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: {
    default: "Pointse",
    template: "%s | Pointse",
  },
  description:
    "Monitoring progres editing titik bangunan terhadap batas Wilkerstat BPS.",
};

export const instant = false;

export default async function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  const sesi = await wajibSesi();

  return (
    <Shell
      sesi={{
        nama: sesi.nama,
        peran: sesi.peran,
        kdprov: sesi.kdprov,
        kdkab: sesi.kdkab,
        foto_url: sesi.foto_url,
      }}
    >
      {children}
    </Shell>
  );
}
