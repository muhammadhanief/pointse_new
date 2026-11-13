/** Halaman pertama yang dibuka setelah login berhasil (grafik langsung penuh). */
export const HALAMAN_AWAL = "/rekonsiliasi-batas?layar-penuh=1";

/** Kembalikan tujuan redirect internal yang aman (cegah open redirect). */
export function jalurAman(nilai: string | null | undefined): string {
  if (
    !nilai ||
    !nilai.startsWith("/") ||
    nilai.startsWith("//") ||
    nilai.includes("\\") ||
    /[\u0000-\u001f]/.test(nilai)
  ) {
    return HALAMAN_AWAL;
  }
  return nilai;
}