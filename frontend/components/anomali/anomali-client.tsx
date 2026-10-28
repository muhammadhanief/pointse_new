"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { MultiPilih } from "@/components/dashboard/multi-pilih";
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
  const [kdkabs, setKdkabs] = useState<string[]>(() =>
    kdkabAwal ? [kdkabAwal] : opsi[0] ? [opsi[0].kode] : [],
  );
  const [jenises, setJenises] = useState<string[]>([]);
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
      limit: String(BATAS),
      offset: String(halaman * BATAS),
    });
    for (const kode of kdkabs) {
      isi.append("kdkab", kode);
    }
    for (const kode of jenises) {
      isi.append("jenis", kode);
    }
    if (kataKunci) {
      isi.set("q", kataKunci);
    }
    return isi;
  }, [kdprov, kdkabs, jenises, kataKunci, halaman]);

  const muat = useCallback(
    async (signal?: AbortSignal) => {
      if (kdkabs.length === 0) {
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
    [kdkabs.length, parameter],
  );

  useEffect(() => {
    const kendali = new AbortController();
    void muat(kendali.signal);
    return () => kendali.abort();
  }, [muat]);

  // ``runs`` baru ada di backend versi ini; sisa pakai ``run`` supaya halaman
  // tetap hidup saat frontend lebih dulu diperbarui.
  const runs = data?.runs ?? (data?.run ? [data.run] : []);
  const jenisTerpilih =
    jenises.length === 1
      ? data?.jenis.find((satu) => satu.kode === jenises[0])
      : undefined;
  const totalSemua =
    data?.jenis.reduce((jumlah, satu) => jumlah + satu.jumlah, 0) ?? 0;
  const total = data?.total ?? 0;
  const mulai = total === 0 ? 0 : halaman * BATAS + 1;
  const akhir = Math.min(total, (halaman + 1) * BATAS);
  const target = runs.reduce((jumlah, satu) => jumlah + satu.target, 0);
  const selesai = runs.reduce((jumlah, satu) => jumlah + satu.selesai, 0);
  const perluHitungUlang = runs.some((satu) => satu.anomali_versi === 0);
  const banyakKabupaten = kdkabs.length > 1;

  const labelKabupaten = useMemo(() => {
    const peta = new Map(opsi.map((satu) => [satu.kode, satu.nama]));
    return (kode: string | null) =>
      kode ? (peta.get(kode) ?? kode) : "–";
  }, [opsi]);

  const labelJenis = useMemo(() => {
    const peta = new Map((data?.jenis ?? []).map((satu) => [satu.kode, satu.label]));
    return (kode: string) => peta.get(kode) ?? kode;
  }, [data]);

  async function unduhExcel() {
    if (runs.length === 0) {
      return;
    }
    setMengunduh(true);
    setGalat(null);
    try {
      const isi = new URLSearchParams({ kdprov });
      for (const kode of kdkabs) {
        isi.append("kdkab", kode);
      }
      for (const kode of jenises) {
        isi.append("jenis", kode);
      }
      if (kataKunci) {
        isi.set("q", kataKunci);
      }
      const label = jenises.length === 1 ? jenises[0] : "semua";
      await unduhBerkas(
        `/anomali.xlsx?${isi}`,
        `anomali_${label}_${kdkabs.join("-")}.xlsx`,
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
          {kdkabAwal ? (
            <div>
              <span className="block text-sm font-medium text-ink">
                Kabupaten/kota
              </span>
              <span className="mt-label block min-h-9 text-sm font-medium text-muted">
                {opsi.find((satu) => satu.kode === kdkabAwal)?.nama ??
                  kdkabAwal}
              </span>
            </div>
          ) : (
            <MultiPilih
              label="Kabupaten/kota"
              labelSemua="Semua kabupaten/kota"
              tempatCari="Cari kode atau nama kabupaten..."
              opsi={opsi.map((satu) => ({
                nilai: satu.kode,
                label: `${satu.kode} · ${satu.nama}`,
              }))}
              terpilih={kdkabs}
              onTerapkan={(nilai) => {
                setKdkabs(nilai);
                setHalaman(0);
              }}
            />
          )}

          <MultiPilih
            label="Jenis anomali"
            labelSemua={`Semua (${formatAngka(totalSemua)})`}
            tempatCari="Cari jenis anomali..."
            opsi={(data?.jenis ?? []).map((satu) => ({
              nilai: satu.kode,
              label: `${satu.label} (${formatAngka(satu.jumlah)})`,
            }))}
            terpilih={jenises}
            onTerapkan={(nilai) => {
              setJenises(nilai);
              setHalaman(0);
            }}
          />

          <form
            className="text-sm font-medium text-ink"
            onSubmit={(kejadian) => {
              kejadian.preventDefault();
              setHalaman(0);
              setKataKunci(cari.trim());
            }}
          >
            <span className="block">Cari</span>
            <div className="mt-label flex gap-1.5">
              <input
                type="search"
                value={cari}
                onChange={(kejadian) => setCari(kejadian.target.value)}
                placeholder="assignment_id / bangunan / kode"
                className="block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
              />
              <TombolAksi
                type="submit"
                varian="sekunder"
                className="min-h-9 px-2.5 text-xs"
              >
                Cari
              </TombolAksi>
            </div>
          </form>

          <div className="flex items-end">
            <TombolAksi
              varian="sekunder"
              className="min-h-9 px-2.5 text-xs"
              onClick={() => void unduhExcel()}
              disabled={runs.length === 0 || mengunduh || total === 0}
              title={
                runs.length === 0
                  ? "Belum ada Proses B yang sukses"
                  : "Unduh anomali sesuai filter sebagai Excel"
              }
            >
              {mengunduh ? "Menyiapkan..." : "Unduh Excel"}
            </TombolAksi>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 text-xs text-muted">
          {runs.length === 1 ? (
            <>
              <span>
                Proses B{" "}
                <strong className="text-ink">#{runs[0].run_id}</strong> ·{" "}
                {formatTanggal(runs[0].tanggal_data)}
                {runs[0].pengunggah ? ` · ${runs[0].pengunggah}` : ""}
              </span>
              <span>
                Selesai{" "}
                <strong className="text-ink">
                  {formatAngka(runs[0].selesai)}
                </strong>{" "}
                dari {formatAngka(runs[0].target)}
              </span>
            </>
          ) : null}
          {runs.length > 1 ? (
            <>
              <span>
                <strong className="text-ink">{formatAngka(runs.length)}</strong>{" "}
                kabupaten/kota dengan Proses B sukses
              </span>
              <span>
                Selesai{" "}
                <strong className="text-ink">{formatAngka(selesai)}</strong> dari{" "}
                {formatAngka(target)}
              </span>
            </>
          ) : null}
          <span>
            <strong className="text-ink">{formatAngka(total)}</strong> anomali
            {jenisTerpilih ? ` · ${jenisTerpilih.label}` : ""}
          </span>
        </div>

        {perluHitungUlang ? (
          <div
            role="status"
            className="mt-3 rounded-lg border border-accent/30 bg-accent-soft/50 px-3 py-2 text-sm text-ink"
          >
            Ada job B yang diproses sebelum fitur anomali ada. Antrekan ulang
            berkas B terakhir kabupaten tersebut untuk menghitung anomali
            (tidak perlu unggah ulang).
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

        {!memuat && data != null && runs.length === 0 ? (
          <EmptyState judul="Belum ada Proses B yang sukses">
            Anomali dihitung saat job Proses B selesai. Unggah titik hasil
            perbaikan untuk kabupaten/kota ini lebih dulu.
          </EmptyState>
        ) : null}

        {runs.length > 0 && data && data.baris.length === 0 ? (
          <EmptyState judul="Tidak ada titik anomali">
            {jenises.length > 0
              ? "Jenis yang dipilih kosong untuk run terakhir."
              : "Semua titik target cocok dan tidak ada kerusakan baru menurut sistem."}
          </EmptyState>
        ) : null}

        {data && data.baris.length > 0 ? (
          <>
            <div className="mt-3 overflow-x-auto rounded-lg border border-line">
              <table className="w-full min-w-[72rem] border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-line bg-paper text-left text-xs uppercase tracking-wide text-muted">
                    {banyakKabupaten ? (
                      <th className="px-3 py-2 font-semibold">Kabupaten/kota</th>
                    ) : null}
                    <th className="px-3 py-2 font-semibold">Jenis</th>
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
                      key={`${baris.kdkab}-${baris.assignment_id}-${baris.assignment_id_baru}-${indeks}`}
                      className="border-b border-line/70 last:border-0"
                    >
                      {banyakKabupaten ? (
                        <td className="whitespace-nowrap px-3 py-2 text-muted">
                          {labelKabupaten(baris.kdkab)}
                        </td>
                      ) : null}
                      <td className="whitespace-nowrap px-3 py-2 text-muted">
                        {labelJenis(baris.jenis)}
                      </td>
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
