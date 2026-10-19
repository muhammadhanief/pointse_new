import "server-only";

import { execFile } from "node:child_process";
import { promisify } from "node:util";

import {
  createLocalJWKSet,
  jwtVerify,
  type JSONWebKeySet,
  type JWTPayload,
} from "jose";

import { peranDariOrg } from "./peran";
import type { SesiPengguna } from "./types";

const execFileAsync = promisify(execFile);

type KonfigurasiOidc = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  userinfo_endpoint: string;
  jwks_uri: string;
};

type TokenOidc = {
  access_token: string;
  id_token: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
};

type Klaim = Record<string, unknown>;

let cacheKonfigurasi:
  | { data: KonfigurasiOidc; sampai: number }
  | undefined;

let cacheJwks:
  | { url: string; set: ReturnType<typeof createLocalJWKSet> }
  | undefined;

let cacheTokenLayanan: { token: string; sampai: number } | undefined;

const AGEN = "pointse/1.0 (BPS)";

type OpsiHttp = {
  method: "GET" | "POST";
  headers?: Record<string, string>;
  body?: string;
};

type HasilHttp = { status: number; teks: string };

/**
 * Cloudflare di accounts.bps.go.id memblokir fingerprint TLS Node/undici,
 * sedangkan curl lolos. Semua panggilan SSO/API Pegawai lewat curl; bila curl
 * tidak tersedia, jatuh ke `fetch` bawaan (mungkin diblokir Cloudflare).
 */
async function curlHttp(url: string, opsi: OpsiHttp): Promise<HasilHttp> {
  const headers = {
    "user-agent": AGEN,
    accept: "application/json",
    ...(opsi.headers ?? {}),
  };
  const argumen = ["-sS", "--max-time", "30", "-X", opsi.method];
  for (const [nama, nilai] of Object.entries(headers)) {
    argumen.push("-H", `${nama}: ${nilai}`);
  }
  if (opsi.body !== undefined) {
    argumen.push("--data-raw", opsi.body);
  }
  argumen.push("-w", "\n%{http_code}", url);

  const { stdout } = await execFileAsync("curl", argumen, {
    maxBuffer: 10 * 1024 * 1024,
    windowsHide: true,
  });
  const potong = stdout.lastIndexOf("\n");
  if (potong < 0) {
    throw new Error("respons curl tidak valid");
  }
  const status = Number(stdout.slice(potong + 1).trim());
  if (!Number.isFinite(status)) {
    throw new Error("status HTTP curl tidak valid");
  }
  return { status, teks: stdout.slice(0, potong) };
}

async function fetchHttp(url: string, opsi: OpsiHttp): Promise<HasilHttp> {
  const resp = await fetch(url, {
    method: opsi.method,
    headers: {
      "user-agent": AGEN,
      accept: "application/json",
      ...(opsi.headers ?? {}),
    },
    body: opsi.body,
    cache: "no-store",
  });
  return { status: resp.status, teks: await resp.text() };
}

async function permintaanHttp(
  url: string,
  opsi: OpsiHttp,
): Promise<HasilHttp> {
  try {
    return await curlHttp(url, opsi);
  } catch (galat) {
    const kode = (galat as NodeJS.ErrnoException).code;
    if (kode === "ENOENT" || kode === "EACCES") {
      return fetchHttp(url, opsi);
    }
    throw galat;
  }
}

function env(nama: string): string {
  const nilai = process.env[nama];
  if (!nilai) {
    throw new Error(`${nama} belum diisi`);
  }
  return nilai;
}

function urlKeycloak(): string {
  return (process.env.KEYCLOAK_URL ?? "https://accounts.bps.go.id").replace(
    /\/+$/,
    "",
  );
}

function realmKeycloak(): string {
  return process.env.KEYCLOAK_REALM ?? "pegawai";
}

function clientId(): string {
  return env("KEYCLOAK_CLIENT_ID");
}

function clientSecret(): string {
  return env("KEYCLOAK_CLIENT_SECRET");
}

function redirectUri(): string {
  return env("KEYCLOAK_REDIRECT_URI");
}

function scopeOidc(): string {
  return process.env.KEYCLOAK_SCOPE ?? "openid profile email";
}

