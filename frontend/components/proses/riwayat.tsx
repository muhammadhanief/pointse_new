"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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
} from "@/lib/api/klien";
import type { DaftarRun, Run, TipeRun } from "@/lib/api/types";
import { kodeWilayah } from "@/lib/auth/peran";
import { formatAngka, formatWaktu } from "@/lib/format";
import { namaKabupaten } from "@/lib/wilayah/kabupaten";

import { BadgeStatus } from "./badge-status";
import { DetailJob } from "./detail-job";

const TAB: { tipe: TipeRun; label: string }[] = [
  { tipe: "A", label: "1. Peta SLS/SubSLS Final" },
  { tipe: "B", label: "2. Titik Hasil Perbaikan" },
];

const UKURAN_HALAMAN = 20;

/** Nomor halaman yang ditampilkan; ``null`` berarti elipsis. */
function daftarHalaman(total: number, aktif: number): (number | null)[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1);
  }

  const dipilih = new Set([1, total, aktif - 1, aktif, aktif + 1]);
  const nomor = [...dipilih]
    .filter((nilai) => nilai >= 1 && nilai <= total)
    .sort((kiri, kanan) => kiri - kanan);

  const hasil: (number | null)[] = [];
  let sebelumnya = 0;
  for (const satu of nomor) {
    if (sebelumnya > 0 && satu - sebelumnya > 1) {
      hasil.push(null);
    }
    hasil.push(satu);
    sebelumnya = satu;
  }
  return hasil;
}

type KolomSort =
  | "job"
  | "wilayah"
  | "pengunggah"
  | "diunggah"
  | "status"
  | "baris";
type ArahSort = "asc" | "desc";
type Sort = { kolom: KolomSort; arah: ArahSort };

const URUT_STATUS: Record<Run["status"], number> = {
  menunggu: 0,
  jalan: 1,
  sukses: 2,
  gagal: 3,
};

function nilaiSort(run: Run, kolom: KolomSort): string | number {
  switch (kolom) {
    case "job":
      return run.nomor_urut ?? 0;
    case "wilayah":
      return `${namaKabupaten(run.kdprov, run.kdkab) ?? ""} ${kodeWilayah(
        run.kdprov,
        run.kdkab,
      )}`.trim();
    case "pengunggah":
      return run.user ?? "";
    case "diunggah":
      return run.created_at;
    case "status":
      return URUT_STATUS[run.status] ?? 99;
    case "baris":
      return run.jumlah_baris ?? -1;
    default:
      return "";
  }
}

function SelSort({
  label,
  kolom,
  sort,
  onSort,
  rata = "left",
  kiri = false,
}: {
  label: string;
  kolom: KolomSort;
  sort: Sort | null;
  onSort: (kolom: KolomSort) => void;
  rata?: "left" | "right";
  kiri?: boolean;
}) {
  const aktif = sort?.kolom === kolom;
  const arah = aktif ? sort.arah : null;
  const ariaSort: "none" | "ascending" | "descending" =
    arah === "asc" ? "ascending" : arah === "desc" ? "descending" : "none";

  return (
    <th
      scope="col"
      aria-sort={ariaSort}
      className={`sticky top-0 border-b border-line bg-paper px-3 py-2 font-semibold ${
        kiri ? "left-0 z-30" : "z-20"
      } ${rata === "right" ? "text-right" : "text-left"}`}
    >
      <button
        type="button"
        onClick={() => onSort(kolom)}
        className={`inline-flex items-center gap-1.5 rounded hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
          rata === "right" ? "w-full justify-end" : ""
        }`}
      >
        <span>{label}</span>
        <span
          aria-hidden="true"
          className={aktif ? "text-brand-strong" : "text-muted/60"}
        >
          {arah === "asc" ? "↑" : arah === "desc" ? "↓" : "↕"}
        </span>
      </button>
    </th>
  );
}

