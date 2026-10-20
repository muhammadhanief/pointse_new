"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  EmptyState,
  Panel,
  TautanAksi,
  TombolAksi,
} from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
  unduhBerkas,
} from "@/lib/api/klien";
import type { DaftarRun, Run } from "@/lib/api/types";
import { kodeWilayah, labelWilayah } from "@/lib/auth/peran";
import { labelNomorJob, labelTipe } from "@/lib/istilah";
import { labelKabupaten } from "@/lib/wilayah/kabupaten";
import {
  formatAngka,
  formatTanggal,
} from "@/lib/format";

function TautanUnduh({
  jalur,
  nama,
  children,
  varian = "sekunder",
  onMulai,
  onGagal,
}: {
  jalur: string;
  nama: string;
  children: ReactNode;
  varian?: "utama" | "sekunder";
  onMulai?: () => void;
  onGagal?: (pesan: string) => void;
}) {
  const [sibuk, setSibuk] = useState(false);
  const gaya =
    varian === "utama"
      ? "bg-brand text-white hover:bg-brand-strong"
      : "border border-line-strong bg-surface text-ink hover:border-brand hover:text-brand-strong";

  async function klik() {
    setSibuk(true);
    onMulai?.();
    try {
      await unduhBerkas(jalur, nama);
    } catch (galatUnduh) {
      onGagal?.(pesanKesalahan(galatUnduh));
    } finally {
      setSibuk(false);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void klik()}
      disabled={sibuk}
      className={`inline-flex min-h-11 items-center rounded-lg px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${gaya}`}
    >
      {sibuk ? "Menyiapkan unduhan..." : children}
    </button>
  );
}

