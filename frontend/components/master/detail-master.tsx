"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState, TombolAksi } from "@/components/dashboard/ui";
import { BadgeStatus } from "@/components/dashboard/ui";
import { adalahBatal, ambilJson, pesanKesalahan } from "@/lib/api/klien";
import type { DaftarMaster, MasterGeotag } from "@/lib/api/types";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";

export function DetailMaster({
  kdkab,
  refreshKey,
  onUnggah,
}: {
  kdkab: string;
  refreshKey: number;
  onUnggah: () => void;
}) {
  const [baris, setBaris] = useState<MasterGeotag[]>([]);
  const [total, setTotal] = useState(0);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setMemuat(true);
    setGalat(null);
    try {
      const hasil = await ambilJson<DaftarMaster>(
        `/geotag-master?kdkab=${kdkab}&limit=100`,
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setBaris(hasil.baris);
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
  }, [kdkab]);

  useEffect(() => {
    void muat();
    return () => controllerRef.current?.abort();
  }, [muat, refreshKey]);

  return (
    <div className="space-y-field">
      <div className="flex flex-wrap items-center justify-between gap-field">
        <div className="flex items-center gap-2">
          <BadgeStatus status={baris.length > 0 ? "ada" : "belum"} />
          <p className="text-xs text-muted" role="status">
            {memuat
              ? "Memuat versi..."
              : `${total} versi tersimpan untuk kabupaten/kota ini.`}
          </p>
        </div>
        <TombolAksi onClick={onUnggah}>Unggah versi baru</TombolAksi>
      </div>

      {galat ? (
        <div
          role="alert"
          className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger"
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
        <p className="text-sm text-muted" role="status">
          Memuat versi master...
        </p>
      ) : null}

      {!memuat && !galat && baris.length === 0 ? (
        <EmptyState
          judul="Belum ada master geotag"
          aksi={<TombolAksi onClick={onUnggah}>Unggah master pertama</TombolAksi>}
        >
          Kabupaten/kota ini belum punya master. Unggah berkas asli dari GS
          untuk memulai.
        </EmptyState>
      ) : null}

      {baris.length > 0 ? (
        <div className="max-h-[55vh] overflow-auto overscroll-contain rounded-lg border border-line">
          <table className="w-full min-w-[54rem] border-collapse text-[13px]">
            <caption className="sr-only">
              Versi master geotag kabupaten/kota, terbaru lebih dulu.
            </caption>
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                {[
                  "Versi",
                  "Tanggal data",
                  "Berkas",
                  "Layer",
                  "Baris",
                  "Diunggah oleh",
                  "Waktu",
                ].map((label) => (
                  <th
                    key={label}
                    scope="col"
                    className={`sticky top-0 z-10 border-b border-line bg-paper px-3 py-2 font-semibold ${
                      label === "Baris" ? "text-right" : "text-left"
                    }`}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {baris.map((master, indeks) => (
                <tr key={master.id} className="hover:bg-brand-soft/20">
                  <th
                    scope="row"
                    className="px-3 py-2 text-left font-medium text-ink"
                  >
                    {master.nomor_versi ? `ke-${master.nomor_versi}` : "-"}
                    {indeks === 0 ? (
                      <span className="ml-1 text-xs font-normal text-muted">
                        Terbaru
                      </span>
                    ) : null}
                  </th>
                  <td className="px-3 py-2 text-muted">
                    {formatTanggal(master.tanggal_data)}
                  </td>
                  <td className="max-w-[14rem] truncate px-3 py-2 text-muted">
                    <span title={master.nama_file}>{master.nama_file}</span>
                  </td>
                  <td className="px-3 py-2 text-muted">{master.layer ?? "-"}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted">
                    {formatAngka(master.jumlah_baris)}
                  </td>
                  <td className="px-3 py-2 text-muted">{master.user ?? "-"}</td>
                  <td className="px-3 py-2 text-muted">
                    {formatWaktu(master.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {total > baris.length ? (
        <p className="text-xs text-muted">
          Menampilkan {baris.length} versi terbaru dari {total} versi.
        </p>
      ) : null}
    </div>
  );
}
