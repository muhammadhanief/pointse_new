import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { RiwayatWorkspace } from "@/components/proses/riwayat";
import type { TipeRun } from "@/lib/api/types";

export const metadata: Metadata = {
  title: "Riwayat upload",
};

const TIPE_VALID: readonly TipeRun[] = ["A", "B", "V"];

/** Tab awal dari query ``?tipe=A|B|V`` (untuk tautan "lihat hasil" sehabis unggah). */
export default async function RiwayatPage({
  searchParams,
}: {
  searchParams: Promise<{ tipe?: string | string[] }>;
}) {
  const params = await searchParams;
  const diminta = Array.isArray(params.tipe) ? params.tipe[0] : params.tipe;
  const bersih = (diminta ?? "").trim().toUpperCase();
  const tabAwal: TipeRun = TIPE_VALID.includes(bersih as TipeRun)
    ? (bersih as TipeRun)
    : "A";

  return (
    <div className="space-y-field">
      <PageHeader
        judul="Riwayat upload"
        deskripsi="Pantau status unggahan peta SLS/SubSLS dan titik hasil perbaikan."
      />
      <RiwayatWorkspace key={tabAwal} tabAwal={tabAwal} />
    </div>
  );
}
