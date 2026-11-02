import type { Metadata } from "next";

import { GeserClient } from "@/components/geser/geser-client";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Pergeseran Titik",
};

export const instant = false;

export default async function GeserPage() {
  const sesi = await wajibSesi();

  return (
    <div className="space-y-field">
      <header className="border-b border-line pb-4">
        <h1 className="text-lg font-semibold tracking-tight text-ink sm:text-xl">
          Pergeseran Titik
        </h1>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-muted sm:text-sm">
          Titik yang sudah benar tetapi posisinya bergeser dari titik asal
          (Master GS). Ini bukan pencermatan, jadi tidak perlu dikonfirmasi:
          cukup informasi jarak. Atur sendiri ambang meter yang ingin
          ditampilkan (minimal 10 m).
        </p>
      </header>
      <GeserClient kdprov={sesi.kdprov} kdkabAwal={sesi.kdkab} />
    </div>
  );
}
