"use client";

import Link from "next/link";

import type { TipeRun } from "@/lib/api/types";

import { FormProsesA } from "./form-a";
import { FormProsesB } from "./form-b";

export function ProsesWorkspace({ tipe }: { tipe: TipeRun }) {
  return (
    <div className="space-y-field">
      {tipe === "A" ? (
        <FormProsesA onSelesai={() => undefined} />
      ) : (
        <FormProsesB onSelesai={() => undefined} />
      )}

      <p className="px-1 text-sm text-muted">
        Pantau status unggahan di{" "}
        <Link
          href="/riwayat"
          className="font-medium text-brand underline-offset-4 hover:underline"
        >
          Riwayat upload
        </Link>
        .
      </p>
    </div>
  );
}
