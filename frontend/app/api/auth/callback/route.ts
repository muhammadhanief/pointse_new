import { timingSafeEqual } from "node:crypto";

import { type NextRequest, NextResponse } from "next/server";

import {
  ambilKonfigurasiOidc,
  ambilUserInfo,
  susunPengguna,
  tukarKode,
  verifikasiIdToken,
} from "@/lib/auth/oidc";
import { NAMA_COOKIE_OIDC } from "@/lib/auth/konstanta";
import {
  ambilStateOidc,
  hapusStateOidc,
  simpanSesi,
} from "@/lib/auth/session";
import { jalurAman } from "@/lib/auth/url";
import { urlPublik } from "@/lib/http/origin";

function samaAman(kiri: string, kanan: string): boolean {
  const a = Buffer.from(kiri);
  const b = Buffer.from(kanan);
  return a.length === b.length && timingSafeEqual(a, b);
}

async function kembaliGagal(
  request: NextRequest,
  kode: string,
): Promise<NextResponse> {
  await hapusStateOidc();
  return NextResponse.redirect(urlPublik(request, `/login?error=${kode}`));
}

/** Callback OIDC: cocokkan state, tukar kode, verifikasi token, buat sesi. */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const params = request.nextUrl.searchParams;
  if (params.get("error")) {
    return kembaliGagal(request, "sso");
  }

  const code = params.get("code");
  const state = params.get("state");
  const stateTersimpan = await ambilStateOidc(
    request.cookies.get(NAMA_COOKIE_OIDC)?.value,
  );
  if (
    !code ||
    !state ||
    !stateTersimpan ||
    !samaAman(stateTersimpan.state, state)
  ) {
    return kembaliGagal(request, "state");
  }

  try {
    const config = await ambilKonfigurasiOidc();
    const token = await tukarKode(
      config,
      code,
      stateTersimpan.codeVerifier,
    );
    const idToken = await verifikasiIdToken(
      config,
      token.id_token,
      stateTersimpan.nonce,
    );
    const userInfo = await ambilUserInfo(config, token.access_token);
    const pengguna = await susunPengguna(config, userInfo, idToken);

    await simpanSesi(pengguna);
    await hapusStateOidc();
    return NextResponse.redirect(
      urlPublik(request, jalurAman(stateTersimpan.next)),
    );
  } catch (galat) {
    const pesan = galat instanceof Error ? galat.message : "";
    const kode =
      pesan === "org" || pesan === "org_tidak_valid"
        ? "org"
        : pesan === "api_pegawai"
          ? "api_pegawai"
          : "login";
    console.error("Callback SSO gagal:", pesan || "kesalahan tidak dikenal");
    return kembaliGagal(request, kode);
  }
}
