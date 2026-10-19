/** Kembalikan tujuan redirect internal yang aman (cegah open redirect). */
export function jalurAman(nilai: string | null | undefined): string {
  if (
    !nilai ||
    !nilai.startsWith("/") ||
    nilai.startsWith("//") ||
    nilai.includes("\\") ||
    /[\u0000-\u001f]/.test(nilai)
  ) {
    return "/";
  }
  return nilai;
}
