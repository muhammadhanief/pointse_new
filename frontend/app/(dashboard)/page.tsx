import type { Metadata } from "next";

import {
  PERAN_ADMIN_PROVINSI,
  labelPeran,
  labelWilayah,
} from "@/lib/auth/peran";
import { wajibSesi } from "@/lib/auth/session";
import {
  BarisStatus,
  EmptyState,
  PageHeader,
  Panel,
  TautanAksi,
} from "@/components/dashboard/ui";

export const metadata: Metadata = {
  title: "Beranda",
};

const LANGKAH = [
  {
    judul: "Siapkan master geotag",
    isi: "Admin provinsi mengunggah geotag asli kabupaten/kota. Versi lama tetap disimpan karena masih dirujuk proses sebelumnya.",
  },
  {
    judul: "Unggah peta Wilkerstat",
    isi: "Peta batas SLS/SubSLS menjadi dasar pencocokan titik. Peta ini dipakai ulang oleh langkah 2. Pengecekan Titik.",
  },
  {
    judul: "Jalankan 1. Identifikasi Titik",
    isi: "Titik bangunan dicocokkan ke poligon, lalu flag awal dihitung untuk melihat titik yang perlu perhatian.",
  },
  {
    judul: "Edit titik di QGIS",
    isi: "Unduh GPKG hasil 1. Identifikasi Titik, geser titik atau perbaiki atribut yang salah, lalu simpan hasilnya.",
  },
  {
    judul: "Jalankan 2. Pengecekan Titik",
    isi: "Unggah kembali hasil edit. Aplikasi menghitung posisi baru, perubahan atribut, dan status akhir.",
  },
];

// Beranda membaca sesi di server; izinkan render memblokir.
export const instant = false;

export default async function BerandaPage() {
  const sesi = await wajibSesi();
  const admin = sesi.peran === PERAN_ADMIN_PROVINSI;

  return (
    <div className="space-y-8">
      <PageHeader
        judul="Ringkasan wilayah kerja"
        deskripsi="Pantau kesiapan data dan progres editing titik bangunan terhadap batas Wilkerstat. Halaman ini akan terisi setelah proses pertama dijalankan."
        meta={
          <div className="sm:text-right">
            <p className="font-semibold text-ink">{labelPeran(sesi.peran)}</p>
            <p className="mt-0.5 text-xs">
              {labelWilayah(sesi.kdprov, sesi.kdkab)}
            </p>
          </div>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(18rem,1fr)]">
        <Panel
          judul="Alur kerja"
          deskripsi="Lima langkah dari data mentah sampai status akhir. Langkah 1 dan 2 mengikuti urutan ini."
        >
          <ol className="mt-5 space-y-4">
            {LANGKAH.map((langkah, indeks) => (
              <li key={langkah.judul} className="flex gap-4">
                <span
                  aria-hidden="true"
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-line bg-paper text-xs font-semibold tabular-nums text-muted"
                >
                  {indeks + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink">
                    {langkah.judul}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-muted">
                    {langkah.isi}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <div className="mt-6">
            <TautanAksi href="/proses/identifikasi">
              Buka 1. Identifikasi Titik
            </TautanAksi>
          </div>
        </Panel>

        <Panel
          judul="Status data"
          deskripsi="Ringkasan berkas dan proses yang sedang dipakai."
        >
          <dl className="mt-4">
            <BarisStatus
              label="Master geotag"
              nilai={admin ? "Belum ada" : "Dikelola provinsi"}
              keterangan={
                admin
                  ? "Unggah master untuk kabupaten/kota di provinsi Anda."
                  : "Admin provinsi menyiapkan master untuk wilayah kerja Anda."
              }
            />
            <BarisStatus
              label="Peta terakhir"
              nilai="Belum ada"
              keterangan="Peta dipakai ulang dari 1. Identifikasi Titik yang sukses."
            />
            <BarisStatus
              label="Proses terakhir"
              nilai="Belum ada"
              keterangan="Riwayat langkah 1 dan 2 akan tampil di sini."
            />
          </dl>

          <EmptyState
            judul="Belum ada proses yang bisa diringkas"
            aksi={
              <TautanAksi href="/proses/identifikasi">
                Lihat langkah 1
              </TautanAksi>
            }
          >
            Setelah langkah 1 atau 2 selesai, jumlah titik dan status
            tindakannya akan muncul di ringkasan ini.
          </EmptyState>
        </Panel>
      </div>

      <Panel
        judul="Progres terakhir"
        deskripsi="Rekap per wilayah dihitung dari proses yang sudah sukses."
      >
        <EmptyState
          judul="Belum ada rekap"
          aksi={
            <TautanAksi href="/rekap" varian="sekunder">
              Lihat bentuk rekap
            </TautanAksi>
          }
        >
          Rekap akan muncul setelah ada proses sukses. Halaman rekap memuat
          contoh bentuk tabel, bukan angka hasil proses.
        </EmptyState>
      </Panel>
    </div>
  );
}