/** Baca OIDC discovery; disimpan di memori selama satu jam. */
export async function ambilKonfigurasiOidc(): Promise<KonfigurasiOidc> {
  if (cacheKonfigurasi && cacheKonfigurasi.sampai > Date.now()) {
    return cacheKonfigurasi.data;
  }

  const alamat = `${urlKeycloak()}/realms/${encodeURIComponent(
    realmKeycloak(),
  )}/.well-known/openid-configuration`;
  const resp = await permintaanHttp(alamat, { method: "GET" });
  if (resp.status !== 200) {
    throw new Error(`OIDC discovery gagal (HTTP ${resp.status})`);
  }
  const data = JSON.parse(resp.teks) as Partial<KonfigurasiOidc>;
  const wajib: (keyof KonfigurasiOidc)[] = [
    "issuer",
    "authorization_endpoint",
    "token_endpoint",
    "userinfo_endpoint",
    "jwks_uri",
  ];
  for (const nama of wajib) {
    if (typeof data[nama] !== "string" || !data[nama]) {
      throw new Error(`OIDC discovery tidak memuat ${nama}`);
    }
  }

  const hasil = data as KonfigurasiOidc;
  cacheKonfigurasi = { data: hasil, sampai: Date.now() + 60 * 60 * 1000 };
  return hasil;
}

/** Susun URL Authorization Endpoint dengan state, nonce, dan PKCE S256. */
export function buatUrlOtorisasi(
  config: KonfigurasiOidc,
  state: string,
  nonce: string,
  challenge: string,
): URL {
  const url = new URL(config.authorization_endpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", clientId());
  url.searchParams.set("redirect_uri", redirectUri());
  url.searchParams.set("scope", scopeOidc());
  url.searchParams.set("state", state);
  url.searchParams.set("nonce", nonce);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  return url;
}

/** Tukar authorization code dengan token di Token Endpoint (client confidential). */
export async function tukarKode(
  config: KonfigurasiOidc,
  code: string,
  codeVerifier: string,
): Promise<TokenOidc> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri(),
    code_verifier: codeVerifier,
  });
  const basic = Buffer.from(
    `${clientId()}:${clientSecret()}`,
    "utf8",
  ).toString("base64");

  const resp = await permintaanHttp(config.token_endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      authorization: `Basic ${basic}`,
    },
    body: body.toString(),
  });
  if (resp.status !== 200) {
    throw new Error(`tukar kode gagal (HTTP ${resp.status})`);
  }
  const data = JSON.parse(resp.teks) as Partial<TokenOidc>;
  if (!data.access_token || !data.id_token) {
    throw new Error("token endpoint tidak mengembalikan access_token/id_token");
  }
  return data as TokenOidc;
}

/** Verifikasi tanda tangan, issuer, audience, dan nonce ID token. */
export async function verifikasiIdToken(
  config: KonfigurasiOidc,
  idToken: string,
  nonce: string,
): Promise<JWTPayload> {
  if (cacheJwks?.url !== config.jwks_uri) {
    const resp = await permintaanHttp(config.jwks_uri, { method: "GET" });
    if (resp.status !== 200) {
      throw new Error(`JWKS gagal diambil (HTTP ${resp.status})`);
    }
    const jwks = JSON.parse(resp.teks) as JSONWebKeySet;
    cacheJwks = {
      url: config.jwks_uri,
      set: createLocalJWKSet(jwks),
    };
  }
  const { payload } = await jwtVerify(idToken, cacheJwks.set, {
    issuer: config.issuer,
    audience: clientId(),
  });
  if (payload.nonce !== nonce) {
    throw new Error("nonce ID token tidak cocok");
  }
  return payload;
}

/** Ambil data profil pengguna dari UserInfo Endpoint. */
export async function ambilUserInfo(
  config: KonfigurasiOidc,
  accessToken: string,
): Promise<Klaim> {
  const resp = await permintaanHttp(config.userinfo_endpoint, {
    method: "GET",
    headers: { authorization: `Bearer ${accessToken}` },
  });
  if (resp.status !== 200) {
    throw new Error(`userinfo gagal (HTTP ${resp.status})`);
  }
  return JSON.parse(resp.teks) as Klaim;
}

