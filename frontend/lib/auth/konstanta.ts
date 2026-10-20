/** Nama cookie sesi dan state OIDC (dipakai juga oleh proxy). */
export const NAMA_COOKIE_SESI = "pointse_session";
//: Salinan token untuk dipakai browser saat memanggil API lintas origin.
//: Tidak httpOnly karena JavaScript harus mengirimnya sebagai Bearer.
export const NAMA_COOKIE_API = "pointse_api_token";
export const NAMA_COOKIE_OIDC = "pointse_oidc";

/** Umur sesi aplikasi dan state OIDC (detik). */
export const UMUR_SESI = 60 * 60 * 8;
export const UMUR_OIDC = 60 * 10;
