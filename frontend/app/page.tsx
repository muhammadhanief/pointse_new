import type { Metadata } from "next";

import { labelPeran } from "@/lib/auth/peran";
import { wajibSesi } from "@/lib/auth/session";

export const metadata: Metadata = {
  title: "Beranda | Pointse",
};

// Halaman ini wajib membaca cookie sesi sebelum merender apa pun; izinkan
// navigasi menunggu pengecekan sesi (bukan shell statis).
export const instant = false;

function BarisInfo({ label, nilai }: { label: string; nilai: string }) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-slate-100 py-3 last:border-0">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="text-right text-sm font-medium text-slate-900">{nilai}</dd>
    </div>
  );
}

export default async function Home() {
  const sesi = await wajibSesi();
  const wilayah =
    sesi.peran === "admin_provinsi"
      ? `Provinsi ${sesi.kdprov}`
      : `Kabupaten/kota ${sesi.kdkab} (provinsi ${sesi.kdprov})`;

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-700 text-xs font-bold text-white">
              BPS
            </div>
            <div>
              <p className="text-xs font-semibold tracking-widest text-blue-700">
                POINTSE
              </p>
              <p className="text-sm font-medium text-slate-700">
                Monitoring Editing Batas Wilkerstat
              </p>
            </div>
          </div>
          <form action="/api/auth/logout" method="post">
            <button
              type="submit"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
            >
              Keluar
            </button>
          </form>
        </div>
      </header>

      <section className="mx-auto max-w-5xl px-6 py-10">
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <p className="text-sm font-medium text-blue-700">
            {labelPeran(sesi.peran)}
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
            Selamat datang, {sesi.nama}
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Anda berhasil masuk memakai SSO BPS. Halaman unggah dan dashboard
            progres akan tersedia pada tahap pengembangan berikutnya.
          </p>

          <dl className="mt-8 grid gap-x-10 md:grid-cols-2">
            <BarisInfo label="Nama" nilai={sesi.nama} />
            <BarisInfo label="Username" nilai={sesi.username} />
            <BarisInfo label="NIP" nilai={sesi.nip ?? "-"} />
            <BarisInfo label="Email" nilai={sesi.email ?? "-"} />
            <BarisInfo label="Kode wilayah kerja" nilai={sesi.org} />
            <BarisInfo label="Wilayah kerja" nilai={wilayah} />
          </dl>
        </div>
      </section>
    </main>
  );
}
