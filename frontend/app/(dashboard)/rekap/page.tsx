import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { RekapWorkspace } from "@/components/rekap/rekap-workspace";
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
        deskripsi="Pantau target awal, perjalanan perbaikan, dan rincian wilayah dari Proses A dan Proses B."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">Data per job</p>
            <p className="mt-0.5 text-xs">
              Angka historis tidak berubah saat upload baru.
            </p>
          </div>
        }
      />
      <RekapWorkspace
        kdprov={sesi.kdprov}
        kdkabAwal={sesi.kdkab}
      />
    </div>
  );
}
