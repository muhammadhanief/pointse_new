"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-2xl rounded-xl border border-line bg-surface p-6 sm:p-8">
      <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">
        Halaman gagal dimuat
      </h1>
      <p className="mt-2 text-sm leading-6 text-muted">
        Ada gangguan saat menyiapkan halaman ini. Coba muat ulang. Bila masih
        gagal, kembali ke beranda dan periksa proses yang sedang berjalan.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={reset}
          className="inline-flex min-h-11 items-center rounded-lg bg-brand px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-strong"
        >
          Coba lagi
        </button>
        <Link
          href="/"
          className="inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface px-4 text-sm font-semibold text-ink transition-colors hover:border-brand hover:text-brand-strong"
        >
          Kembali ke beranda
        </Link>
      </div>
    </div>
  );
}