function klaimTeks(klaim: Klaim, nama: string): string | undefined {
  const nilai = klaim[nama];
  if (Array.isArray(nilai)) {
    const pertama = nilai.find((satu) => satu !== null && satu !== undefined);
    return pertama === undefined ? undefined : String(pertama);
  }
  if (typeof nilai === "string") {
    return nilai.trim() ? nilai : undefined;
  }
  if (typeof nilai === "number") {
    return String(nilai);
  }
  return undefined;
}

function klaimGabungan(userInfo: Klaim, idToken: JWTPayload): Klaim {
  const atribut =
    userInfo.attributes &&
    typeof userInfo.attributes === "object" &&
    !Array.isArray(userInfo.attributes)
      ? (userInfo.attributes as Klaim)
      : {};
  return { ...idToken, ...atribut, ...userInfo };
}

/**
 * Token service account (Client Credentials) untuk REST API Data Pegawai.
 * Cache singkat supaya beberapa login berurutan tidak selalu meminta token baru.
 */
async function tokenLayanan(config: KonfigurasiOidc): Promise<string> {
  if (cacheTokenLayanan && cacheTokenLayanan.sampai > Date.now()) {
    return cacheTokenLayanan.token;
  }

  const basic = Buffer.from(
    `${clientId()}:${clientSecret()}`,
    "utf8",
  ).toString("base64");
  const resp = await permintaanHttp(config.token_endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      authorization: `Basic ${basic}`,
    },
    body: new URLSearchParams({ grant_type: "client_credentials" }).toString(),
  });
  if (resp.status !== 200) {
    throw new Error(`token layanan gagal (HTTP ${resp.status})`);
  }
  const data = JSON.parse(resp.teks) as {
    access_token?: string;
    expires_in?: number;
  };
  if (!data.access_token) {
    throw new Error("token layanan tidak memuat access_token");
  }

  const umur = typeof data.expires_in === "number" ? data.expires_in : 60;
  cacheTokenLayanan = {
    token: data.access_token,
    sampai: Date.now() + Math.max(15, umur - 30) * 1000,
  };
  return data.access_token;
}

function atributDariItem(item: unknown): Klaim | undefined {
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return undefined;
  }
  const obj = item as Klaim;
  const atribut = obj.attributes;
  if (atribut && typeof atribut === "object" && !Array.isArray(atribut)) {
    return atribut as Klaim;
  }
  return obj;
}

/**
 * Pilih kode wilayah kerja dari atribut pegawai.
 *
 * ``org`` adalah kode unit organisasi, tetapi pada data BPS bisa tidak sejalan
 * dengan provinsi kerja (mis. org 92000 untuk pegawai provinceCode 33).
 * ``provinceCode`` + ``cityCode`` adalah lokasi kerja; pakai keduanya bila
 * awalan provinsi pada ``org`` tidak cocok. ``cityCode`` 00 = tingkat provinsi.
 */
function kodeWilayahDariAtribut(klaim: Klaim): string | undefined {
  const org = klaimTeks(klaim, "org");
  const provinsi = klaimTeks(klaim, "provinceCode");
  const kabupaten = klaimTeks(klaim, "cityCode");
  const orgValid = org && /^\d{4,5}$/.test(org) ? org : undefined;

  if (
    provinsi &&
    /^\d{2}$/.test(provinsi) &&
    provinsi !== "00" &&
    kabupaten &&
    /^\d{2}$/.test(kabupaten)
  ) {
    const kode = `${provinsi}${kabupaten}`;
    if (!orgValid || orgValid.slice(0, 2) !== provinsi) {
      return kode;
    }
  }
  return orgValid;
}

/**
 * Ambil atribut pegawai dari REST API Data Pegawai BPS (Client Credentials).
 *
 * Client OIDC belum tentu memetakan atribut ``org`` ke UserInfo/ID token
 * (atribut tergantung scope dan mapper client). API Data Pegawai selalu
 * tersedia di realm ``pegawai`` dan mengembalikan ``attributes.org`` serta
 * ``provinceCode``/``cityCode``.
 */
