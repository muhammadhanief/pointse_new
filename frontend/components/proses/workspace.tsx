"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  EmptyState,
  Panel,
  TombolAksi,
} from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
} from "@/lib/api/klien";
import type { DaftarRun, Run, TipeRun } from "@/lib/api/types";
import { formatWaktu } from "@/lib/format";
import { labelTipe } from "@/lib/istilah";

import { FormProsesA } from "./form-a";
import { FormProsesB } from "./form-b";
import { KartuJob } from "./kartu-job";

export function ProsesWorkspace({ tipe }: { tipe: TipeRun }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [total, setTotal] = useState(0);
  const [aktif, setAktif] = useState(0);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [diperbarui, setDiperbarui] = useState<string | null>(null);
  const [sumberA, setSumberA] = useState<Run[]>([]);
  const [memuatSumberA, setMemuatSumberA] = useState(tipe === "B");
  const [galatSumberA, setGalatSumberA] = useState<string | null>(null);

  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async (senyap = false) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    if (!senyap) {
      setMemuat(true);
      setGalat(null);
      if (tipe === "B") {
        setMemuatSumberA(true);
      }
    }

    const [hasilRun, hasilJalan, hasilMenunggu, hasilSumber] =
      await Promise.allSettled([
        ambilJson<DaftarRun>(`/runs?tipe=${tipe}&limit=20`, {
          signal: controller.signal,
        }),
        ambilJson<DaftarRun>(`/runs?tipe=${tipe}&status=jalan&limit=1`, {
          signal: controller.signal,
        }),
        ambilJson<DaftarRun>(`/runs?tipe=${tipe}&status=menunggu&limit=1`, {
          signal: controller.signal,
        }),
        tipe === "B"
          ? ambilJson<DaftarRun>("/runs?tipe=A&status=sukses&limit=50", {
              signal: controller.signal,
            })
          : Promise.resolve(null),
      ]);

    if (controller.signal.aborted) {
      return;
    }

    const aktifTerhitung =
      hasilJalan.status === "fulfilled" &&
      hasilMenunggu.status === "fulfilled"
        ? hasilJalan.value.total + hasilMenunggu.value.total
        : null;

    if (hasilRun.status === "fulfilled") {
      const aktifDiDaftar = hasilRun.value.baris.filter(
        (run) => run.status === "menunggu" || run.status === "jalan",
      ).length;
      setRuns(hasilRun.value.baris);
      setTotal(hasilRun.value.total);
      setAktif(aktifTerhitung ?? aktifDiDaftar);
      setGalat(null);
      setDiperbarui(formatWaktu(new Date().toISOString()));
    } else if (!adalahBatal(hasilRun.reason)) {
      setGalat(pesanKesalahan(hasilRun.reason));
      if (aktifTerhitung !== null) {
        setAktif(aktifTerhitung);
      }
    }

    if (tipe === "B") {
      if (hasilSumber.status === "fulfilled" && hasilSumber.value) {
        setSumberA(hasilSumber.value.baris);
        setGalatSumberA(null);
      } else if (
        hasilSumber.status === "rejected" &&
        !adalahBatal(hasilSumber.reason)
      ) {
        setGalatSumberA(pesanKesalahan(hasilSumber.reason));
      }
    }

    setMemuat(false);
    setMemuatSumberA(false);
  }, [tipe]);

  useEffect(() => {
    void muat();

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void muat(true);
      }
    }, 5000);

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

  const aktifDiDaftar = runs.filter(
    (run) => run.status === "menunggu" || run.status === "jalan",
  ).length;

  async function ulang() {
    await muat();
  }

  return (
    <div className="space-y-6">
      <div className="max-w-3xl">
        {tipe === "A" ? (
          <FormProsesA onSelesai={() => void muat(true)} />
        ) : (
          <FormProsesB
            onSelesai={() => void muat(true)}
            sumberA={sumberA}
            memuatSumberA={memuatSumberA}
            galatSumberA={galatSumberA}
          />
        )}
      </div>

      <Panel
        judul={`Riwayat ${labelTipe(tipe)}`}
        deskripsi="Status diperbarui otomatis setiap 5 detik. Waktu ditampilkan dalam zona waktu perangkat Anda."
      >
        <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink" aria-live="polite">
              {aktif > 0 ? `${aktif} job aktif` : "Tidak ada job aktif"}
            </p>
            <p className="mt-0.5 text-xs text-muted">
              {total} job total
              {diperbarui ? `. Diperbarui ${diperbarui}` : ""}.
            </p>
          </div>
          <TombolAksi varian="sekunder" onClick={() => void ulang()}>
            Muat ulang
          </TombolAksi>
        </div>

        {galat ? (
          <div
            role="alert"
            className="mt-4 rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm leading-6 text-danger"
          >
            <p>{galat}</p>
            <button
              type="button"
              onClick={() => void ulang()}
              className="mt-2 min-h-11 rounded-lg border border-danger/30 bg-surface px-3 text-sm font-semibold text-danger"
            >
              Coba lagi
            </button>
          </div>
        ) : null}

        {memuat && runs.length === 0 ? (
          <p className="mt-4 text-sm leading-6 text-muted" role="status">
            Memuat status job...
          </p>
        ) : null}

        {!memuat && !galat && runs.length === 0 ? (
          <EmptyState judul={`Belum ada job ${labelTipe(tipe)}`}>
            {tipe === "A"
              ? "Unggah peta untuk membuat job identifikasi pertama. Master geotag disiapkan admin provinsi bila belum tersedia."
              : "Selesaikan langkah 1. Identifikasi Titik, lalu unggah GPKG hasil edit untuk membuat job pengecekan."}
          </EmptyState>
        ) : null}

        {runs.length > 0 ? (
          <div className="mt-4 divide-y divide-line">
            {runs.map((run) => (
              <KartuJob key={run.id} run={run} />
            ))}
          </div>
        ) : null}

        {total > runs.length ? (
          <p className="mt-4 text-xs leading-5 text-muted">
            Menampilkan {runs.length} job terbaru dari {total} job.
          </p>
        ) : null}

        {aktif > aktifDiDaftar ? (
          <p className="mt-2 text-xs leading-5 text-muted">
            {aktif - aktifDiDaftar} job aktif berada di luar daftar 20 terbaru.
          </p>
        ) : null}
      </Panel>
    </div>
  );
}
