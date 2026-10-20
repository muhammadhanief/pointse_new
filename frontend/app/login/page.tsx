import type { Metadata } from "next";
import { Suspense } from "react";

import { jalurAman } from "@/lib/auth/url";
import { daftarKabupaten } from "@/lib/wilayah/kabupaten";

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
  bypass: "Kode bypass atau pilihan kabupaten/kota tidak valid.",
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
  const perluKodeBypass = Boolean(process.env.AUTH_BYPASS_SECRET);
  const bypassAktif =
    process.env.AUTH_BYPASS_ENABLED === "true" &&
    (process.env.NODE_ENV !== "production" || perluKodeBypass);
  const kabupaten = bypassAktif ? daftarKabupaten("33") : [];

  return (
    <div className="w-full max-w-md rounded-xl border border-line bg-surface p-8">
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand text-sm font-bold text-white">
          BPS
        </div>
        <div>
          <p className="font-display text-lg font-semibold leading-tight text-brand">
            Pointse
          </p>
          <p className="text-xs text-muted">Badan Pusat Statistik</p>
        </div>
      </div>

      <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">
        Monitoring Editing Batas Wilkerstat
      </h1>
      <p className="mt-3 text-sm leading-6 text-muted">
        Masuk dengan akun SSO BPS untuk memantau progres perbaikan titik
        bangunan terhadap batas SLS/SubSLS.
      </p>

      {galat ? (
        <div
          role="alert"
          className="mt-6 rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm leading-6 text-danger"
        >
          {galat}
        </div>
      ) : null}

      <a
        href={tautan}
        className="mt-7 flex min-h-11 w-full items-center justify-center rounded-lg bg-brand px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-strong"
      >
        Masuk dengan SSO BPS
      </a>

      {bypassAktif ? (
        <div className="mt-6 border-t border-line pt-5">
          <p className="text-sm font-semibold text-ink">Bypass pengujian</p>
          <p className="mt-1 text-xs leading-5 text-muted">
            Masuk tanpa SSO untuk pengujian. Di production, kode bypass wajib
            diisi. Jangan biarkan aktif setelah pengujian selesai.
          </p>
          <form
            action="/api/auth/bypass"
            method="post"
            className="mt-3 space-y-3"
          >
            <div>
              <label
                htmlFor="bypass-kode"
                className="text-sm font-medium text-ink"
              >
                Kode bypass
              </label>
              <input
                id="bypass-kode"
                name="kode"
                type="password"
                required={perluKodeBypass}
                autoComplete="off"
                className="mt-2 block min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink"
              />
              <p className="mt-1.5 text-xs leading-5 text-muted">
                {perluKodeBypass
                  ? "Wajib diisi sesuai AUTH_BYPASS_SECRET di server."
                  : "Kosongkan bila server lokal tidak memakai kode."}
              </p>
            </div>

            <div>
              <label
                htmlFor="bypass-kdkab"
                className="text-sm font-medium text-ink"
              >
                Kabupaten/kota (untuk petugas)
              </label>
              <select
                id="bypass-kdkab"
                name="kdkab"
                defaultValue="3307"
                className="mt-2 block min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink"
              >
                {kabupaten.map((satu) => (
                  <option key={satu.kode} value={satu.kode}>
                    {satu.kode} · {satu.nama}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="submit"
                name="peran"
                value="petugas_kabkot"
                className="flex min-h-11 items-center justify-center rounded-lg border border-line-strong bg-surface px-4 text-sm font-semibold text-ink transition-colors hover:border-brand hover:text-brand-strong"
              >
                Masuk petugas
              </button>
              <button
                type="submit"
                name="peran"
                value="admin_prov"
                className="flex min-h-11 items-center justify-center rounded-lg border border-line-strong bg-surface px-4 text-sm font-semibold text-ink transition-colors hover:border-brand hover:text-brand-strong"
              >
                Masuk admin provinsi 33
              </button>
            </div>
          </form>
        </div>
      ) : null}

      <p className="mt-5 text-center text-xs leading-5 text-muted">
        Gunakan akun pegawai BPS. Anda akan diarahkan ke halaman login resmi
        <span className="font-medium text-ink"> accounts.bps.go.id</span>.
      </p>
    </div>
  );
}

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-paper px-4 py-12">
      <Suspense
        fallback={
          <div className="h-80 w-full max-w-md animate-pulse rounded-xl border border-line bg-surface" />
        }
      >
        <IsiLogin searchParams={searchParams} />
      </Suspense>
      <p className="mt-8 text-xs text-muted">Badan Pusat Statistik</p>
    </main>
  );
}