export function RiwayatWorkspace() {
  const [tipe, setTipe] = useState<TipeRun>("A");
  const [runs, setRuns] = useState<Run[]>([]);
  const [total, setTotal] = useState(0);
  const [aktif, setAktif] = useState(0);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [diperbarui, setDiperbarui] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort | null>(null);
  const [dipilih, setDipilih] = useState<Run | null>(null);
  const [halaman, setHalaman] = useState(0);
  const [cari, setCari] = useState("");
  const [cariAktif, setCariAktif] = useState("");

  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(
    async (senyap = false) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      if (!senyap) {
        setMemuat(true);
        setGalat(null);
      }

      const parameter = new URLSearchParams({
        tipe,
        limit: String(UKURAN_HALAMAN),
        offset: String(halaman * UKURAN_HALAMAN),
      });
      if (cariAktif) {
        parameter.set("q", cariAktif);
      }

      const [hasilRun, hasilJalan, hasilMenunggu] =
        await Promise.allSettled([
          ambilJson<DaftarRun>(`/runs?${parameter.toString()}`, {
            signal: controller.signal,
          }),
          ambilJson<DaftarRun>(`/runs?tipe=${tipe}&status=jalan&limit=1`, {
            signal: controller.signal,
          }),
          ambilJson<DaftarRun>(`/runs?tipe=${tipe}&status=menunggu&limit=1`, {
            signal: controller.signal,
          }),
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
        const totalBaru = hasilRun.value.total;
        const halamanTerakhir = Math.max(
          0,
          Math.ceil(totalBaru / UKURAN_HALAMAN) - 1,
        );
        if (halaman > halamanTerakhir) {
          setHalaman(halamanTerakhir);
          setRuns([]);
          setTotal(totalBaru);
          setMemuat(false);
          return;
        }

        const aktifDiDaftar = hasilRun.value.baris.filter(
          (run) => run.status === "menunggu" || run.status === "jalan",
        ).length;
        setRuns(hasilRun.value.baris);
        setTotal(totalBaru);
        setAktif(aktifTerhitung ?? aktifDiDaftar);
        setGalat(null);
        setDiperbarui(formatWaktu(new Date().toISOString()));
      } else if (!adalahBatal(hasilRun.reason)) {
        setGalat(pesanKesalahan(hasilRun.reason));
        if (aktifTerhitung !== null) {
          setAktif(aktifTerhitung);
        }
      }

      setMemuat(false);
    },
    [tipe, halaman, cariAktif],
  );

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

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCariAktif(cari.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [cari]);

  useEffect(() => {
    if (!dipilih) {
      return;
    }
    const terbaru = runs.find((run) => run.id === dipilih.id);
    if (terbaru && terbaru !== dipilih) {
      setDipilih(terbaru);
    }
  }, [runs, dipilih]);

  function gantiTipe(nilai: TipeRun) {
    if (nilai === tipe) {
      return;
    }
    setTipe(nilai);
    setRuns([]);
    setTotal(0);
    setAktif(0);
    setGalat(null);
    setMemuat(true);
    setDiperbarui(null);
    setSort(null);
    setDipilih(null);
    setHalaman(0);
    setCari("");
    setCariAktif("");
  }

  function gantiCari(nilai: string) {
    setCari(nilai);
    setHalaman(0);
  }

  function gantiSort(kolom: KolomSort) {
    setSort((lama) => {
      if (lama?.kolom === kolom) {
        return {
          kolom,
          arah: lama.arah === "asc" ? "desc" : "asc",
        };
      }
      return {
        kolom,
        arah:
          kolom === "job" || kolom === "diunggah" || kolom === "baris"
            ? "desc"
            : "asc",
      };
    });
  }

  const urut = useMemo(() => {
    if (!sort) {
      return runs;
    }

    return [...runs].sort((kiri, kanan) => {
      const a = nilaiSort(kiri, sort.kolom);
      const b = nilaiSort(kanan, sort.kolom);
      let hasil =
        typeof a === "number" && typeof b === "number"
          ? a - b
          : String(a).localeCompare(String(b), "id-ID");

      if (hasil === 0) {
        hasil = (kiri.nomor_urut ?? 0) - (kanan.nomor_urut ?? 0);
      }
      return sort.arah === "asc" ? hasil : -hasil;
    });
  }, [runs, sort]);

  const aktifDiDaftar = runs.filter(
    (run) => run.status === "menunggu" || run.status === "jalan",
  ).length;

  const labelAktif =
    tipe === "A" ? "Peta SLS/SubSLS Final" : "Titik Hasil Perbaikan";
  const jalurUnggah =
    tipe === "A" ? "/proses/identifikasi" : "/proses/pengecekan";
  const totalHalaman = Math.max(1, Math.ceil(total / UKURAN_HALAMAN));
  const nomorHalaman = daftarHalaman(totalHalaman, halaman + 1);
  const mulai = total === 0 ? 0 : halaman * UKURAN_HALAMAN + 1;
  const akhir = Math.min((halaman + 1) * UKURAN_HALAMAN, total);

  return (
    <div className="space-y-field">
      <div className="flex flex-col gap-field rounded-xl border border-line bg-surface p-kartu sm:flex-row sm:items-center sm:justify-between">
        <div
          role="tablist"
          aria-label="Jenis riwayat"
          className="flex flex-wrap gap-field"
        >
          {TAB.map((satu) => (
            <button
              key={satu.tipe}
              type="button"
              role="tab"
              id={`tab-riwayat-${satu.tipe}`}
              aria-selected={tipe === satu.tipe}
              aria-controls="panel-riwayat"
              onClick={() => gantiTipe(satu.tipe)}
              className={`min-h-9 rounded-lg px-tombol text-sm font-semibold transition-colors ${
                tipe === satu.tipe
                  ? "bg-brand text-white"
                  : "border border-line bg-surface text-muted hover:border-brand hover:text-brand-strong"
              }`}
            >
              {satu.label}
            </button>
          ))}
        </div>

        <TombolAksi varian="sekunder" onClick={() => void muat()}>
          Muat ulang
        </TombolAksi>
      </div>

      <Panel
        judul={`Riwayat ${labelAktif}`}
        deskripsi="Status diperbarui otomatis setiap 5 detik. Waktu ditampilkan dalam zona waktu perangkat Anda."
      >
        <div
          id="panel-riwayat"
          role="tabpanel"
          aria-labelledby={`tab-riwayat-${tipe}`}
        >
          <div className="mt-3 flex flex-col gap-field sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-ink" aria-live="polite">
                {aktif > 0 ? `${aktif} job aktif` : "Tidak ada job aktif"}
              </p>
              <p className="mt-1 text-xs text-muted">
                {total} job{total === 1 ? "" : " total"}
                {cariAktif ? ` cocok dengan "${cariAktif}"` : ""}
                {diperbarui ? `. Diperbarui ${diperbarui}` : ""}.
              </p>
            </div>
            <label className="w-full text-sm font-medium text-ink sm:w-80">
              Cari riwayat
              <input
                type="search"
                value={cari}
                maxLength={100}
                onChange={(event) => gantiCari(event.target.value)}
                placeholder="Job, wilayah, pengunggah, status..."
                className="mt-1 min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
              />
            </label>
          </div>

          {galat ? (
            <div
              role="alert"
              className="mt-3 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger"
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

          {memuat && runs.length === 0 ? (
            <p className="mt-3 text-sm leading-normal text-muted" role="status">
              Memuat riwayat unggahan...
            </p>
          ) : null}

          {!memuat && !galat && runs.length === 0 ? (
            cariAktif ? (
              <EmptyState judul={`Tidak ada hasil untuk "${cariAktif}"`}>
                Coba kata kunci lain, atau hapus pencarian untuk melihat semua job.
              </EmptyState>
            ) : (
              <EmptyState
                judul={`Belum ada unggahan ${labelAktif}`}
                aksi={
                  <TautanAksi href={jalurUnggah} ringkas>
                    Buka halaman unggah
                  </TautanAksi>
                }
              >
                {tipe === "A"
                  ? "Unggah peta SLS/SubSLS final untuk membuat job identifikasi pertama."
                  : "Selesaikan langkah 1, edit GPKG di QGIS, lalu unggah hasil perbaikan titik."}
              </EmptyState>
            )
          ) : null}

          {urut.length > 0 ? (
            <div className="relative mt-3 max-h-[70vh] overflow-auto overscroll-contain">
              <table className="w-full min-w-[56rem] border-collapse text-[13px]">
                <caption className="sr-only">
                  Riwayat {labelAktif}. Klik judul kolom untuk mengurutkan
                  halaman ini.
                </caption>
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted">
                    <SelSort
                      label="Job"
                      kolom="job"
                      sort={sort}
                      onSort={gantiSort}
                      kiri
                    />
                    <SelSort
                      label="Wilayah"
                      kolom="wilayah"
                      sort={sort}
                      onSort={gantiSort}
                    />
                    <SelSort
                      label="Pengunggah"
                      kolom="pengunggah"
                      sort={sort}
                      onSort={gantiSort}
                    />
                    <SelSort
                      label="Diunggah"
                      kolom="diunggah"
                      sort={sort}
                      onSort={gantiSort}
                    />
                    <SelSort
                      label="Status"
                      kolom="status"
                      sort={sort}
                      onSort={gantiSort}
                    />
                    <SelSort
                      label="Baris"
                      kolom="baris"
                      sort={sort}
                      onSort={gantiSort}
                      rata="right"
                    />
                    <th className="sticky top-0 z-20 border-b border-line bg-paper px-3 py-2 text-right font-semibold">
                      Aksi
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {urut.map((run) => {
                    const terhenti =
                      run.status === "gagal" && /terhenti/i.test(run.pesan ?? "");
                    const nama = namaKabupaten(run.kdprov, run.kdkab);

                    return (
                      <tr
                        key={run.id}
                        className="group border-b border-line/70 last:border-0 hover:bg-brand-soft/20"
                      >
                        <th
                          scope="row"
                          className="sticky left-0 z-10 bg-surface px-3 py-2 text-left font-medium text-ink group-hover:bg-brand-soft/20"
                        >
                          {run.nomor_urut ?? "-"}
                        </th>
                        <td className="px-3 py-2">
                          <p className="font-medium text-ink">{nama ?? "-"}</p>
                          <p className="text-xs text-muted">
                            {kodeWilayah(run.kdprov, run.kdkab)}
                          </p>
                        </td>
                        <td className="max-w-[14rem] px-3 py-2 text-muted">
                          <span className="block truncate" title={run.user ?? ""}>
                            {run.user ?? "-"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-muted">
                          {formatWaktu(run.created_at)}
                        </td>
                        <td className="px-3 py-2">
                          <BadgeStatus
                            status={run.status}
                            terhenti={terhenti}
                            rata="start"
                          />
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-muted">
                          {formatAngka(run.jumlah_baris)}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <TombolAksi
                            varian="sekunder"
                            className="min-h-8 px-3 text-xs"
                            onClick={() => setDipilih(run)}
                          >
                            Detail
                          </TombolAksi>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}

          {total > 0 ? (
            <div className="mt-3 flex flex-col gap-2 border-t border-line pt-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs leading-5 text-muted">
                Menampilkan {mulai}–{akhir} dari {total} job
                {cariAktif ? ` untuk "${cariAktif}"` : ""}.
              </p>
              {totalHalaman > 1 ? (
                <nav
                  aria-label="Halaman riwayat"
                  className="flex flex-wrap items-center gap-1"
                >
                  <TombolAksi
                    varian="sekunder"
                    className="min-h-8 px-3 text-xs"
                    disabled={halaman === 0}
                    onClick={() =>
                      setHalaman((lama) => Math.max(0, lama - 1))
                    }
                  >
                    Sebelumnya
                  </TombolAksi>
                  {nomorHalaman.map((nomor, index) =>
                    nomor === null ? (
                      <span
                        key={`elipsis-${index}`}
                        aria-hidden="true"
                        className="px-1 text-xs text-muted"
                      >
                        …
                      </span>
                    ) : (
                      <TombolAksi
                        key={nomor}
                        varian={nomor === halaman + 1 ? "utama" : "sekunder"}
                        className="min-h-8 min-w-8 px-2 text-xs"
                        aria-current={
                          nomor === halaman + 1 ? "page" : undefined
                        }
                        onClick={() => setHalaman(nomor - 1)}
                      >
                        {nomor}
                      </TombolAksi>
                    ),
                  )}
                  <TombolAksi
                    varian="sekunder"
                    className="min-h-8 px-3 text-xs"
                    disabled={halaman >= totalHalaman - 1}
                    onClick={() =>
                      setHalaman((lama) =>
                        Math.min(totalHalaman - 1, lama + 1),
                      )
                    }
                  >
                    Berikutnya
                  </TombolAksi>
                </nav>
              ) : null}
            </div>
          ) : null}

          {aktif > aktifDiDaftar ? (
            <p className="mt-bantuan text-xs leading-5 text-muted">
              {aktif - aktifDiDaftar} job aktif berada di halaman lain.
            </p>
          ) : null}
        </div>
      </Panel>

      <DetailJob run={dipilih} onTutup={() => setDipilih(null)} />
    </div>
  );
}
