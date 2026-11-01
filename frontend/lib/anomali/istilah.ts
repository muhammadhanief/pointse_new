/**
 * Teks penjelasan jenis pencermatan titik (dipakai modal "Penjelasan poin
 * pencermatan").
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

/** Label dropdown/tabel; menimpa label bawaan API supaya seragam dengan modal. */
export const LABEL_JENIS: Readonly<Record<string, string>> = {
  hilang: "Titik hilang",
  id_berubah: "Assignment ID berubah",
  luar_wilayah: "Di luar wilayah",
  posisi_menyimpang: "Posisi menyimpang",
  kode_berubah: "Kode SLS berubah",
  digeser: "Digeser ≥10 m",
  regresi: "Awal Tidak masalah, sekarang jadi masalah",
  titik_baru: "Titik baru",
};

export const PENGANTAR =
  "Master GS = berkas A (daftar tugas). Geotag Kabkot = berkas B (hasil perbaikan kabupaten/kota). Satu titik hanya masuk satu jenis.";

export const ISTILAH: readonly IstilahJenis[] = [
  {
    kode: "hilang",
    judul: "Titik hilang",
    isi: "Titik target di Master GS (flag_repair = 1 run model 1) yang assignment_id nya tidak ada di Geotag hasil perbaikan kabkot, , dan unique_bang-nya juga tidak ketemu (atau ketemu lebih dari satu sehingga ambigu). kemungkinan petugas ga sengaja mengubah assignment_id. solusinya cari kehilangan ini di poin pemeriksaan \"Titik baru\" lalu betulkan assignment_idnya lalu upload ulang",
  },
  {
    kode: "luar_wilayah",
    judul: "Di luar wilayah",
    isi: "Titik ada di Geotag hasil perbaikan kabkot, tetapi posisinya tidak masuk poligon wilkerstat mana pun (hasil join peta kosong). Biasanya titik digeser melewati batas atau poligonnya bolong. Bisa diwajarkan jika memang titik berada di luar kabupaten/kota anda",
  },
  {
    kode: "posisi_menyimpang",
    judul: "Posisi menyimpang",
    isi: "Titik ada di geotag hasil perbaikan kabkot, kabupaten megklaim flag_repair = 0 (sudah beres) tapi sistem mendeteksi kalau titik jatuh tidak di subsls yang sama dengan level_6_fullcode di geotag master GS.",
  },
  {
    kode: "digeser",
    judul: "Digeser ≥10 m",
    isi: "Titik yang menurut sistem sudah benar (flag_repair akhir 0 dan atribut flag tidak diedit petugas), tetapi posisinya bergeser 10 meter atau lebih dari titik asal di Master GS. Pergeseran di bawah 10 meter dianggap getaran GPS dan tidak dimunculkan. Jarak dihitung dari kedua koordinat (bukan hanya latitude seperti flag_position model), jadi geseran mendatar pun terhitung.",
    solusi: "Periksa apakah pergeseran sejauh itu memang sesuai kondisi lapangan (misalnya titik asal salah tempat). Kalau sesuai, konfirmasi \"Sesuai Kondisi Kenyataan\" dengan catatan alasannya.",
  },
  {
    kode: "regresi",
    judul: "Awal Tidak masalah, sekarang jadi masalah",
    isi: "Titik ada di Master GS tetapi bukan target (hasil run model 1 flag repairnya sudah = 0 : harusnya tidak perlu perbaikan ), tapi petugas menggeser titik dan jatuh di subSLS yang salah dengan level_6_fullcode master Geotag GS",
  },
  {
    kode: "titik_baru",
    judul: "Titik baru",
    isi: "assignment_id di Geotag Kabkot yang tidak ada di Master GS sama sekali. ini sih paling petugasnya ga sengaja ngubah isian assignment_id",
  },
];
