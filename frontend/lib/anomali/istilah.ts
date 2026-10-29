/**
 * Teks penjelasan jenis pencermatan titik (dipakai modal "Apa arti jenis ini?").
 *
 * Sumber istilah: Master GS = berkas A (daftar tugas), Geotag Kabkot = berkas B
 * (hasil perbaikan kabupaten/kota).
 */

export type IstilahJenis = {
  kode: string;
  judul: string;
  isi: string;
  solusi?: string;
};

export const PENGANTAR =
  "Master GS = berkas A (daftar tugas). Geotag Kabkot = berkas B (hasil perbaikan kabupaten/kota). Satu titik hanya masuk satu jenis.";

export const ISTILAH: readonly IstilahJenis[] = [
  {
    kode: "hilang",
    judul: "Titik hilang",
    isi: "Titik target di Master GS (flag_repair = 1 run model 1) yang assignment_id nya tidak ada di Geotag hasil perbaikan kabkot, dan unique_bang-nya juga tidak ketemu (atau ketemu lebih dari satu sehingga ambigu). Kemungkinan petugas tidak sengaja mengubah assignment_id.",
    solusi:
      'Cari kehilangan ini di poin pemeriksaan "Titik baru" lalu betulkan assignment_idnya lalu upload ulang.',
  },
  {
    kode: "id_berubah",
    judul: "Assignment ID berubah",
    isi: "Titik target tidak ada dengan id lama, tetapi ada tepat satu baris di Geotag Kabkot dengan unique_bang yang sama. Petugas mengganti id, bukan membuang titik.",
    solusi: "Betulkan id assignment.",
  },
  {
    kode: "luar_wilayah",
    judul: "Di luar wilayah",
    isi: "Titik ada di Geotag hasil perbaikan kabkot, tetapi posisinya tidak masuk poligon wilkerstat mana pun (hasil join peta kosong). Biasanya titik digeser melewati batas atau poligonnya bolong. Bisa diwajarkan jika memang titik berada di luar kabupaten/kota anda.",
  },
  {
    kode: "posisi_menyimpang",
    judul: "Posisi menyimpang",
    isi: "Titik ada di Geotag hasil perbaikan kabkot, kabupaten mengklaim flag_repair = 0 (sudah beres) tapi sistem mendeteksi kalau titik jatuh tidak di subsls yang sama dengan level_6_fullcode di Geotag Master GS.",
  },
  {
    kode: "kode_berubah",
    judul: "Kode SLS berubah",
    isi: "Titik ada di Geotag Kabkot dan sistem menilai beres, tetapi level_6_fullcode di berkas B berbeda dari kode penugasan di Master GS.",
  },
  {
    kode: "regresi",
    judul: "Awal tidak masalah, sekarang jadi masalah",
    isi: "Titik ada di Master GS tetapi bukan target (hasil run model 1 flag repairnya sudah = 0 : harusnya tidak perlu perbaikan), tapi petugas menggeser titik dan jatuh di subSLS yang salah dengan level_6_fullcode Master Geotag GS.",
  },
  {
    kode: "titik_baru",
    judul: "Titik baru",
    isi: "assignment_id di Geotag Kabkot yang tidak ada di Master GS sama sekali. Ini sih paling petugasnya ga sengaja ngubah isian assignment_id.",
  },
];
