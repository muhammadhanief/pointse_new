"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
  unduhBerkas,
} from "@/lib/api/klien";
import type { Anomali } from "@/lib/api/types";
import { formatAngka, formatTanggal } from "@/lib/format";
import { daftarKabupaten } from "@/lib/wilayah/kabupaten";

const BATAS = 50;

function teks(nilai: string | null | undefined): string {
  return nilai && nilai.trim() !== "" ? nilai : "–";
}

export function AnomaliClient({
  kdprov,
  kdkabAwal,
}: {
  kdprov: string;
  kdkabAwal: string | null;
}) {
  const opsi = daftarKabupaten(kdprov);
  const [kdkab, setKdkab] = useState(kdkabAwal ?? opsi[0]?.kode ?? "");
  const [jenis, setJenis] = useState("");
  const [cari, setCari] = useState("");
  const [kataKunci, setKataKunci] = useState("");
  const [halaman, setHalaman] = useState(0);
  const [data, setData] = useState<Anomali | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [mengunduh, setMengunduh] = useState(false);

  const parameter = useMemo(() => {
    const isi = new URLSearchParams({
      kdprov,
      kdkab,
      limit: String(BATAS),
      offset: String(halaman * BATAS),
    });
    if (jenis) {
      isi.set("jenis", jenis);
    }
    if (kataKunci) {
      isi.set("q", kataKunci);
    }
    return isi;
  }, [kdprov, kdkab, jenis, kataKunci, halaman]);

  const muat = useCallback(
    async (signal?: AbortSignal) => {
      if (!kdkab) {
        setData(null);
        setMemuat(false);
        return;
      }
      setMemuat(true);
      setGalat(null);
      try {
        const hasil = await ambilJson<Anomali>(`/anomali?${parameter}`, {
          signal,
        });
        setData(hasil);
      } catch (kesalahan) {
        if (!adalahBatal(kesalahan)) {
          setGalat(pesanKesalahan(kesalahan));
        }
      } finally {
        if (!signal?.aborted) {
          setMemuat(false);
        }
      }
    },
    [kdkab, parameter],
  );

  useEffect(() => {
    const kendali = new AbortController();
    void muat(kendali.signal);
    return () => kendali.abort();
  }, [muat]);

  const jenisTerpilih = data?.jenis.find((satu) => satu.kode === jenis);
  const totalSemua =
    data?.jenis.reduce((jumlah, satu) => jumlah + satu.jumlah, 0) ?? 0;
  const total = data?.total ?? 0;
  const mulai = total === 0 ? 0 : halaman * BATAS + 1;
  const akhir = Math.min(total, (halaman + 1) * BATAS);

  function gantiKabupaten(nilai: string) {
    setKdkab(nilai);
    setHalaman(0);
  }

  function gantiJenis(nilai: string) {
    setJenis(nilai);
    setHalaman(0);
  }

  async function unduhExcel() {
    if (!jenis) {
      return;
    }
    setMengunduh(true);
    setGalat(null);
    try {
      const isi = new URLSearchParams({ kdprov, kdkab, jenis });
      if (kataKunci) {
        isi.set("q", kataKunci);
      }
      await unduhBerkas(
        `/anomali.xlsx?${isi}`,
        `anomali_${jenis}_${kdkab}.xlsx`,
      );
    } catch (kesalahan) {
      setGalat(pesanKesalahan(kesalahan));
    } finally {
      setMengunduh(false);
    }
  }

  return (
    <div className="space-y-field">
      <Panel
        judul="Anomali titik"
        deskripsi="Titik yang menurut sistem masih bermasalah pada Proses B terakhir. Rekap memakai klaim kabupaten; halaman ini memperlihatkan selisihnya."
      >
        <div className="mt-3 grid gap-field sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-sm font-medium text-ink">
            Kabupaten/kota
            {kdkabAwal ? (
              <span className="mt-label block min-h-9 text-sm font-medium text-muted">
                {opsi.find((satu) => satu.kode === kdkabAwal)?.nama ?? kdkabAwal}
              </span>
            ) : (
              <select
                value={kdkab}
                onChange={(event) => gantiKabupaten(event.target.value)}
                className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
              >
                {opsi.map((satu) => (
                  <option key={satu.kode} value={satu.kode}>
                    {satu.nama}
                  </option>
                ))}
              </select>
            )}
          </label>

          <label className="text-sm font-medium text-ink">
            Jenis anomali
            <select
              value={jenis}
              onChange={(event) => gantiJenis(event.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              <option value="">
                Semua ({formatAngka(totalSemua)})
              </option>
              {(data?.jenis ?? []).map((satu) => (
                <option key={satu.kode} value={satu.kode}>
                  {satu.label} ({formatAngka(satu.jumlah)})
                </option>
              ))}
            </select>
          </label>

          <form
            className="text-sm font-medium text-ink"
            onSubmit={(event) => {
              event.preventDefault();
              setHalaman(0);
              setKataKunci(cari.trim());
            }}
          >
            <span className="block">Cari</span>
            <div className="mt-label flex gap-1.5">
              <input
                type="search"
                value={cari}
                onChange={(event) => setCari(event.target.value)}
                placeholder="assignment_id / bangunan / kode"
                className="block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
              />
              <TombolAksi varian="sekunder" className="min-h-9 px-2.5 text-xs">
                Cari
              </TombolAksi>
            </div>
          </form>

          <div className="flex items-end">
            <TombolAksi
              varian="sekunder"
              className="min-h-9 px-2.5 text-xs"
              onClick={() => void unduhExcel()}
              disabled={!jenis || mengunduh || total === 0}
              title={
                jenis
                  ? "Unduh satu jenis anomali sebagai Excel"
                  : "Pilih satu jenis anomali dulu"
              }
            >
              {mengunduh ? "Menyiapkan..." : "Unduh Excel"}
            </TombolAksi>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 text-xs text-muted">
          {data?.run ? (
            <>
              <span>
                Proses B{" "}
                <strong className="text-ink">#{data.run.run_id}</strong> ·{" "}
                {formatTanggal(data.run.tanggal_data)}
                {data.run.pengunggah ? ` · ${data.run.pengunggah}` : ""}
              </span>
              <span>
                Selesai{" "}
                <strong className="text-ink">
                  {formatAngka(data.run.selesai)}
                </strong>{" "}
                dari {formatAngka(data.run.target)}
              </span>
            </>
          ) : null}
          <span>
            <strong className="text-ink">{formatAngka(total)}</strong> anomali
            {jenisTerpilih ? ` · ${jenisTerpilih.label}` : ""}
          </span>
        </div>

        {data?.run && data.run.anomali_versi === 0 ? (
          <div
            role="status"
            className="mt-3 rounded-lg border border-accent/30 bg-accent-soft/50 px-3 py-2 text-sm text-ink"
          >
            Job B ini diproses sebelum fitur anomali ada. Antrekan ulang berkas B
            terakhir untuk menghitung anomali (tidak perlu unggah ulang).
          </div>
        ) : null}

        {galat ? (
          <div
            role="alert"
            className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
          >
            {galat}
          </div>
        ) : null}

        {memuat && data == null ? (
          <div className="mt-3 space-y-2" aria-label="Memuat anomali">
            {[0, 1, 2, 3].map((baris) => (
              <div
                key={baris}
                className="h-11 animate-pulse rounded-lg bg-paper"
              />
            ))}
          </div>
        ) : null}

        {!memuat && data?.run == null ? (
          <EmptyState judul="Belum ada Proses B yang sukses">
            Anomali dihitung saat job Proses B selesai. Unggah titik hasil
            perbaikan untuk kabupaten/kota ini lebih dulu.
          </EmptyState>
        ) : null}

        {data?.run && data.baris.length === 0 ? (
          <EmptyState judul="Tidak ada titik anomali">
            {jenis
              ? "Jenis ini kosong untuk run terakhir."
              : "Semua titik target cocok dan tidak ada kerusakan baru menurut sistem."}
          </EmptyState>
        ) : null}

        {data && data.baris.length > 0 ? (
          <>
            <div className="mt-3 overflow-x-auto rounded-lg border border-line">
              <table className="w-full min-w-[64rem] border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-line bg-paper text-left text-xs uppercase tracking-wide text-muted">
                    <th className="px-3 py-2 font-semibold">Assignment ID</th>
                    <th className="px-3 py-2 font-semibold">ID baru</th>
                    <th className="px-3 py-2 font-semibold">Bangunan</th>
                    <th className="px-3 py-2 font-semibold">Kode SLS tugas</th>
                    <th className="px-3 py-2 font-semibold">Kode SLS B</th>
                    <th className="px-3 py-2 font-semibold">Wilayah</th>
                    <th className="px-3 py-2 font-semibold">Flag unggah / model</th>
                    <th className="px-3 py-2 font-semibold">Keterangan</th>
                  </tr>
                </thead>
                <tbody>
                  {data.baris.map((baris, indeks) => (
                    <tr
                      key={`${baris.assignment_id}-${baris.assignment_id_baru}-${indeks}`}
                      className="border-b border-line/70 last:border-0"
                    >
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-ink">
                        {teks(baris.assignment_id)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                        {teks(baris.assignment_id_baru)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                        {teks(baris.unique_bang)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                        {teks(baris.level_6_full_code)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                        {teks(baris.level_6_full_code_b)}
                      </td>
                      <td className="px-3 py-2 text-muted">
                        {teks(baris.wilayah)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                        {baris.flag_unggah ?? "–"} / {baris.flag_model ?? "–"}
                      </td>
                      <td className="px-3 py-2 text-muted">
                        {teks(baris.keterangan)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <span>
                {formatAngka(mulai)}–{formatAngka(akhir)} dari{" "}
                {formatAngka(total)}
              </span>
              <div className="flex gap-1.5">
                <TombolAksi
                  varian="sekunder"
                  className="min-h-8 px-2.5 text-xs"
                  onClick={() => setHalaman((lama) => Math.max(0, lama - 1))}
                  disabled={halaman === 0 || memuat}
                >
                  Sebelumnya
                </TombolAksi>
                <TombolAksi
                  varian="sekunder"
                  className="min-h-8 px-2.5 text-xs"
                  onClick={() => setHalaman((lama) => lama + 1)}
                  disabled={akhir >= total || memuat}
                >
                  Berikutnya
                </TombolAksi>
              </div>
            </div>
          </>
        ) : null}
      </Panel>
    </div>
  );
}
