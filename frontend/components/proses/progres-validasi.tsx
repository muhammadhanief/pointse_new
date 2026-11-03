"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
  unduhBerkas,
} from "@/lib/api/klien";
import type { ValidasiRingkasan, ValidasiRingkasanBaris } from "@/lib/api/types";
import { kodeWilayah } from "@/lib/auth/peran";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";
import { namaKabupaten } from "@/lib/wilayah/kabupaten";

import { BadgeStatus } from "./badge-status";

const INTERVAL_MUAT_ULANG = 15000;

function labelJenis(jenis: string): string {
  switch (jenis) {
    case "tidak_di_peta":
      return "Tidak ada di peta";
    case "tidak_di_master":
      return "Tidak ada di master";
    case "ganda":
      return "Ganda di peta";
    default:
      return jenis;
  }
}

export function ProgresValidasi() {
  const [baris, setBaris] = useState<ValidasiRingkasanBaris[]>([]);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [sibuk, setSibuk] = useState<number | null>(null);
  const [diperbarui, setDiperbarui] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async (senyap = false) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    if (!senyap) {
      setMemuat(true);
      setGalat(null);
    }

    try {
      const hasil = await ambilJson<ValidasiRingkasan>(
        "/validasi-sls/ringkasan",
        { signal: controller.signal },
      );
      if (controller.signal.aborted) {
        return;
      }
      setBaris(hasil.baris);
      setGalat(null);
      setDiperbarui(formatWaktu(new Date().toISOString()));
    } catch (kesalahan) {
      if (!adalahBatal(kesalahan)) {
        setGalat(pesanKesalahan(kesalahan));
      }
    } finally {
      if (!controller.signal.aborted) {
        setMemuat(false);
      }
    }
  }, []);

  useEffect(() => {
    void muat();

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void muat(true);
      }
    }, INTERVAL_MUAT_ULANG);

    function saatTerlihat() {
      if (document.visibilityState === "visible") {
        void muat(true);
      }
    }

    document.addEventListener("visibilitychange", saatTerlihat);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", saatTerlihat);
      controllerRef.current?.abort();
    };
  }, [muat]);

  async function unduh(runId: number, kode: string, nomor: number | null) {
    setSibuk(runId);
    try {
      await unduhBerkas(
        `/runs/${runId}/ekspor/unmatch-v.xlsx`,
        `${kode}_validasi_sls_2026_s1_ke${nomor ?? "?"}.xlsx`,
      );
    } catch {
      // Biarkan tombol kembali normal; unduhan detail ada di riwayat.
    } finally {
      setSibuk(null);
    }
  }

  return (
    <Panel
      judul="Progres validasi per kabupaten/kota"
      deskripsi="Run validasi (tipe V) terakhir tiap kabupaten/kota beserta temuan yang belum diperbaiki. Diperbarui otomatis."
    >
      <div className="mt-3 flex flex-col gap-field sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted" aria-live="polite">
          {baris.length} kabupaten/kota sudah mengunggah
          {diperbarui ? `. Diperbarui ${diperbarui}` : ""}.
        </p>
        <TombolAksi varian="sekunder" onClick={() => void muat()}>
          {memuat ? "Memuat..." : "Muat ulang"}
        </TombolAksi>
      </div>

      {galat ? (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
        >
          <p>{galat}</p>
          <button
            type="button"
            onClick={() => void muat()}
            className="mt-1 min-h-9 rounded-lg border border-danger/30 bg-surface px-tombol text-sm font-semibold text-danger"
          >
            Coba lagi
          </button>
        </div>
      ) : null}

      {memuat && baris.length === 0 ? (
        <p className="mt-3 text-sm leading-normal text-muted" role="status">
          Memuat progres validasi...
        </p>
      ) : null}

      {!memuat && !galat && baris.length === 0 ? (
        <EmptyState judul="Belum ada unggahan validasi">
          Unggah peta SLS/SubSLS 2026 Semester 1 lewat halaman validasi untuk
          mulai memantau progres kabupaten/kota.
        </EmptyState>
      ) : null}

      {baris.length > 0 ? (
        <div className="relative mt-3 max-h-[70vh] overflow-auto overscroll-contain">
          <table className="w-full min-w-[56rem] border-collapse text-[13px]">
            <caption className="sr-only">
              Progres validasi SLS 2026 Semester 1 per kabupaten/kota
            </caption>
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th
                  scope="col"
                  className="sticky top-0 z-10 bg-paper px-3 py-2 font-semibold"
                >
                  Kabupaten/kota
                </th>
                <th
                  scope="col"
                  className="sticky top-0 z-10 bg-paper px-3 py-2 font-semibold"
                >
                  Status
                </th>
                <th
                  scope="col"
                  className="sticky top-0 z-10 bg-paper px-3 py-2 font-semibold"
                >
                  Run terakhir
                </th>
                <th
                  scope="col"
                  className="sticky top-0 z-10 bg-paper px-3 py-2 text-right font-semibold"
                >
                  Temuan
                </th>
                <th
                  scope="col"
                  className="sticky top-0 z-10 bg-paper px-3 py-2 font-semibold"
                >
                  Rincian
                </th>
                <th
                  scope="col"
                  className="sticky top-0 z-10 bg-paper px-3 py-2 text-right font-semibold"
                >
                  Aksi
                </th>
              </tr>
            </thead>
            <tbody>
              {baris.map((satu) => {
                const kode = kodeWilayah(satu.kdprov, satu.kdkab);
                const rincian = Object.entries(satu.per_jenis)
                  .map(([jenis, jumlah]) => `${labelJenis(jenis)} ${jumlah}`)
                  .join(", ");
                return (
                  <tr
                    key={`${satu.kdprov}-${satu.kdkab}`}
                    className="border-b border-line/70 last:border-0 hover:bg-brand-soft/20"
                  >
                    <td className="px-3 py-2">
                      <p className="font-medium text-ink">
                        {namaKabupaten(satu.kdprov, satu.kdkab) ?? "-"}
                      </p>
                      <p className="text-xs text-muted">{kode}</p>
                    </td>
                    <td className="px-3 py-2">
                      <BadgeStatus status={satu.status} rata="start" />
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-muted">
                      {formatTanggal(satu.tanggal_data)}
                      <span className="text-xs">
                        {" "}
                        · {satu.semester ?? "-"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-semibold text-ink">
                      {formatAngka(satu.total)}
                    </td>
                    <td className="max-w-[22rem] px-3 py-2 text-xs leading-5 text-muted">
                      {rincian || "Tidak ada temuan"}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <TombolAksi
                        varian="sekunder"
                        className="min-h-8 px-3 text-xs"
                        onClick={() => void unduh(satu.run_id, kode, null)}
                        disabled={sibuk !== null || satu.total === 0}
                        title={
                          satu.total === 0
                            ? "Tidak ada temuan untuk diunduh"
                            : "Unduh daftar temuan sebagai Excel"
                        }
                      >
                        {sibuk === satu.run_id
                          ? "Menyiapkan..."
                          : "Unduh Excel"}
                      </TombolAksi>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </Panel>
  );
}
