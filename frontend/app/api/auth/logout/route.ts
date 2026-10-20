import { type NextRequest, NextResponse } from "next/server";

import { hapusSesi } from "@/lib/auth/session";
import { urlPublik } from "@/lib/http/origin";

/** Logout lokal (cookie sesi dihapus); sesi SSO BPS di server tetap hidup. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  await hapusSesi();
  return NextResponse.redirect(urlPublik(request, "/login"), { status: 303 });
}
