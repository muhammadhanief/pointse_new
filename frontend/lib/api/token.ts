/**
 * Penyimpanan token Bearer di browser.
 *
 * Frontend statis tidak memakai cookie sesi. Token disimpan di memori dan
 * dicerminkan ke ``sessionStorage`` agar bertahan saat halaman dimuat ulang di
 * tab yang sama; token tidak pernah ditulis ke ``localStorage``.
 */

const KUNCI_TOKEN = "pointse_access_token";

let tokenMemori: string | null = null;

function penyimpanan(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function simpanToken(token: string): void {
  const bersih = token.trim();
  tokenMemori = bersih || null;
  const tempat = penyimpanan();
  if (!tempat) {
    return;
  }
  if (tokenMemori) {
    tempat.setItem(KUNCI_TOKEN, tokenMemori);
  } else {
    tempat.removeItem(KUNCI_TOKEN);
  }
}

export function ambilToken(): string | null {
  if (tokenMemori) {
    return tokenMemori;
  }
  const tempat = penyimpanan();
  if (!tempat) {
    return null;
  }
  const tersimpan = tempat.getItem(KUNCI_TOKEN);
  tokenMemori = tersimpan?.trim() || null;
  return tokenMemori;
}

export function hapusToken(): void {
  tokenMemori = null;
  penyimpanan()?.removeItem(KUNCI_TOKEN);
}
