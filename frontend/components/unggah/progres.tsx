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
    <div className="mt-4 rounded-lg border border-line bg-paper p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-ink">Mengunggah berkas...</p>
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
          className="mt-2 h-2 overflow-hidden rounded-full bg-line/50"
        >
          <div
            className="h-full rounded-full bg-brand"
            style={{ width: `${persen}%` }}
          />
        </div>
      ) : null}

      <p className="mt-2 text-xs leading-5 text-muted">
        {formatBytes(progres.loaded)}
        {progres.total ? ` dari ${formatBytes(progres.total)}` : " terkirim"}.
        Jangan tutup atau pindah halaman sampai selesai.
      </p>

      <button
        type="button"
        onClick={onBatal}
        className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface px-3 text-sm font-semibold text-ink transition-colors hover:border-brand hover:text-brand-strong"
      >
        Batalkan unggahan
      </button>
    </div>
  );
}
