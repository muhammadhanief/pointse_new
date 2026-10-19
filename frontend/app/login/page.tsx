import type { Metadata } from "next";
import { Suspense } from "react";

import { jalurAman } from "@/lib/auth/url";

export const metadata: Metadata = {
  title: "Masuk | Pointse",
  description: "Monitoring progres editing batas Wilkerstat BPS",
};

const PESAN_GALAT: Record<string, string> = {
  konfigurasi:
    "Konfigurasi SSO belum lengkap. Hubungi administrator aplikasi.",
  state: "Sesi login sudah kedaluwarsa. Silakan coba masuk lagi.",
  sso: "Login dibatalkan atau ditolak oleh SSO BPS.",
  org: "Akun SSO tidak memiliki atribut unit kerja (org). Hubungi admin SSO BPS.",
  api_pegawai:
    "Gagal mengambil data unit kerja dari API Pegawai BPS. Coba lagi beberapa saat atau hubungi administrator.",
  login: "Login gagal. Silakan coba lagi atau hubungi administrator.",
};

function pesanGalat(nilai: string | string[] | undefined): string | null {
  const kode = Array.isArray(nilai) ? nilai[0] : nilai;
  return kode ? (PESAN_GALAT[kode] ?? PESAN_GALAT.login) : null;
}

async function IsiLogin({
  searchParams,
}: {
  searchParams: PageProps<"/login">["searchParams"];
}) {
  const params = await searchParams;
  const galat = pesanGalat(params.error);
  const next = jalurAman(
    typeof params.next === "string" ? params.next : undefined,
  );
  const tautan = `/api/auth/login?next=${encodeURIComponent(next)}`;

  return (
    <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-200/60">
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-700 text-sm font-bold text-white">
          BPS
        </div>
        <div>
          <p className="text-sm font-semibold tracking-wide text-blue-700">
            POINTSE
          </p>
          <p className="text-xs text-slate-500">Badan Pusat Statistik</p>
        </div>
      </div>

      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
        Monitoring Editing Batas Wilkerstat
      </h1>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Masuk dengan akun SSO BPS untuk memantau progres perbaikan titik
        bangunan terhadap batas SLS/SubSLS.
      </p>

      {galat ? (
        <div
          role="alert"
          className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
        >
          {galat}
        </div>
      ) : null}

      <a
        href={tautan}
        className="mt-7 flex h-11 w-full items-center justify-center rounded-lg bg-blue-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      >
        Masuk dengan SSO BPS
      </a>

      <p className="mt-5 text-center text-xs leading-5 text-slate-500">
        Gunakan akun pegawai BPS. Anda akan diarahkan ke halaman login resmi
        <span className="font-medium text-slate-700"> accounts.bps.go.id</span>.
      </p>
    </div>
  );
}

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-slate-100 via-white to-blue-50 px-4 py-12">
      <Suspense
        fallback={
          <div className="h-80 w-full max-w-md animate-pulse rounded-2xl bg-white shadow-xl" />
        }
      >
        <IsiLogin searchParams={searchParams} />
      </Suspense>
      <p className="mt-8 text-xs text-slate-400">
        Badan Pusat Statistik
      </p>
    </main>
  );
}
