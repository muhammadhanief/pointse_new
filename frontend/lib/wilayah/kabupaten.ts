export type Kabupaten = {
  kode: string;
  nama: string;
};

export type Karesidenan = {
  id: string;
  nama: string;
  kdkabList: readonly string[];
};

// Pengelompokan Karesidenan Provinsi Jawa Tengah (33).
export const KARESIDENAN_33: readonly Karesidenan[] = [
  {
    id: "pati",
    nama: "Karesidenan Pati",
    kdkabList: ["3315", "3316", "3317", "3318", "3319", "3320"],
  },
  {
    id: "surakarta",
    nama: "Karesidenan Surakarta",
    kdkabList: ["3309", "3310", "3311", "3312", "3313", "3314", "3372"],
  },
  {
    id: "semarang",
    nama: "Karesidenan Semarang",
    kdkabList: ["3321", "3322", "3324", "3373", "3374"],
  },
  {
    id: "kedu",
    nama: "Karesidenan Kedu",
    kdkabList: ["3305", "3306", "3307", "3308", "3323", "3371"],
  },
  {
    id: "pekalongan",
    nama: "Karesidenan Pekalongan",
    kdkabList: ["3325", "3326", "3327", "3328", "3329", "3375", "3376"],
  },
  {
    id: "banyumas",
    nama: "Karesidenan Banyumas",
    kdkabList: ["3301", "3302", "3303", "3304"],
  },
];

export function daftarKaresidenan(kdprov: string): readonly Karesidenan[] {
  return kdprov === "33" ? KARESIDENAN_33 : [];
}

// Kode BPS 4 digit untuk Provinsi Jawa Tengah (33).
export const KABUPATEN_33: readonly Kabupaten[] = [
  { kode: "3301", nama: "Kabupaten Cilacap" },
  { kode: "3302", nama: "Kabupaten Banyumas" },
  { kode: "3303", nama: "Kabupaten Purbalingga" },
  { kode: "3304", nama: "Kabupaten Banjarnegara" },
  { kode: "3305", nama: "Kabupaten Kebumen" },
  { kode: "3306", nama: "Kabupaten Purworejo" },
  { kode: "3307", nama: "Kabupaten Wonosobo" },
  { kode: "3308", nama: "Kabupaten Magelang" },
  { kode: "3309", nama: "Kabupaten Boyolali" },
  { kode: "3310", nama: "Kabupaten Klaten" },
  { kode: "3311", nama: "Kabupaten Sukoharjo" },
  { kode: "3312", nama: "Kabupaten Wonogiri" },
  { kode: "3313", nama: "Kabupaten Karanganyar" },
  { kode: "3314", nama: "Kabupaten Sragen" },
  { kode: "3315", nama: "Kabupaten Grobogan" },
  { kode: "3316", nama: "Kabupaten Blora" },
  { kode: "3317", nama: "Kabupaten Rembang" },
  { kode: "3318", nama: "Kabupaten Pati" },
  { kode: "3319", nama: "Kabupaten Kudus" },
  { kode: "3320", nama: "Kabupaten Jepara" },
  { kode: "3321", nama: "Kabupaten Demak" },
  { kode: "3322", nama: "Kabupaten Semarang" },
  { kode: "3323", nama: "Kabupaten Temanggung" },
  { kode: "3324", nama: "Kabupaten Kendal" },
  { kode: "3325", nama: "Kabupaten Batang" },
  { kode: "3326", nama: "Kabupaten Pekalongan" },
  { kode: "3327", nama: "Kabupaten Pemalang" },
  { kode: "3328", nama: "Kabupaten Tegal" },
  { kode: "3329", nama: "Kabupaten Brebes" },
  { kode: "3371", nama: "Kota Magelang" },
  { kode: "3372", nama: "Kota Surakarta" },
  { kode: "3373", nama: "Kota Salatiga" },
  { kode: "3374", nama: "Kota Semarang" },
  { kode: "3375", nama: "Kota Pekalongan" },
  { kode: "3376", nama: "Kota Tegal" },
];

export function daftarKabupaten(kdprov: string): readonly Kabupaten[] {
  return kdprov === "33" ? KABUPATEN_33 : [];
}

export function kodeKabupaten(kdprov: string, kdkab: string | null): string {
  if (!kdkab) {
    return kdprov;
  }
  return kdkab.length === 2 ? `${kdprov}${kdkab}` : kdkab;
}

export function namaKabupaten(
  kdprov: string,
  kdkab: string | null,
): string | null {
  const kode = kodeKabupaten(kdprov, kdkab);
  return daftarKabupaten(kdprov).find((satu) => satu.kode === kode)?.nama ?? null;
}

export function labelKabupaten(
  kdprov: string,
  kdkab: string | null,
): string {
  const kode = kodeKabupaten(kdprov, kdkab);
  const nama = namaKabupaten(kdprov, kdkab);
  return nama ? `${kode} ${nama}` : kode;
}

/** Nama tampilan: kota berawalan "KOTA", kabupaten tanpa awalan "Kabupaten". */
export function namaKabupatenTampil(
  kode: string,
  nama: string | null,
): string | null {
  if (!nama) {
    return null;
  }
  const bersih = nama.replace(/^(kabupaten|kota)\s+/i, "").trim();
  if (!bersih) {
    return nama;
  }
  return kode.length >= 3 && kode[2] === "7" ? `KOTA ${bersih}` : bersih;
}
