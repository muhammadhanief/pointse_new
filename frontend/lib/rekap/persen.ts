/** Persen penyelesaian dari hitungan titik, bukan dari nilai kiriman API.
 *
 *  API membulatkan persennya (2 angka di belakang koma), sehingga sisa 1 titik
 *  dari 65.034 titik jadi `100,00%` dan wilayah itu terlihat tuntas. Dengan
 *  menghitung dari `selesai`/`target` yang berupa bilangan bulat, wilayah
 *  seperti itu tetap terbaca `99,9985%` dan tidak pernah tampil 100% selama
 *  masih ada sisa.
 */
export function persenPenyelesaian(nilai: {
  target: number;
  selesai: number;
}): number | null {
  return nilai.target > 0 ? (nilai.selesai / nilai.target) * 100 : null;
}