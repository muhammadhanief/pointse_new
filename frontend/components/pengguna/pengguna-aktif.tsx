"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import {
  KesalahanApi,
  adalahBatal,
  ambilJson,
  pesanKesalahan,
} from "@/lib/api/klien";
import type { DaftarPenggunaAktif, PenggunaAktif } from "@/lib/api/types";
import {
  PERAN_ADMIN_PROVINSI,
  PERAN_PETUGAS_KABKOT,
  labelWilayah,
} from "@/lib/auth/peran";
import { formatWaktu } from "@/lib/format";

function labelPeranApi(peran: string): string {
  if (peran === PERAN_ADMIN_PROVINSI) {
    return "Admin Provinsi";
  }
  if (peran === PERAN_PETUGAS_KABKOT) {
    return "Petugas Kabupaten/Kota";
  }
  return peran;
}

function FotoPengguna({ pengguna }: { pengguna: PenggunaAktif }) {
  const [gagal, setGagal] = useState(false);
  const inisial = pengguna.nama.trim().charAt(0).toUpperCase() || "?";

  if (pengguna.foto_url && !gagal) {
    return (
      <img
        src={pengguna.foto_url}
        alt={pengguna.nama}
        loading="lazy"
        onError={() => setGagal(true)}
        className="h-8 w-8 shrink-0 rounded-md border border-line object-cover"
      />
    );
  }

  return (
    <div
      aria-hidden="true"
      className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-brand-soft text-xs font-semibold text-brand-strong"
    >
      {inisial}
    </div>
  );
}

function LencanaStatus({ online }: { online: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold ${
        online
          ? "border-success/30 bg-success-soft text-success"
          : "border-line bg-paper text-muted"
      }`}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${
          online ? "bg-success" : "bg-muted/50"
        }`}
      />
      {online ? "Online" : "Offline"}
    </span>
  );
}

