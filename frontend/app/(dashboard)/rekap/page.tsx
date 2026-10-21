import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { TabulasiRekap } from "@/components/rekap/tabulasi-rekap";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Rekap progres",
};

export const instant = false;

export default async function RekapPage() {
  const sesi = await wajibSesi();

  return (
    <div className="space-y-8">
      <PageHeader
        judul="Rekap progres"
        deskripsi="Tabulasi target dan penyelesaian wilayah. Klik kabupaten/kota untuk turun ke kecamatan, lalu desa/kelurahan."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Target A pertama</p>
            <p className="mt-0.5 text-xs">
              Dibandingkan dengan Proses B terakhir.
            </p>
          </div>
        }
      />
      <TabulasiRekap kdprov={sesi.kdprov} kdkabAwal={sesi.kdkab} />
    </div>
  );
}