export function PemilihEkspor({
  onUnduh,
}: {
  onUnduh?: (nama: string) => void;
}) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [total, setTotal] = useState(0);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [pilihan, setPilihan] = useState("");
  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setMemuat(true);
    setGalat(null);
    try {
      const hasil = await ambilJson<DaftarRun>(
        "/runs?status=sukses&limit=50",
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setRuns(hasil.baris);
        setTotal(hasil.total);
      }
    } catch (galatAmbil) {
      if (!adalahBatal(galatAmbil)) {
        setGalat(pesanKesalahan(galatAmbil));
      }
    } finally {
      if (!controller.signal.aborted) {
        setMemuat(false);
      }
    }
  }, []);

  useEffect(() => {
    void muat();
    return () => controllerRef.current?.abort();
  }, [muat]);

  useEffect(() => {
    if (runs.length === 0) {
      setPilihan("");
      return;
    }
    if (!runs.some((run) => String(run.id) === pilihan)) {
      setPilihan(String(runs[0].id));
    }
  }, [runs, pilihan]);

  const run = runs.find((satu) => String(satu.id) === pilihan) ?? null;
  const kodeUnduh = run ? kodeWilayah(run.kdprov, run.kdkab) : "";
  const nomorUnduh = run?.nomor_urut ?? "?";
  const namaHasilA = run
    ? `${kodeUnduh}_hasil_identifikasi_titik_ke${nomorUnduh}.gpkg`
    : "";
  const namaTitikCsv = run
    ? `${kodeUnduh}_titik_perlu_tindakan_ke${nomorUnduh}.csv`
    : "";
  const namaTitikGpkg = run
    ? `${kodeUnduh}_titik_perlu_tindakan_ke${nomorUnduh}.gpkg`
    : "";

  return (
    <Panel
      judul="Unduh hasil per job"
      deskripsi="Hanya job sukses yang bisa diekspor. Tombol detail titik hanya muncul bila baris titiknya masih disimpan."
    >
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <div className="min-w-[16rem] flex-1">
          <label
            htmlFor="pilih-run-ekspor"
            className="text-sm font-medium text-ink"
          >
            Job sukses
          </label>
          <select
            id="pilih-run-ekspor"
            value={pilihan}
            disabled={memuat || runs.length === 0}
            onChange={(event) => setPilihan(event.target.value)}
            className="mt-2 block min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
          >
            {runs.map((satu) => (
              <option key={satu.id} value={satu.id}>
                {labelTipe(satu.tipe)} ·{" "}
                {labelKabupaten(satu.kdprov, satu.kdkab)} ·{" "}
                {labelNomorJob(satu.nomor_urut)} ·{" "}
                {formatTanggal(satu.tanggal_data)}
              </option>
            ))}
          </select>
        </div>
        <TombolAksi varian="sekunder" onClick={() => void muat()}>
          Muat ulang
        </TombolAksi>
      </div>

      {memuat ? (
        <p className="mt-4 text-sm leading-6 text-muted" role="status">
          Memuat job sukses...
        </p>
      ) : null}

      {!memuat && total > runs.length ? (
        <p className="mt-2 text-xs leading-5 text-muted">
          Menampilkan {runs.length} job sukses terbaru dari {total} job.
        </p>
      ) : null}

      {galat ? (
        <div
          role="alert"
          className="mt-4 rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm leading-6 text-danger"
        >
          <p>{galat}</p>
          <button
            type="button"
            onClick={() => void muat()}
            className="mt-2 min-h-11 rounded-lg border border-danger/30 bg-surface px-3 text-sm font-semibold text-danger"
          >
            Coba lagi
          </button>
        </div>
      ) : null}

      {!memuat && !galat && runs.length === 0 ? (
        <EmptyState
          judul="Belum ada job sukses"
          aksi={
            <TautanAksi href="/proses/identifikasi">
              Buka 1. Identifikasi Titik
            </TautanAksi>
          }
        >
          Ekspor per job tersedia setelah langkah 1 atau 2 sukses.
        </EmptyState>
      ) : null}

      {run ? (
        <div className="mt-5 rounded-lg border border-line bg-paper p-4">
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-xs text-muted">Job</dt>
              <dd className="mt-0.5 font-semibold text-ink">
                {labelTipe(run.tipe)} · {labelNomorJob(run.nomor_urut)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Wilayah</dt>
              <dd className="mt-0.5 font-medium text-ink">
                {labelWilayah(run.kdprov, run.kdkab)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Tanggal data</dt>
              <dd className="mt-0.5 font-medium text-ink">
                {formatTanggal(run.tanggal_data)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Jumlah baris</dt>
              <dd className="mt-0.5 font-medium tabular-nums text-ink">
                {formatAngka(run.jumlah_baris)}
              </dd>
            </div>
          </dl>

          <div className="mt-4 flex flex-wrap gap-3">
            {run.tipe === "A" ? (
              <TautanUnduh
                jalur={`/runs/${run.id}/ekspor/hasil-a.gpkg`}
                nama={namaHasilA}
                varian="utama"
                onMulai={() => onUnduh?.(namaHasilA)}
                onGagal={setGalat}
              >
                Hasil 1. Identifikasi Titik (GPKG)
              </TautanUnduh>
            ) : null}

            {run.detail_tersedia ? (
              <>
                <TautanUnduh
                  jalur={`/runs/${run.id}/ekspor/titik.csv`}
                  nama={namaTitikCsv}
                  onMulai={() => onUnduh?.(namaTitikCsv)}
                  onGagal={setGalat}
                >
                  Titik perlu tindakan (CSV)
                </TautanUnduh>
                <TautanUnduh
                  jalur={`/runs/${run.id}/ekspor/titik.gpkg`}
                  nama={namaTitikGpkg}
                  onMulai={() => onUnduh?.(namaTitikGpkg)}
                  onGagal={setGalat}
                >
                  Titik perlu tindakan (GPKG)
                </TautanUnduh>
              </>
            ) : (
              <p className="text-sm leading-6 text-muted">
                Detail titik job ini sudah dipangkas. Rekap tetap bisa diunduh
                lewat formulir rekap di bawah.
              </p>
            )}
          </div>

          <p className="mt-3 text-xs leading-5 text-muted">
            Jika server membalas 409, berkas mentah atau detail titik job ini
            sudah tidak tersedia. Ekspor rekap tetap memakai snapshot.
          </p>
        </div>
      ) : null}
    </Panel>
  );
}
