import type { Metadata } from "next";

import { PERAN_ADMIN_PROVINSI } from "@/lib/auth/peran";
import { wajibSesi } from "@/lib/auth/session";
import {
  BarisStatus,
  EmptyState,
  Panel,
  TautanAksi,
} from "@/components/dashboard/ui";
import { StatusDataAdmin } from "@/components/dashboard/status-data-admin";

export const metadata: Metadata = {
  title: "Beranda",
};

const tautanIsi = "font-medium text-brand underline-offset-4 hover:underline";

const LANGKAH = [
  {
    judul: "Admin Provinsi siapkan Master Landmark",
    isi: (
      <>
        Unduh master landmark dari{" "}
        <a
          href="https://dataspasial.bps.go.id/gs/"
          target="_blank"
          rel="noreferrer"
          className={tautanIsi}
        >
          dataspasial.bps.go.id/gs
        </a>
        .
      </>
    ),
  },
  {
    judul: "Kabupaten/Kota unggah Peta Digital SLS/SubSLS final",
    isi: (
      <>
        Peta batas final menjadi dasar pencocokan titik bangunan.{" "}
        <TautanAksi href="/proses/identifikasi" ringkas>
          Unggah
        </TautanAksi>
      </>
    ),
  },
  {
    judul: 'Sistem menjalankan model "01 Identifikasi Titik.model3"',
    isi: "Master Landmark (1) dan Peta Digital (2) diproses otomatis; hasilnya Hasil Identifikasi Titik (.gpkg).",
  },
  {
    judul: "Edit titik di QGIS",
    isi: "Unduh .gpkg, perbaiki titik atau atribut di QGIS, lalu simpan hasilnya.",
  },
  {
    judul: "Kabupaten/Kota unggah titik hasil perbaikan",
    isi: "Unggah kembali .gpkg hasil edit di QGIS untuk dicek.",
  },
  {
    judul: 'Sistem menjalankan model "02 Pengecekan Titik.model3"',
    isi: "Titik hasil perbaikan (4) dan Peta Digital (2) diproses otomatis; hasilnya Hasil Pengecekan Titik (.gpkg).",
  },
  {
    judul: "Lihat progres di menu Rekap",
    isi: (
      <>
        Lihat target, sisa, dan status per wilayah.{" "}
        <TautanAksi href="/rekap" ringkas>
          Rekap
        </TautanAksi>
      </>
    ),
  },
  {
    judul: "Ulangi langkah 4-7 jika belum selesai",
    isi: "Jika masih ada titik yang belum selesai, perbaiki dan unggah ulang.",
  },
];

// Beranda membaca sesi di server; izinkan render memblokir.
export const instant = false;

export default async function BerandaPage() {
  const sesi = await wajibSesi();
  const admin = sesi.peran === PERAN_ADMIN_PROVINSI;

  return (
    <div className="space-y-6">
      <h1 className="sr-only">Beranda</h1>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(18rem,1fr)]">
        <Panel judul="Alur kerja">
          <ol className="mt-4 space-y-3">
            {LANGKAH.map((langkah, indeks) => (
              <li key={langkah.judul} className="flex gap-3">
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
                  <p className="mt-1 text-sm leading-normal text-muted">
                    {langkah.isi}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </Panel>

        <Panel
          judul="Status data"
          deskripsi={
            admin
              ? "Tabulasi kesiapan data seluruh kabupaten/kota."
              : "Ringkasan berkas dan proses yang sedang dipakai."
          }
        >
          {admin ? (
            <StatusDataAdmin />
          ) : (
            <>
              <dl className="mt-3">
                <BarisStatus
                  label="Master geotag"
                  status="ada"
                  keterangan="Dikelola admin provinsi."
                />
                <BarisStatus
                  label="Peta terakhir"
                  status="belum"
                  keterangan="Dipakai ulang dari Proses 1 yang sukses."
                  aksi={
                    <TautanAksi href="/proses/identifikasi" ringkas>
                      Unggah
                    </TautanAksi>
                  }
                />
                <BarisStatus
                  label="Proses terakhir"
                  status="belum"
                  keterangan="Riwayat Proses 1 dan 2 tampil di sini."
                  aksi={
                    <TautanAksi href="/proses/identifikasi" ringkas>
                      Jalankan
                    </TautanAksi>
                  }
                />
              </dl>

              <EmptyState
                judul="Belum ada proses yang bisa diringkas"
                aksi={
                  <TautanAksi href="/proses/identifikasi">
                    Lihat Proses 1
                  </TautanAksi>
                }
              >
                Setelah Proses 1 atau 2 selesai, jumlah titik dan status
                tindakannya akan muncul di ringkasan ini.
              </EmptyState>
            </>
          )}
        </Panel>
      </div>

    </div>
  );
}