export function PenggunaAktifClient() {
  const [data, setData] = useState<DaftarPenggunaAktif | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [diperbarui, setDiperbarui] = useState<string | null>(null);
  const [cari, setCari] = useState("");
  const [kataKunci, setKataKunci] = useState("");
  const kendaliRef = useRef<AbortController | null>(null);

  const muat = useCallback(
    async (senyap = false) => {
      kendaliRef.current?.abort();
      const kendali = new AbortController();
      kendaliRef.current = kendali;

      if (!senyap) {
        setMemuat(true);
      }
      setGalat(null);

      try {
        const jalur = kataKunci
          ? `/pengguna?q=${encodeURIComponent(kataKunci)}`
          : "/pengguna";
        const hasil = await ambilJson<DaftarPenggunaAktif>(jalur, {
          signal: kendali.signal,
        });
        if (!kendali.signal.aborted) {
          setData(hasil);
          setDiperbarui(new Date().toISOString());
        }
      } catch (kesalahan) {
        if (!adalahBatal(kesalahan)) {
          setGalat(
            kesalahan instanceof KesalahanApi && kesalahan.status === 404
              ? "Endpoint pengguna aktif belum tersedia di backend (404). Deploy backend dan jalankan migrasi 0010."
              : pesanKesalahan(kesalahan),
          );
        }
      } finally {
        if (!kendali.signal.aborted) {
          setMemuat(false);
        }
      }
    },
    [kataKunci],
  );

  useEffect(() => {
    void muat();
    const timer = window.setInterval(() => void muat(true), 30_000);
    return () => {
      window.clearInterval(timer);
      kendaliRef.current?.abort();
    };
  }, [muat]);

  return (
    <Panel
      judul="Daftar pengguna"
      deskripsi="Pengguna yang pernah masuk ke PointSE di provinsi Anda. Status online diperbarui otomatis setiap 30 detik."
    >
      {!galat || data ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
            <span>
              <strong className="text-ink">{data?.online ?? 0}</strong> online
            </span>
            <span>
              <strong className="text-ink">{data?.total ?? 0}</strong> pengguna
            </span>
            {diperbarui ? (
              <span>Diperbarui {formatWaktu(diperbarui)}</span>
            ) : null}
          </div>
          <TombolAksi
            varian="sekunder"
            className="min-h-8 px-2.5 text-xs"
            onClick={() => void muat()}
            disabled={memuat}
          >
            {memuat ? "Memuat..." : "Muat ulang"}
          </TombolAksi>
        </div>
      ) : null}

      <form
        className="mt-3 flex flex-wrap items-end gap-1.5"
        onSubmit={(kejadian) => {
          kejadian.preventDefault();
          setKataKunci(cari.trim());
        }}
      >
        <label className="min-w-0 flex-1 text-sm font-medium text-ink">
          Cari pengguna
          <input
            type="search"
            value={cari}
            onChange={(kejadian) => setCari(kejadian.target.value)}
            placeholder="nama, username, NIP, atau kode wilayah"
            className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
          />
        </label>
        <TombolAksi type="submit" varian="sekunder" className="min-h-9 px-2.5 text-xs">
          Cari
        </TombolAksi>
        {kataKunci ? (
          <TombolAksi
            varian="sekunder"
            className="min-h-9 px-2.5 text-xs"
            onClick={() => {
              setCari("");
              setKataKunci("");
            }}
          >
            Reset
          </TombolAksi>
        ) : null}
      </form>

      {galat ? (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
        >
          {galat}
        </div>
      ) : null}

      {memuat && data == null ? (
        <div className="mt-3 space-y-2" aria-label="Memuat pengguna">
          {[0, 1, 2, 3].map((baris) => (
            <div
              key={baris}
              className="h-11 animate-pulse rounded-lg bg-paper"
            />
          ))}
        </div>
      ) : null}

      {!memuat && data && data.baris.length === 0 ? (
        kataKunci ? (
          <EmptyState judul="Tidak ada pengguna yang cocok">
            Tidak ada nama, username, NIP, atau kode wilayah yang memuat
            &ldquo;{kataKunci}&rdquo;. Coba kata kunci lain.
          </EmptyState>
        ) : (
          <EmptyState judul="Belum ada pengguna tercatat">
            Kehadiran akan muncul setelah pengguna membuka dashboard PointSE.
          </EmptyState>
        )
      ) : null}

      {data && data.baris.length > 0 ? (
        <div className="mt-3 overflow-x-auto rounded-lg border border-line">
          <table className="w-full min-w-[52rem] border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line bg-paper text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-3 py-2 font-semibold">Pengguna</th>
                <th className="px-3 py-2 font-semibold">Wilayah</th>
                <th className="px-3 py-2 font-semibold">Peran</th>
                <th className="px-3 py-2 font-semibold">Login terakhir</th>
                <th className="px-3 py-2 font-semibold">Aktif terakhir</th>
                <th className="px-3 py-2 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.baris.map((pengguna) => (
                <tr
                  key={pengguna.sub}
                  className="border-b border-line/70 last:border-0"
                >
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <FotoPengguna pengguna={pengguna} />
                      <div className="min-w-0">
                        <p className="truncate font-medium text-ink">
                          {pengguna.nama}
                        </p>
                        <p className="truncate text-[11px] text-muted">
                          {pengguna.username}
                          {pengguna.nip ? ` · ${pengguna.nip}` : ""}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-muted">
                    {labelWilayah(pengguna.kdprov, pengguna.kdkab)}
                  </td>
                  <td className="px-3 py-2 text-muted">
                    {labelPeranApi(pengguna.peran)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                    {formatWaktu(pengguna.login_pada)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                    {formatWaktu(pengguna.terakhir_aktif)}
                  </td>
                  <td className="px-3 py-2">
                    <LencanaStatus online={pengguna.online} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Panel>
  );
}
