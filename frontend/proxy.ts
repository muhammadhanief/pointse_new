import { type NextRequest, NextResponse } from "next/server";

import { NAMA_COOKIE_SESI } from "@/lib/auth/konstanta";
import { verifikasiTokenSesi } from "@/lib/auth/jwt";
import { urlPublik } from "@/lib/http/origin";

/** Cek sesi secara optimistis: halaman terlindungi diarahkan ke /login. */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname, search } = request.nextUrl;
  const token = request.cookies.get(NAMA_COOKIE_SESI)?.value;
  const sesi = await verifikasiTokenSesi(token);

  if (pathname === "/login" || pathname.startsWith("/login/")) {
    if (sesi) {
      return NextResponse.redirect(urlPublik(request, "/"));
    }
    return NextResponse.next();
  }

  if (!sesi) {
    const next = encodeURIComponent(`${pathname}${search}`);
    return NextResponse.redirect(urlPublik(request, `/login?next=${next}`));
  }
  return NextResponse.next();
}

export const config = {
  // Rute API Next (/api) dan callback SSO (/callback) tidak boleh diarahkan
  // ke /login oleh penjaga halaman.
  matcher: ["/((?!api|callback|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
