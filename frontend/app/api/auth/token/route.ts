import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { NAMA_COOKIE_SESI } from "@/lib/auth/konstanta";
import { ambilSesi } from "@/lib/auth/session";

/**
 * Berikan token Bearer ke JavaScript same-origin.
 *
 * Ini diperlukan karena sebagian hosting cPanel memaksa semua cookie menjadi
 * ``HttpOnly``. Token tetap hanya bisa diambil setelah sesi server diverifikasi.
 */
export async function GET(): Promise<NextResponse> {
  const sesi = await ambilSesi();
  if (!sesi) {
    return NextResponse.json(
      { detail: "belum login" },
      { status: 401, headers: { "cache-control": "no-store" } },
    );
  }

  const token = (await cookies()).get(NAMA_COOKIE_SESI)?.value;
  if (!token) {
    return NextResponse.json(
      { detail: "token sesi tidak tersedia" },
      { status: 401, headers: { "cache-control": "no-store" } },
    );
  }

  return NextResponse.json(
    { token },
    { headers: { "cache-control": "no-store" } },
  );
}
