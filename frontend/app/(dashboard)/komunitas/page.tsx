import type { Metadata } from "next";

import { PageHeader } from "@/components/dashboard/ui";
import { RuangKomunitas } from "@/components/komunitas/ruang-komunitas";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Komunitas",
};

export const instant = false;

export default async function KomunitasPage() {
  const sesi = await wajibSesi();

  return (
    <div className="space-y-field">
      <PageHeader
        judul="Komunitas"
        deskripsi="Ruang berbagi temuan error .txt saat unggah ke dataspasial.bps.go.id/gs, diskusi solusi antar kabupaten/kota, serta usulan penambahan rule validasi otomatis di PointSE."
      />
      <RuangKomunitas
        kdprov={sesi.kdprov}
        kdkab={sesi.kdkab}
        peran={sesi.peran}
      />
    </div>
  );
}
