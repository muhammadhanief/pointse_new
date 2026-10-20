/**
 * Penyimpanan token Bearer di browser.
 *
 * API dipanggil langsung dari browser ke backend lintas origin. Callback SSO
 * menulis token ke cookie non-httpOnly ``pointse_api_token``; token juga
 * dicerminkan ke memori/``sessionStorage`` untuk kompatibilitas. Token tidak
 * pernah ditulis ke ``localStorage``.
 */

const KUNCI_TOKEN = "pointse_access_token";
const KUNCI_COOKIE = "pointse_api_token";

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

function bacaCookie(nama: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const awalan = `${nama}=`;
  for (const bagian of document.cookie.split(";")) {
    const bersih = bagian.trim();
    if (bersih.startsWith(awalan)) {
      try {
        return decodeURIComponent(bersih.slice(awalan.length)).trim() || null;
      } catch {
        return null;
      }
    }
  }
  return null;
}

export function ambilToken(): string | null {
  const dariCookie = bacaCookie(KUNCI_COOKIE);
  if (dariCookie) {
    tokenMemori = dariCookie;
    return dariCookie;
  }
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
  if (typeof document !== "undefined") {
    document.cookie = `${KUNCI_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax`;
  }
}
