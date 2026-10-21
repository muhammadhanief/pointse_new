import { formatBytes } from "@/lib/format";

export function BidangBerkas({
  id,
  label,
  accept,
  berkas,
  onPilih,
  keterangan,
  disabled = false,
}: {
  id: string;
  label: string;
  accept: string;
  berkas: File | null;
  onPilih: (berkas: File | null) => void;
  keterangan: string;
  disabled?: boolean;
}) {
  const bantuanId = `${id}-bantuan`;

  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type="file"
        accept={accept}
        disabled={disabled}
        aria-describedby={bantuanId}
        onChange={(event) => onPilih(event.target.files?.[0] ?? null)}
        className="mt-1 block w-full cursor-pointer rounded-lg border border-line-strong bg-surface p-2 text-sm text-muted file:mr-3 file:min-h-9 file:cursor-pointer file:rounded-md file:border-0 file:bg-brand file:px-3 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-60"
      />
      <div id={bantuanId} className="mt-bantuan text-xs leading-5 text-muted">
        {berkas ? (
          <p>
            <span className="font-medium text-ink">{berkas.name}</span>{" "}
            <span className="tabular-nums">({formatBytes(berkas.size)})</span>
          </p>
        ) : (
          <p>{keterangan}</p>
        )}
        {berkas && berkas.size > 100 * 1024 * 1024 ? (
          <p className="mt-1 text-accent-strong">
            Berkas di atas 100 MB. Unggahan bisa lama; jangan tutup halaman
            sampai selesai.
          </p>
        ) : null}
      </div>
    </div>
  );
}
