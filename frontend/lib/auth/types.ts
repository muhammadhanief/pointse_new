import type { NamaPeran } from "./peran";

/** Identitas pengguna yang disimpan di cookie sesi (JWT HS256). */
export type SesiPengguna = {
  sub: string;
  username: string;
  nama: string;
  nip?: string | null;
  email?: string | null;
  //: Kode wilayah kerja hasil pemetaan org/provinceCode+cityCode (4/5 digit).
  org: string;
  peran: NamaPeran;
  kdprov: string;
  kdkab: string | null;
};

/** Data sementara selama proses OIDC (state, nonce, PKCE, tujuan setelah login). */
export type StateOidc = {
  state: string;
  nonce: string;
  codeVerifier: string;
  next: string;
};
