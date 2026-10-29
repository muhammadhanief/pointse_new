import type { Metadata } from "next";

import { AnomaliClient } from "@/components/anomali/anomali-client";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Pencermatan Titik",
};

export const instant = false;

export default async function AnomaliPage() {
  const sesi = await wajibSesi();

  return (
    <div className="space-y-field">
      <header className="border-b border-line pb-4">
        <h1 className="text-lg font-semibold tracking-tight text-ink sm:text-xl">
          Pencermatan Titik
        </h1>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted sm:text-sm">
          Titik yang menurut sistem masih bermasalah pada Proses B terakhir:
          hilang, id berubah, posisi menyimpang, di luar wilayah, kode SLS
          berubah, bermasalah lagi, atau titik baru. Rekap memakai klaim
          kabupaten, halaman ini alat auditnya.
        </p>
      </header>
      <AnomaliClient kdprov={sesi.kdprov} kdkabAwal={sesi.kdkab} />
    </div>
  );
}
