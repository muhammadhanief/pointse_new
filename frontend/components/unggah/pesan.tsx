import type { ReactNode } from "react";

import type { StatusUnggah } from "./use-unggah";

export function PesanUnggah({
  status,
  pesan,
  children,
}: {
  status: StatusUnggah;
  pesan: string | null;
  children?: ReactNode;
}) {
  if (status === "sukses") {
    return (
      <div
        role="status"
        className="mt-4 rounded-lg border border-success/30 bg-success-soft px-4 py-3 text-sm leading-6 text-success"
      >
        {children ?? "Unggahan berhasil."}
      </div>
    );
  }

  if (status === "galat") {
    return (
      <div
        role="alert"
        className="mt-4 rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm leading-6 text-danger"
      >
        {pesan}
      </div>
    );
  }

  if (status === "batal") {
    return (
      <div
        role="status"
        className="mt-4 rounded-lg border border-line bg-paper px-4 py-3 text-sm leading-6 text-muted"
      >
        {pesan ?? "Unggahan dibatalkan."}
      </div>
    );
  }

  return null;
}
