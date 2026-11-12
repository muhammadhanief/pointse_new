"use client";

export type ArahUrut = "asc" | "desc";

/** Panah kecil penanda kolom urut aktif pada kepala tabel.
 *
 * Saat tidak aktif, panah disembunyikan dan baru muncul samar ketika baris
 * kepala di-hover, supaya tabel tidak penuh ornamen.
 */
export function PenandaUrut({
  aktif,
  arah,
}: {
  aktif: boolean;
  arah: ArahUrut;
}) {
  return (
    <span
      aria-hidden="true"
      className={`text-[10px] leading-none transition-opacity ${
        aktif
          ? "text-brand-strong opacity-100"
          : "text-line-strong opacity-0 group-hover:opacity-70"
      }`}
    >
      {aktif ? (arah === "asc" ? "▲" : "▼") : "↕"}
    </span>
  );
}
