import type { NextRequest } from "next/server";

function hostDari(nilai: string | null | undefined): string | null {
  if (!nilai) {
    return null;
  }
  const teks = nilai.split(",")[0].trim();
  if (!teks) {
    return null;
  }
  try {
    const url = new URL(teks.includes("://") ? teks : `https://${teks}`);
    return url.host.toLowerCase();
  } catch {
    return null;
  }
}

/**
 * Cek Origin berdasarkan host, bukan origin internal Passenger/NGINX.
 * Ini menghindari false 403 saat Next berjalan di balik proxy cPanel.
 */
export function asalDiizinkan(request: NextRequest): boolean {
  const asal = request.headers.get("origin");
  if (!asal) {
    return true;
  }

  const hostAsal = hostDari(asal);
  if (!hostAsal) {
    return false;
  }

  const kandidat = [
    hostDari(request.headers.get("host")),
    hostDari(request.headers.get("x-forwarded-host")),
    hostDari(process.env.APP_URL),
    hostDari(request.nextUrl.origin),
  ];

  return kandidat.some((host) => host === hostAsal);
}

/** URL publik untuk redirect, memakai APP_URL atau header proxy. */
export function urlPublik(request: NextRequest, jalur: string): URL {
  const host =
    request.headers.get("x-forwarded-host")?.split(",")[0]?.trim() ||
    request.headers.get("host");
  const protokol =
    request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim() ||
    request.nextUrl.protocol.replace(":", "");
  const dariHeader = host ? `${protokol}://${host}` : request.nextUrl.origin;
  const dasar = process.env.APP_URL?.trim() || dariHeader;
  return new URL(jalur, dasar.endsWith("/") ? dasar : `${dasar}/`);
}
