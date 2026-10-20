import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import {
  NAMA_COOKIE_API,
  NAMA_COOKIE_OIDC,
  NAMA_COOKIE_SESI,
  UMUR_OIDC,
  UMUR_SESI,
} from "./konstanta";
import {
  tandaTanganSesi,
  tandaTanganState,
  verifikasiState,
  verifikasiTokenSesi,
} from "./jwt";
import type { SesiPengguna, StateOidc } from "./types";

function opsiCookie(umurDetik: number, httpOnly = true) {
  return {
    httpOnly,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: umurDetik,
  };
}

/** Baca dan verifikasi sesi dari cookie (di-cache per render). */
export const ambilSesi = cache(async (): Promise<SesiPengguna | null> => {
  const token = (await cookies()).get(NAMA_COOKIE_SESI)?.value;
  return verifikasiTokenSesi(token);
});

/** Sesi wajib; redirect ke /login bila belum masuk. */
export async function wajibSesi(): Promise<SesiPengguna> {
  const sesi = await ambilSesi();
  if (!sesi) {
    redirect("/login");
  }
  return sesi;
}

/** Simpan sesi sebagai cookie httpOnly dan token API yang bisa dibaca browser. */
export async function simpanSesi(pengguna: SesiPengguna): Promise<void> {
  const token = await tandaTanganSesi(pengguna);
  const jar = await cookies();
  jar.set(NAMA_COOKIE_SESI, token, opsiCookie(UMUR_SESI));
  // Frontend memanggil API lintas origin langsung dari browser karena server
  // cPanel tidak dapat menjangkau domain backend. Token ini harus terbaca JS.
  jar.set(NAMA_COOKIE_API, token, opsiCookie(UMUR_SESI, false));
}

/** Hapus cookie sesi server dan token API browser. */
export async function hapusSesi(): Promise<void> {
  const jar = await cookies();
  jar.set(NAMA_COOKIE_SESI, "", opsiCookie(0));
  jar.set(NAMA_COOKIE_API, "", opsiCookie(0, false));
}

/** Simpan state OIDC (state, nonce, PKCE) di cookie berumur pendek. */
export async function simpanStateOidc(state: StateOidc): Promise<void> {
  const token = await tandaTanganState(state);
  (await cookies()).set(NAMA_COOKIE_OIDC, token, opsiCookie(UMUR_OIDC));
}

/** Verifikasi state OIDC dari cookie. */
export async function ambilStateOidc(
  token: string | undefined,
): Promise<StateOidc | null> {
  return verifikasiState(token);
}

/** Hapus cookie state OIDC setelah callback. */
export async function hapusStateOidc(): Promise<void> {
  (await cookies()).set(NAMA_COOKIE_OIDC, "", opsiCookie(0));
}
