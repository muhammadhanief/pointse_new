import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function PageHeader({
  judul,
  deskripsi,
  meta,
}: {
  judul: string;
  deskripsi: string;
  meta?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[28px] sm:leading-9">
          {judul}
        </h1>
        <p className="mt-1.5 text-sm leading-normal text-muted">{deskripsi}</p>
      </div>
      {meta ? <div className="shrink-0 text-sm text-muted">{meta}</div> : null}
    </header>
  );
}

export function Panel({
  judul,
  deskripsi,
  children,
  className = "",
}: {
  judul: string;
  deskripsi?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-line bg-surface p-4 sm:p-5 ${className}`}
    >
      <div className="max-w-2xl">
        <h2 className="text-lg font-semibold tracking-tight text-ink">
          {judul}
        </h2>
        {deskripsi ? (
          <p className="mt-1 text-sm leading-normal text-muted">{deskripsi}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function BadgeStatus({ status }: { status: "ada" | "belum" }) {
  const gaya =
    status === "ada"
      ? "border-success/20 bg-success-soft text-success"
      : "border-line bg-paper text-muted";

  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${gaya}`}
    >
      {status === "ada" ? "Ada" : "Belum ada"}
    </span>
  );
}

export function BarisStatus({
  label,
  nilai,
  status,
  keterangan,
  aksi,
}: {
  label: string;
  nilai?: string;
  status?: "ada" | "belum";
  keterangan?: string;
  aksi?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line py-3 last:border-0">
      <div className="min-w-0">
        <dt className="text-sm font-medium text-ink">{label}</dt>
        {keterangan ? (
          <p className="mt-0.5 text-xs leading-5 text-muted">{keterangan}</p>
        ) : null}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        <dd className="text-right text-xs font-medium text-muted">
          {status ? <BadgeStatus status={status} /> : nilai}
        </dd>
        {aksi}
      </div>
    </div>
  );
}

export function EmptyState({
  judul,
  children,
  aksi,
}: {
  judul: string;
  children: ReactNode;
  aksi?: ReactNode;
}) {
  return (
    <div className="mt-4 rounded-lg border border-dashed border-line bg-paper/70 p-4">
      <p className="text-sm font-semibold text-ink">{judul}</p>
      <div className="mt-1 text-sm leading-normal text-muted">{children}</div>
      {aksi ? <div className="mt-3">{aksi}</div> : null}
    </div>
  );
}

export function CatatanContoh({ children }: { children: ReactNode }) {
  return (
    <div
      role="note"
      className="rounded-lg border border-accent/25 bg-accent-soft/60 px-4 py-3 text-sm leading-normal text-ink"
    >
      <span className="font-semibold">Data contoh. </span>
      {children}
    </div>
  );
}

export function TautanAksi({
  href,
  children,
  varian = "utama",
  ringkas = false,
}: {
  href: string;
  children: ReactNode;
  varian?: "utama" | "sekunder";
  ringkas?: boolean;
}) {
  const gaya =
    varian === "utama"
      ? "bg-brand text-white hover:bg-brand-strong"
      : "border border-line-strong bg-surface text-ink hover:border-brand hover:text-brand-strong";
  const ukuran = ringkas
    ? "min-h-6 px-2 text-xs leading-4"
    : "min-h-11 px-4 text-sm";

  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center rounded-lg font-semibold transition-colors ${ukuran} ${gaya}`}
    >
      {children}
    </Link>
  );
}

export function TombolAksi({
  children,
  varian = "utama",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  varian?: "utama" | "sekunder";
}) {
  const gaya =
    varian === "utama"
      ? "bg-brand text-white hover:bg-brand-strong"
      : "border border-line-strong bg-surface text-ink hover:border-brand hover:text-brand-strong";

  return (
    <button
      type={type}
      className={`inline-flex min-h-11 items-center justify-center rounded-lg px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${gaya} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function BarProgres({ nilai }: { nilai: number }) {
  return (
    <div className="flex items-center justify-end gap-3">
      <div
        className="h-1.5 w-20 overflow-hidden rounded-full bg-brand-soft"
        aria-hidden="true"
      >
        <div
          className="h-full rounded-full bg-brand"
          style={{ width: `${nilai}%` }}
        />
      </div>
      <span className="tabular-nums">{nilai}%</span>
    </div>
  );
}
