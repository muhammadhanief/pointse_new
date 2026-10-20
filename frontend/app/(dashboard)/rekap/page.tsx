import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { DashboardRekap } from "@/components/rekap/dashboard-rekap";

export const metadata: Metadata = {
  title: "Rekap progres",
};

export default function RekapPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        judul="Rekap progres"
        deskripsi="Jumlah titik dibagi menjadi belum, benar sejak awal, dan sudah ditindak. Rekap disimpan per job agar angka historis tidak berubah."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Run sukses terakhir</p>
            <p className="mt-0.5 text-xs">
              Satu baris per kabupaten/kota; rincian mengikuti run tersebut.
            </p>
          </div>
        }
      />
      <DashboardRekap />
    </div>
  );
}
