import { type NextRequest, NextResponse } from "next/server";

import { NAMA_COOKIE_SESI } from "@/lib/auth/konstanta";
import { verifikasiTokenSesi } from "@/lib/auth/jwt";

/** Cek sesi secara optimistis: halaman terlindungi diarahkan ke /login. */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname, search } = request.nextUrl;
  const token = request.cookies.get(NAMA_COOKIE_SESI)?.value;
  const sesi = await verifikasiTokenSesi(token);

  if (pathname === "/login" || pathname.startsWith("/login/")) {
    if (sesi) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next();
  }

  if (!sesi) {
    const next = encodeURIComponent(`${pathname}${search}`);
    return NextResponse.redirect(new URL(`/login?next=${next}`, request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
