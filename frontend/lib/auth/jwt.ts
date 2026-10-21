import { jwtVerify, SignJWT, type JWTPayload } from "jose";

import { peranDariOrg } from "./peran";
import type { SesiPengguna, StateOidc } from "./types";
import { jalurAman } from "./url";

const ISSUER = process.env.AUTH_ISSUER ?? "pointse";
const AUDIENCE = process.env.AUTH_AUDIENCE ?? "pointse-backend";
const AUDIENCE_OIDC = "pointse-oidc";

function kunci(): Uint8Array {
  const rahasia = process.env.AUTH_SECRET;
  if (!rahasia || rahasia.length < 32) {
    throw new Error("AUTH_SECRET belum diisi (minimal 32 karakter)");
  }
  return new TextEncoder().encode(rahasia);
}

function teks(payload: JWTPayload, nama: string): string | undefined {
  const nilai = payload[nama];
  return typeof nilai === "string" && nilai.trim() ? nilai : undefined;
}

/** Buat token sesi HS256 yang juga diverifikasi backend FastAPI. */
export async function tandaTanganSesi(pengguna: SesiPengguna): Promise<string> {
  const isi: JWTPayload = {
    username: pengguna.username,
    nama: pengguna.nama,
    nip: pengguna.nip ?? null,
    email: pengguna.email ?? null,
    foto_url: pengguna.foto_url ?? null,
    org: pengguna.org,
    peran: pengguna.peran,
    kdprov: pengguna.kdprov,
    kdkab: pengguna.kdkab,
  };
  return new SignJWT(isi)
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE)
    .setSubject(pengguna.sub)
    .setIssuedAt()
    .setExpirationTime("8h")
    .sign(kunci());
}

/** Verifikasi token sesi; kembalikan null bila tidak valid/kedaluwarsa. */
export async function verifikasiTokenSesi(
  token: string | undefined,
): Promise<SesiPengguna | null> {
  if (!token) {
    return null;
  }
  try {
    const { payload } = await jwtVerify(token, kunci(), {
      algorithms: ["HS256"],
      issuer: ISSUER,
      audience: AUDIENCE,
    });

    const org = teks(payload, "org");
    const peran = org ? peranDariOrg(org) : null;
    const username = teks(payload, "username") ?? teks(payload, "sub");
    const sub = teks(payload, "sub") ?? username;
    if (!org || !peran || !username || !sub) {
      return null;
    }

    return {
      sub,
      username,
      nama: teks(payload, "nama") ?? username,
      nip: teks(payload, "nip") ?? null,
      email: teks(payload, "email") ?? null,
      foto_url: teks(payload, "foto_url") ?? null,
      org,
      peran: peran.nama,
      kdprov: peran.kdprov,
      kdkab: peran.kdkab,
    };
  } catch {
    return null;
  }
}

/** Buat token state OIDC berumur pendek (disimpan di cookie httpOnly). */
export async function tandaTanganState(state: StateOidc): Promise<string> {
  return new SignJWT({
    tujuan: "oidc",
    state: state.state,
    nonce: state.nonce,
    codeVerifier: state.codeVerifier,
    next: state.next,
  })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE_OIDC)
    .setIssuedAt()
    .setExpirationTime("10m")
    .sign(kunci());
}

/** Verifikasi token state OIDC dari cookie. */
export async function verifikasiState(
  token: string | undefined,
): Promise<StateOidc | null> {
  if (!token) {
    return null;
  }
  try {
    const { payload } = await jwtVerify(token, kunci(), {
      algorithms: ["HS256"],
      issuer: ISSUER,
      audience: AUDIENCE_OIDC,
    });
    if (payload.tujuan !== "oidc") {
      return null;
    }
    const state = teks(payload, "state");
    const nonce = teks(payload, "nonce");
    const codeVerifier = teks(payload, "codeVerifier");
    if (!state || !nonce || !codeVerifier) {
      return null;
    }
    return {
      state,
      nonce,
      codeVerifier,
      next: jalurAman(teks(payload, "next")),
    };
  } catch {
    return null;
  }
}
