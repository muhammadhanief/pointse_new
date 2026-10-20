import type { TipeRun } from "@/lib/api/types";

export function labelTipe(tipe: TipeRun): string {
  return tipe === "A" ? "1. Identifikasi Titik" : "2. Pengecekan Titik";
}

export function labelNomorJob(
  nomor: number | null | undefined,
  kata = "Job",
): string {
  return nomor && nomor > 0 ? `${kata} ke-${nomor}` : kata;
}

/** Ganti istilah teknis A/B dari backend dengan istilah layar. */
export function istilahProses(teks: string): string {
  return teks
    .replace(/\bProses A\b/g, "1. Identifikasi Titik")
    .replace(/\bProses B\b/g, "2. Pengecekan Titik");
}
