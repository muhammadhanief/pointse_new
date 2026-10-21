import type { Metadata } from "next";

import { TabulasiRekap } from "@/components/rekap/tabulasi-rekap";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Rekap progres",
};

export const instant = false;

export default async function RekapPage() {
  const sesi = await wajibSesi();

  return (
    <div className="space-y-3">
      <header className="border-b border-line pb-3">
        <h1 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">
          Rekap progres
        </h1>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted sm:text-sm">
          Tabulasi target dan penyelesaian wilayah. Klik kabupaten/kota untuk
          turun ke kecamatan, lalu desa/kelurahan.
        </p>
      </header>
      <TabulasiRekap kdprov={sesi.kdprov} kdkabAwal={sesi.kdkab} />
    </div>
  );
}
