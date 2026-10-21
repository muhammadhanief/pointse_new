"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EmptyState, Panel, TautanAksi } from "@/components/dashboard/ui";
import { adalahBatal, ambilJson, pesanKesalahan } from "@/lib/api/klien";
import type { ProgresB, Rekap, RekapBaris } from "@/lib/api/types";
import { formatAngka } from "@/lib/format";

type Tingkat = "kecamatan" | "desa";
type Batas = 25 | 50 | 0;

function porsi(belum: number, jumlah: number): string {
  return jumlah > 0 ? `${formatAngka(Math.round((belum / jumlah) * 1000) / 10)}%` : "-";
}

export function TargetB({ kdkab }: { kdkab: string }) {
  const [progres, setProgres] = useState<ProgresB | null>(null);
  const [rekap, setRekap] = useState<Rekap | null>(null);
  const [tingkat, setTingkat] = useState<Tingkat>("desa");
  const [cari, setCari] = useState("");
  const [batas, setBatas] = useState<Batas>(25);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async () => {
    if (!kdkab) {
      setMemuat(false);
      setProgres(null);
      setRekap(null);
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setMemuat(true);
    setGalat(null);
    try {
      const hasil = await ambilJson<ProgresB>(
        `/progres-b?kdkab=${encodeURIComponent(kdkab)}`,
        { signal: controller.signal },
      );
      setProgres(hasil);
      if (!hasil.target) {
        setRekap(null);
        return;
      }
      const rincian = await ambilJson<Rekap>(
        `/runs/${hasil.target.run_a_id}/rekap?tingkat=${tingkat}&dasar=tugas`,
        { signal: controller.signal },
      );
      setRekap(rincian);
    } catch (kesalahan) {
      if (!adalahBatal(kesalahan)) setGalat(pesanKesalahan(kesalahan));
    } finally {
      if (!controller.signal.aborted) setMemuat(false);
    }
  }, [kdkab, tingkat]);

  useEffect(() => {
    const timer = window.setTimeout(() => void muat(), 0);
    return () => {
      window.clearTimeout(timer);
      controllerRef.current?.abort();
    };
  }, [muat]);

  const tersaring = useMemo(() => {
    const kunci = cari.trim().toLowerCase();
    const baris = (rekap?.baris ?? []).filter((satu) => {
      if (!kunci) return true;
      return [satu.kode, satu.nama]
        .filter(Boolean)
        .some((nilai) => String(nilai).toLowerCase().includes(kunci));
    });
    return [...baris].sort((a, b) => b.belum - a.belum || (a.nama ?? "").localeCompare(b.nama ?? ""));
  }, [rekap, cari]);

  const tampil = batas === 0 ? tersaring : tersaring.slice(0, batas);

  if (!kdkab) {
    return (
      <Panel judul="Target Proses B">
        <EmptyState judul="Pilih kabupaten/kota">
          Target per wilayah ditampilkan per kabupaten/kota.
        </EmptyState>
      </Panel>
    );
  }

  if (memuat && progres === null) {
    return (
      <Panel judul="Target Proses B">
        <p className="mt-3 text-sm text-muted" role="status">
          Membaca target wilayah…
        </p>
      </Panel>
    );
  }

  if (galat) {
    return (
      <Panel judul="Target Proses B">
        <div role="alert" className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink">
          {galat}
        </div>
      </Panel>
    );
  }

  if (!progres?.target) {
    return (
      <Panel judul="Target Proses B">
        <EmptyState
          judul="Target belum terbentuk"
          aksi={
            <TautanAksi href="/proses/identifikasi" varian="sekunder">
              Jalankan Proses A
            </TautanAksi>
          }
        >
          Target Proses B diambil dari jumlah titik flag 1 pada Proses A
          terbaru.
        </EmptyState>
      </Panel>
    );
  }

  const target = progres.target;
  const sisa = progres.baris.at(-1)?.sisa_flag_1 ?? target.flag_1;
  const beres = Math.max(target.flag_1 - sisa, 0);

  return (
    <div className="space-y-field">
      <Panel
        judul="Lembar target"
        deskripsi="Jumlah titik flag 1 pada Proses A terbaru. Angka ini menjadi beban kerja awal Proses B."
      >
        <div className="mt-3 grid gap-field lg:grid-cols-[minmax(0,1.2fr)_minmax(17rem,0.8fr)] lg:items-end">
          <div>
            <p className="font-display text-5xl font-semibold tracking-tight text-accent-strong sm:text-6xl">
              {formatAngka(target.flag_1)}
            </p>
            <p className="mt-1 text-sm leading-normal text-muted">
              titik flag 1 dari {formatAngka(target.total)} titik pada Proses A
              terbaru.
            </p>
            <p className="mt-1 text-sm font-medium text-ink">
              {porsi(target.flag_1, target.total)} populasi titik
            </p>
          </div>
          <div className="border-t border-line pt-3 lg:border-t-0 lg:border-l lg:pl-5">
            <div className="flex items-end justify-between gap-field">
              <div>
                <p className="text-xs text-muted">Sudah beres</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-brand-strong">
                  {formatAngka(beres)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-muted">Masih flag 1</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-accent-strong">
                  {formatAngka(sisa)}
                </p>
              </div>
            </div>
          </div>
        </div>
        <div className="mt-3 flex h-4 overflow-hidden rounded-full bg-brand-soft">
          <div
            className="h-full bg-accent"
            style={{
              width: `${target.total > 0 ? Math.min(100, (target.flag_1 / target.total) * 100) : 0}%`,
            }}
          />
        </div>
        <div className="mt-1 flex justify-between text-xs text-muted">
          <span>0</span>
          <span>Target {formatAngka(target.flag_1)}</span>
          <span>{formatAngka(target.total)}</span>
        </div>
      </Panel>

      <Panel
        judul="Tabulasi target"
        deskripsi="Urut dari wilayah dengan flag 1 terbanyak. Klik judul kolom tidak mengubah urutan data sumber."
      >
        <div className="mt-3 flex flex-wrap items-end gap-field">
          <label className="text-sm font-medium text-ink">
            Tingkat
            <select
              value={tingkat}
              onChange={(event) => setTingkat(event.target.value as Tingkat)}
              className="mt-label block min-h-9 rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              <option value="desa">Desa</option>
              <option value="kecamatan">Kecamatan</option>
            </select>
          </label>
          <label className="min-w-[12rem] flex-1 text-sm font-medium text-ink sm:max-w-xs">
            Cari wilayah
            <input
              value={cari}
              onChange={(event) => setCari(event.target.value)}
              placeholder="Nama atau kode"
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            />
          </label>
          <label className="text-sm font-medium text-ink">
            Tampilkan
            <select
              value={batas}
              onChange={(event) => setBatas(Number(event.target.value) as Batas)}
              className="mt-label block min-h-9 rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              <option value={25}>25 baris</option>
              <option value={50}>50 baris</option>
              <option value={0}>Semua</option>
            </select>
          </label>
        </div>

        {memuat ? (
          <p className="mt-3 text-sm text-muted">Memuat tabulasi…</p>
        ) : tampil.length === 0 ? (
          <EmptyState judul="Tidak ada wilayah yang cocok">
            Ubah kata pencarian atau pilih tingkat wilayah lain.
          </EmptyState>
        ) : (
          <>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[680px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-muted">
                    <th className="py-2 pl-3 pr-3 font-semibold">#</th>
                    <th className="py-2 pr-3 font-semibold">
                      {tingkat === "desa" ? "Desa" : "Kecamatan"}
                    </th>
                    <th className="py-2 pr-3 font-semibold">Kode</th>
                    <th className="py-2 pr-3 text-right font-semibold">Jumlah titik</th>
                    <th className="py-2 pr-3 text-right font-semibold">Flag 1</th>
                    <th className="py-2 text-right font-semibold">Porsi</th>
                  </tr>
                </thead>
                <tbody>
                  {tampil.map((baris, indeks) => (
                    <BarisTarget
                      key={`${baris.kode ?? "tanpa"}-${indeks}`}
                      nomor={indeks + 1}
                      baris={baris}
                      maks={tampil[0]?.belum ?? 1}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            {batas !== 0 && tersaring.length > batas ? (
              <p className="mt-1 text-xs text-muted">
                Menampilkan {batas} dari {formatAngka(tersaring.length)} wilayah.
              </p>
            ) : null}
          </>
        )}
      </Panel>
    </div>
  );
}

function BarisTarget({
  nomor,
  baris,
  maks,
}: {
  nomor: number;
  baris: RekapBaris;
  maks: number;
}) {
  const lebar = maks > 0 ? Math.max(2, (baris.belum / maks) * 100) : 0;
  return (
    <tr className="border-b border-line/70 last:border-0">
      <td className="py-2 pl-3 pr-3 tabular-nums text-muted">{nomor}</td>
      <td className="py-2 pr-3 font-medium text-ink">
        {baris.nama || "(tanpa wilayah)"}
      </td>
      <td className="py-2 pr-3 text-muted">{baris.kode || "-"}</td>
      <td className="py-2 pr-3 text-right tabular-nums text-muted">
        {formatAngka(baris.jumlah)}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums font-semibold text-ink">
        {formatAngka(baris.belum)}
      </td>
      <td className="py-2 text-right text-muted">
        <span className="inline-flex items-center justify-end gap-field">
          <span className="h-1.5 w-16 overflow-hidden rounded-full bg-brand-soft" aria-hidden="true">
            <span className="block h-full rounded-full bg-accent" style={{ width: `${lebar}%` }} />
          </span>
          <span className="w-12 tabular-nums">{porsi(baris.belum, baris.jumlah)}</span>
        </span>
      </td>
    </tr>
  );
}
