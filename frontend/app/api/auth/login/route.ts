import { createHash, randomBytes } from "node:crypto";

import { type NextRequest, NextResponse } from "next/server";

import {
  ambilKonfigurasiOidc,
  buatUrlOtorisasi,
} from "@/lib/auth/oidc";
import { simpanStateOidc } from "@/lib/auth/session";
import { jalurAman } from "@/lib/auth/url";

/** Mulai login SSO BPS: buat state + PKCE, lalu redirect ke Keycloak. */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const next = jalurAman(request.nextUrl.searchParams.get("next"));

  try {
    const config = await ambilKonfigurasiOidc();
    const state = randomBytes(32).toString("base64url");
    const nonce = randomBytes(32).toString("base64url");
    const codeVerifier = randomBytes(48).toString("base64url");
    const challenge = createHash("sha256")
      .update(codeVerifier)
      .digest("base64url");

    await simpanStateOidc({ state, nonce, codeVerifier, next });
    return NextResponse.redirect(
      buatUrlOtorisasi(config, state, nonce, challenge),
    );
  } catch (galat) {
    console.error(
      "Login SSO gagal:",
      galat instanceof Error ? galat.message : "kesalahan tidak dikenal",
    );
    return NextResponse.redirect(
      new URL("/login?error=konfigurasi", request.url),
    );
  }
}
