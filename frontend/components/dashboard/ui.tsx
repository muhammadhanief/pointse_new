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
    <header className="flex flex-col gap-5 border-b border-line pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-3xl">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
          {judul}
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted">{deskripsi}</p>
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
      className={`rounded-xl border border-line bg-surface p-5 sm:p-6 ${className}`}
    >
      <div className="max-w-2xl">
        <h2 className="font-display text-xl font-semibold tracking-tight text-ink">
          {judul}
        </h2>
        {deskripsi ? (
          <p className="mt-1.5 text-sm leading-6 text-muted">{deskripsi}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function BarisStatus({
  label,
  nilai,
  keterangan,
}: {
  label: string;
  nilai: string;
  keterangan?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-5 border-b border-line py-3 last:border-0">
      <div>
        <dt className="text-sm font-medium text-ink">{label}</dt>
        {keterangan ? (
          <p className="mt-0.5 text-xs leading-5 text-muted">{keterangan}</p>
        ) : null}
      </div>
      <dd className="shrink-0 text-right text-sm font-semibold text-muted">
        {nilai}
      </dd>
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
    <div className="mt-5 rounded-lg border border-dashed border-line bg-paper/70 p-5">
      <p className="text-sm font-semibold text-ink">{judul}</p>
      <div className="mt-1 text-sm leading-6 text-muted">{children}</div>
      {aksi ? <div className="mt-4">{aksi}</div> : null}
    </div>
  );
}

export function CatatanContoh({ children }: { children: ReactNode }) {
  return (
    <div
      role="note"
      className="rounded-lg border border-accent/25 bg-accent-soft/60 px-4 py-3 text-sm leading-6 text-ink"
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
}: {
  href: string;
  children: ReactNode;
  varian?: "utama" | "sekunder";
}) {
  const gaya =
    varian === "utama"
      ? "bg-brand text-white hover:bg-brand-strong"
      : "border border-line-strong bg-surface text-ink hover:border-brand hover:text-brand-strong";

  return (
    <Link
      href={href}
      className={`inline-flex min-h-11 items-center justify-center rounded-lg px-4 text-sm font-semibold transition-colors ${gaya}`}
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
