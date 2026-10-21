import { formatBytes } from "@/lib/format";

import type { ProgresUnggah, StatusUnggah } from "./use-unggah";

export function ProgresUnggahan({
  status,
  progres,
  onBatal,
}: {
  status: StatusUnggah;
  progres: ProgresUnggah;
  onBatal: () => void;
}) {
  if (status !== "mengunggah") {
    return null;
  }

  const persen =
    progres.total && progres.total > 0
      ? Math.min(100, Math.round((progres.loaded / progres.total) * 100))
      : null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Mengunggah berkas"
      className="fixed inset-0 z-[100] grid place-items-center bg-ink/45 p-4"
    >
      <div className="w-full max-w-sm rounded-xl border border-line bg-surface p-4 shadow-2xl">
        <div className="flex items-center justify-between gap-field">
          <p className="text-sm font-semibold text-ink">Mengunggah berkas...</p>
          {persen !== null ? (
            <p className="text-sm font-semibold tabular-nums text-ink">
              {persen}%
            </p>
          ) : null}
        </div>

        {persen !== null ? (
          <div
            role="progressbar"
            aria-label="Kemajuan unggahan"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={persen}
            className="mt-2 h-2.5 overflow-hidden rounded-full bg-line/50"
          >
            <div
              className="h-full rounded-full bg-brand transition-[width] duration-150"
              style={{ width: `${persen}%` }}
            />
          </div>
        ) : (
          <div
            aria-hidden="true"
            className="mt-3 h-2.5 animate-pulse rounded-full bg-brand-soft"
          />
        )}

        <p className="mt-2 text-xs leading-5 text-muted">
          {formatBytes(progres.loaded)}
          {progres.total ? ` dari ${formatBytes(progres.total)}` : " terkirim"}.
          Jangan tutup atau pindah halaman sampai selesai.
        </p>

        <button
          type="button"
          onClick={onBatal}
          className="mt-3 inline-flex min-h-9 w-full items-center justify-center rounded-lg border border-line-strong bg-surface px-tombol text-sm font-semibold text-ink transition-colors hover:border-brand hover:text-brand-strong"
        >
          Batalkan unggahan
        </button>
      </div>
    </div>
  );
}
