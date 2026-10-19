import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import {
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

function opsiCookie(umurDetik: number) {
  return {
    httpOnly: true,
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

/** Simpan sesi sebagai cookie httpOnly. */
export async function simpanSesi(pengguna: SesiPengguna): Promise<void> {
  const token = await tandaTanganSesi(pengguna);
  (await cookies()).set(NAMA_COOKIE_SESI, token, opsiCookie(UMUR_SESI));
}

/** Hapus cookie sesi. */
export async function hapusSesi(): Promise<void> {
  (await cookies()).set(NAMA_COOKIE_SESI, "", opsiCookie(0));
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
