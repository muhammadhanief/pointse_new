import { NextResponse } from "next/server";

import { ambilSesi } from "@/lib/auth/session";

/** Identitas pengguna yang sedang login (dipakai komponen klien bila perlu). */
export async function GET(): Promise<NextResponse> {
  const sesi = await ambilSesi();
  if (!sesi) {
    return NextResponse.json(
      { detail: "belum login" },
      { status: 401, headers: { "cache-control": "no-store" } },
    );
  }
  return NextResponse.json(sesi, {
    headers: { "cache-control": "no-store" },
  });
}