async function atributPegawaiDariApi(
  config: KonfigurasiOidc,
  klaim: Klaim,
): Promise<Klaim | undefined> {
  const kandidat: { jalur: string; nilai: string }[] = [];
  const username =
    klaimTeks(klaim, "preferred_username") ?? klaimTeks(klaim, "username");
  if (username) {
    kandidat.push({ jalur: "username", nilai: username });
  }
  const email = klaimTeks(klaim, "email");
  if (email) {
    kandidat.push({ jalur: "email", nilai: email });
  }
  const nipBaru = klaimTeks(klaim, "employeeNumber");
  if (nipBaru) {
    kandidat.push({ jalur: "nipbaru", nilai: nipBaru });
  }
  const nipLama = klaimTeks(klaim, "employeeID") ?? klaimTeks(klaim, "nip");
  if (nipLama) {
    kandidat.push({ jalur: "nip", nilai: nipLama });
  }
  if (kandidat.length === 0) {
    return undefined;
  }

  const token = await tokenLayanan(config);
  const dasar = urlKeycloak();
  for (const { jalur, nilai } of kandidat) {
    const resp = await permintaanHttp(
      `${dasar}/realms/pegawai/api/${jalur}/${encodeURIComponent(nilai)}`,
      {
        method: "GET",
        headers: { authorization: `Bearer ${token}` },
      },
    );
    if (resp.status === 401 || resp.status === 403) {
      // Token service account tidak berhak/kedaluwarsa: jangan lanjut diam-diam.
      cacheTokenLayanan = undefined;
      throw new Error("api_pegawai");
    }
    if (resp.status !== 200) {
      continue;
    }
    const data = JSON.parse(resp.teks) as unknown;
    if (!Array.isArray(data)) {
      continue;
    }
    for (const item of data) {
      const atribut = atributDariItem(item);
      if (
        atribut &&
        (klaimTeks(atribut, "org") || klaimTeks(atribut, "provinceCode"))
      ) {
        return atribut;
      }
    }
  }
  return undefined;
}

/**
 * Susun sesi aplikasi dari klaim UserInfo/ID token.
 *
 * Bila client OIDC tidak memetakan ``org`` ke token, atribut diambil dari REST
 * API Data Pegawai BPS memakai service account.
 *
 * Raises:
 *   Error("org") bila org tetap tidak ditemukan; Error("org_tidak_valid") bila
 *   formatnya tidak dikenali; Error("api_pegawai") bila API pegawai gagal.
 */
export async function susunPengguna(
  config: KonfigurasiOidc,
  userInfo: Klaim,
  idToken: JWTPayload,
): Promise<SesiPengguna> {
  const subUserInfo = klaimTeks(userInfo, "sub");
  const subIdToken = typeof idToken.sub === "string" ? idToken.sub : undefined;
  if (subUserInfo && subIdToken && subUserInfo !== subIdToken) {
    throw new Error("sub UserInfo tidak cocok dengan ID token");
  }

  const klaim = klaimGabungan(userInfo, idToken);
  let org = kodeWilayahDariAtribut(klaim);
  if (!org) {
    try {
      const atribut = await atributPegawaiDariApi(config, klaim);
      org = atribut ? kodeWilayahDariAtribut(atribut) : undefined;
    } catch (galat) {
      if (galat instanceof Error && galat.message === "api_pegawai") {
        throw galat;
      }
    }
  }
  if (!org) {
    throw new Error("org");
  }
  const peran = peranDariOrg(org);
  if (!peran) {
    throw new Error("org_tidak_valid");
  }

  const username =
    klaimTeks(klaim, "preferred_username") ??
    klaimTeks(klaim, "username") ??
    subIdToken ??
    subUserInfo;
  if (!username) {
    throw new Error("username tidak ditemukan");
  }

  const namaDepan = klaimTeks(klaim, "given_name");
  const namaBelakang = klaimTeks(klaim, "family_name");
  const nama =
    klaimTeks(klaim, "name") ??
    [namaDepan, namaBelakang].filter(Boolean).join(" ").trim() ??
    username;

  return {
    sub: subIdToken ?? subUserInfo ?? username,
    username,
    nama: nama || username,
    nip:
      klaimTeks(klaim, "employeeID") ??
      klaimTeks(klaim, "employeeNumber") ??
      klaimTeks(klaim, "nip") ??
      null,
    email: klaimTeks(klaim, "email") ?? null,
    org,
    peran: peran.nama,
    kdprov: peran.kdprov,
    kdkab: peran.kdkab,
  };
}
