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
import type { DaftarMaster, MasterGeotag } from "@/lib/api/types";
import {
  formatAngka,
  formatTanggal,
  formatWaktu,
} from "@/lib/format";
import { labelKabupaten } from "@/lib/wilayah/kabupaten";

const LIMIT = 20;

export function DaftarMaster({ refreshKey }: { refreshKey: number }) {
  const [baris, setBaris] = useState<MasterGeotag[]>([]);
  const [total, setTotal] = useState(0);
  const [memuat, setMemuat] = useState(true);
  const [memuatLagi, setMemuatLagi] = useState(false);
  const [galat, setGalat] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const ambil = useCallback(
    async (offset: number, ganti: boolean) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      if (ganti) {
        setMemuat(true);
        setMemuatLagi(false);
        setGalat(null);
      } else {
        setMemuatLagi(true);
      }

      try {
        const hasil = await ambilJson<DaftarMaster>(
          `/geotag-master?limit=${LIMIT}&offset=${offset}`,
          { signal: controller.signal },
        );
        if (controller.signal.aborted) {
          return;
        }
        setTotal(hasil.total);
        setBaris((lama) => (ganti ? hasil.baris : [...lama, ...hasil.baris]));
        setGalat(null);
      } catch (galatAmbil) {
        if (!adalahBatal(galatAmbil)) {
          setGalat(pesanKesalahan(galatAmbil));
        }
      } finally {
        if (!controller.signal.aborted) {
          setMemuat(false);
          setMemuatLagi(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    void ambil(0, true);
    return () => controllerRef.current?.abort();
  }, [ambil, refreshKey]);

  async function muatLagi() {
    await ambil(baris.length, false);
  }

  return (
    <Panel
      judul="Versi master"
      deskripsi="Untuk setiap kabupaten/kota, versi terbaru dipakai 1. Identifikasi Titik berikutnya. Versi lama tetap tersimpan untuk run yang sudah berjalan."
    >
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted" role="status">
          {memuat ? "Memuat..." : `${total} versi tersimpan.`}
        </p>
        <TombolAksi
          varian="sekunder"
          onClick={() => void ambil(0, true)}
          disabled={memuat}
        >
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
            onClick={() => void ambil(0, true)}
            className="mt-2 min-h-11 rounded-lg border border-danger/30 bg-surface px-3 text-sm font-semibold text-danger"
          >
            Coba lagi
          </button>
        </div>
      ) : null}

      {memuat && baris.length === 0 ? (
        <p className="mt-4 text-sm leading-6 text-muted" role="status">
          Memuat versi master...
        </p>
      ) : null}

      {!memuat && !galat && baris.length === 0 ? (
        <EmptyState judul="Belum ada master geotag">
          Unggah versi pertama di formulir atas. Setelah tersimpan, versi,
          tanggal data, layer, dan jumlah baris akan tampil di sini.
        </EmptyState>
      ) : null}

      {baris.length > 0 ? (
        <div
          role="region"
          aria-label="Tabel versi master geotag"
          tabIndex={0}
          className="mt-4 overflow-x-auto"
        >
          <table className="w-full min-w-[58rem] border-collapse text-sm">
            <caption className="sr-only">
              Daftar versi master geotag, terbaru lebih dulu.
            </caption>
            <thead>
              <tr className="border-b border-line text-left text-xs font-semibold text-muted">
                <th scope="col" className="py-2.5 pr-3">
                  Versi
                </th>
                <th scope="col" className="px-3 py-2.5">
                  Kabupaten/kota
                </th>
                <th scope="col" className="px-3 py-2.5">
                  Tanggal data
                </th>
                <th scope="col" className="px-3 py-2.5">
                  Berkas
                </th>
                <th scope="col" className="px-3 py-2.5">
                  Layer
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Baris
                </th>
                <th scope="col" className="px-3 py-2.5">
                  Diunggah oleh
                </th>
                <th scope="col" className="px-3 py-2.5">
                  Waktu
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {baris.map((master, indeks) => (
                <tr key={master.id}>
                  <th
                    scope="row"
                    className="py-3 pr-3 text-left font-medium text-ink"
                  >
                    {master.nomor_versi
                      ? `ke-${master.nomor_versi}`
                      : "-"}
                    {indeks === 0 ? (
                      <span className="ml-2 text-xs font-normal text-muted">
                        Terbaru
                      </span>
                    ) : null}
                  </th>
                  <td className="px-3 py-3 tabular-nums text-muted">
                    {labelKabupaten(master.kdprov, master.kdkab)}
                  </td>
                  <td className="px-3 py-3 text-muted">
                    {formatTanggal(master.tanggal_data)}
                  </td>
                  <td className="max-w-[16rem] truncate px-3 py-3 text-muted">
                    <span title={master.nama_file}>{master.nama_file}</span>
                  </td>
                  <td className="px-3 py-3 text-muted">
                    {master.layer ?? "-"}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-muted">
                    {formatAngka(master.jumlah_baris)}
                  </td>
                  <td className="px-3 py-3 text-muted">
                    {master.user ?? "-"}
                  </td>
                  <td className="px-3 py-3 text-muted">
                    {formatWaktu(master.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {baris.length < total ? (
        <div className="mt-4">
          <TombolAksi
            varian="sekunder"
            onClick={() => void muatLagi()}
            disabled={memuatLagi}
          >
            {memuatLagi ? "Memuat..." : "Muat 20 versi berikutnya"}
          </TombolAksi>
        </div>
      ) : null}
    </Panel>
  );
}
