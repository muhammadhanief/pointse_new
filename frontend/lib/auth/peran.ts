/** Pemetaan kode unit SSO BPS (org) ke peran aplikasi. */

import { kodeKabupaten, labelKabupaten } from "@/lib/wilayah/kabupaten";

export const PERAN_ADMIN_PROVINSI = "admin_provinsi" as const;
export const PERAN_PETUGAS_KABKOT = "petugas_kabkot" as const;

export type NamaPeran =
  | typeof PERAN_ADMIN_PROVINSI
  | typeof PERAN_PETUGAS_KABKOT;

export type Peran = {
  nama: NamaPeran;
  kdprov: string;
  kdkab: string | null;
};

/**
 * Turunkan peran dari org SSO.
 *
 * Panduan SSO memakai org 5 digit (mis. 33000/33070); asumsi awal aplikasi
 * memakai 4 digit. Digit terakhir pada org 5 digit adalah kode sub-unit, jadi
 * keduanya dinormalisasi ke 4 digit: 3300 = provinsi, 3307 = kabupaten/kota.
 *
 * @returns null bila org bukan 4/5 digit.
 */
export function peranDariOrg(org: string): Peran | null {
  const bersih = String(org ?? "").trim();
  if (!/^\d{4,5}$/.test(bersih)) {
    return null;
  }

  const kode4 = bersih.slice(0, 4);
  const kdprov = kode4.slice(0, 2);
  if (kode4.slice(2) === "00") {
    return { nama: PERAN_ADMIN_PROVINSI, kdprov, kdkab: null };
  }
  return { nama: PERAN_PETUGAS_KABKOT, kdprov, kdkab: kode4 };
}

/** Label peran untuk ditampilkan di antarmuka. */
export function labelPeran(peran: NamaPeran): string {
  return peran === PERAN_ADMIN_PROVINSI
    ? "Admin Provinsi"
    : "Petugas Kabupaten/Kota";
}

/** Kode kabupaten/kota 4 digit dari kode peta yang mungkin 2 digit. */
export function kodeWilayah(kdprov: string, kdkab: string | null): string {
  return kodeKabupaten(kdprov, kdkab);
}

/** Label wilayah kerja tanpa mengarang nama jika kode belum dikenal. */
export function labelWilayah(kdprov: string, kdkab: string | null): string {
  return kdkab
    ? `${labelKabupaten(kdprov, kdkab)}, Provinsi ${kdprov}`
    : `Provinsi ${kdprov}`;
}
