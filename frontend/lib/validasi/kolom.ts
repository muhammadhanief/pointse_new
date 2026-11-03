/** 17 kolom wajib peta SLS 2026 Semester 1 (disalin dari dokumen Validasi Atribut).
 *
 *  Sumber: ``app/validasi_sls.py`` (``KOLOM_PETA_V`` + ``PANJANG_MAKS_V``).
 *  Semua bertipe teks, kecuali ``tingkat`` yang bertipe bilangan bulat.
 *  Nilai aktual di master memakai 16 digit untuk ``idsubsls``.
 */

export type KolomValidasi = {
  nama: string;
  tipe: string;
  panjang: number;
};

export const KOLOM_PETA_VALIDASI: KolomValidasi[] = [
  { nama: "kdprov", tipe: "teks", panjang: 2 },
  { nama: "kdkab", tipe: "teks", panjang: 2 },
  { nama: "kdkec", tipe: "teks", panjang: 3 },
  { nama: "kddesa", tipe: "teks", panjang: 3 },
  { nama: "kdsls", tipe: "teks", panjang: 4 },
  { nama: "kdsubsls", tipe: "teks", panjang: 2 },
  { nama: "idsls", tipe: "teks", panjang: 14 },
  // Dokumen sumber menulis 18, tetapi seluruh data aktual memakai 16 digit.
  { nama: "idsubsls", tipe: "teks", panjang: 16 },
  { nama: "nmprov", tipe: "teks", panjang: 50 },
  { nama: "nmkab", tipe: "teks", panjang: 50 },
  { nama: "nmkec", tipe: "teks", panjang: 50 },
  { nama: "nmdesa", tipe: "teks", panjang: 50 },
  { nama: "nmsls", tipe: "teks", panjang: 100 },
  { nama: "rw_dki", tipe: "teks", panjang: 3 },
  { nama: "tingkat", tipe: "bilangan bulat", panjang: 1 },
  { nama: "nm_gedung", tipe: "teks", panjang: 50 },
  { nama: "posisi", tipe: "teks", panjang: 50 },
];
