"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  BarStack,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import type { ArahUrut } from "@/components/dashboard/tabel-urut";
import { formatAngka } from "@/lib/format";

export type BatangBatasKabKota = {
  kode: string;
  nama: string;
  label: string;
  clean: number;
  belum_clean: number;
  menunggu_tetangga: number;
  belum_unggah: number;
  total: number;
};

const JUDUL_GRAFIK =
  "Pemeriksaan Batas Kabupaten/Kota se-Provinsi Jawa Tengah";

// Warna sama dengan badge Clean/Belum Clean di tabel supaya maknanya konsisten.
// Dua kategori sisanya sengaja redup karena bukan hasil pemeriksaan, hanya
// prasyarat yang belum terpenuhi.
const WARNA_KATEGORI = {
  clean: "var(--success)",
  belum_clean: "var(--danger)",
  menunggu_tetangga: "var(--warning)",
  belum_unggah: "var(--line-strong)",
} as const;

type KunciKategori = keyof typeof WARNA_KATEGORI;

const URUTAN_KATEGORI: { kunci: KunciKategori; label: string }[] = [
  { kunci: "clean", label: "Clean" },
  { kunci: "belum_clean", label: "Belum Clean" },
  { kunci: "menunggu_tetangga", label: "Menunggu Tetangga" },
  { kunci: "belum_unggah", label: "Belum Unggah" },
];

type KunciUrutGrafik = "kode" | "clean";

function persenDari(nilai: number, total: number): number {
  return total > 0 ? (nilai / total) * 100 : 0;
}

function IkonLayarPenuh() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M9 3H3v6" />
      <path d="M15 21h6v-6" />
    </svg>
  );
}

function IkonKeluarLayarPenuh() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 9V3h-6" />
      <path d="M3 15v6h6" />
    </svg>
  );
}

function TitikWarna({ warna }: { warna: string }) {
  return (
    <span
      aria-hidden="true"
      className="h-2 w-2 shrink-0 rounded-sm"
      style={{ background: warna }}
    />
  );
}

function TombolPilih({
  aktif,
  onClick,
  children,
}: {
  aktif: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={aktif}
      onClick={onClick}
      className={`min-h-9 border-l border-line-strong px-3 text-xs font-semibold transition-colors first:border-l-0 ${
        aktif ? "bg-brand text-white" : "bg-surface text-ink hover:bg-paper"
      }`}
    >
      {children}
    </button>
  );
}

function BarisTooltip({
  warna,
  label,
  nilai,
  persen,
}: {
  warna: string;
  label: string;
  nilai: number;
  persen: number;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="inline-flex items-center gap-1.5 text-muted">
        <TitikWarna warna={warna} />
        {label}
      </dt>
      <dd className="font-mono font-semibold tabular-nums text-ink">
        {formatAngka(nilai)}
        <span className="ml-1 font-normal text-muted">({persen}%)</span>
      </dd>
    </div>
  );
}

function TooltipBatasKabKota({ active, payload }: TooltipContentProps) {
  const data = payload?.[0]?.payload as BatangBatasKabKota | undefined;
  if (!active || !data) {
    return null;
  }

  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold text-ink">{data.label}</p>
      <dl className="mt-1 space-y-0.5">
        {URUTAN_KATEGORI.map((kategori) => (
          <BarisTooltip
            key={kategori.kunci}
            warna={WARNA_KATEGORI[kategori.kunci]}
            label={kategori.label}
            nilai={data[kategori.kunci]}
            persen={Math.round(persenDari(data[kategori.kunci], data.total))}
          />
        ))}
      </dl>
      <p className="mt-1 border-t border-line pt-1 text-muted">
        Total {formatAngka(data.total)} pasangan
      </p>
    </div>
  );
}

export function GrafikBatasKabKota({
  data,
  diperbarui,
}: {
  data: BatangBatasKabKota[];
  diperbarui?: string | null;
}) {
  const [urutKunci, setUrutKunci] = useState<KunciUrutGrafik>("kode");
  const [urutArah, setUrutArah] = useState<ArahUrut>("asc");
  // "proporsi" = 100% bertumpuk, "jumlah" = tinggi batang sebesar jumlah
  // pasangan apa adanya.
  const [modeNilai, setModeNilai] = useState<"proporsi" | "jumlah">("proporsi");
  const [layarPenuh, setLayarPenuh] = useState(false);
  const tombolTutupRef = useRef<HTMLButtonElement | null>(null);

  // Layar penuh: fokus ke tombol tutup, tutup dengan Escape, dan kunci gulir
  // halaman selama tampilan penuh terbuka.
  useEffect(() => {
    if (!layarPenuh) {
      return;
    }
    tombolTutupRef.current?.focus();
    const overflowAwal = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function saatTombol(kejadian: KeyboardEvent) {
      if (kejadian.key === "Escape") {
        setLayarPenuh(false);
      }
    }
    window.addEventListener("keydown", saatTombol);
    return () => {
      window.removeEventListener("keydown", saatTombol);
      document.body.style.overflow = overflowAwal;
    };
  }, [layarPenuh]);

  const proporsi = modeNilai === "proporsi";

  // Kunci "clean" mengikuti mode tampilan: pada mode proporsi urutkan menurut
  // persentase clean, pada mode jumlah urutkan menurut banyaknya pasangan clean
  // supaya panjang batang hijau memang berurutan di layar.
  const dataTerurut = useMemo(() => {
    const faktor = urutArah === "asc" ? 1 : -1;
    return [...data].sort((a, b) => {
      const selisih =
        urutKunci === "kode"
          ? a.kode.localeCompare(b.kode)
          : proporsi
            ? persenDari(a.clean, a.total) - persenDari(b.clean, b.total)
            : a.clean - b.clean;
      if (selisih !== 0) {
        return selisih * faktor;
      }
      return a.kode.localeCompare(b.kode);
    });
  }, [data, urutKunci, urutArah, proporsi]);

  if (data.length < 2) {
    return (
      <p className="p-kartu text-sm text-muted">
        Grafik butuh minimal 2 kabupaten/kota untuk dibandingkan. Pilih wilayah
        lain pada saringan untuk melihat sebarannya.
      </p>
    );
  }

  const kontrolUrut = (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
      <div className="inline-flex items-center gap-2">
        <span className="text-muted">Nilai batang:</span>
        <div className="inline-flex overflow-hidden rounded-lg border border-line-strong">
          <TombolPilih
            aktif={modeNilai === "proporsi"}
            onClick={() => setModeNilai("proporsi")}
          >
            Proporsi
          </TombolPilih>
          <TombolPilih
            aktif={modeNilai === "jumlah"}
            onClick={() => setModeNilai("jumlah")}
          >
            Jumlah
          </TombolPilih>
        </div>
      </div>
      <div className="inline-flex items-center gap-2">
        <span className="text-muted">Urutkan menurut:</span>
        <div className="inline-flex overflow-hidden rounded-lg border border-line-strong">
          <TombolPilih
            aktif={urutKunci === "kode"}
            onClick={() => setUrutKunci("kode")}
          >
            Kode
          </TombolPilih>
          <TombolPilih
            aktif={urutKunci === "clean"}
            onClick={() => setUrutKunci("clean")}
          >
            Clean
          </TombolPilih>
        </div>
      </div>
      <div className="inline-flex items-center gap-2">
        <span className="text-muted">Arah:</span>
        <div className="inline-flex overflow-hidden rounded-lg border border-line-strong">
          <TombolPilih
            aktif={urutArah === "asc"}
            onClick={() => setUrutArah("asc")}
          >
            Naik
          </TombolPilih>
          <TombolPilih
            aktif={urutArah === "desc"}
            onClick={() => setUrutArah("desc")}
          >
            Turun
          </TombolPilih>
        </div>
      </div>
    </div>
  );

  const bagan = (tinggi: string) => (
    <div className="mt-3 overflow-x-auto">
      <div className={`${tinggi} min-w-[1100px]`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={dataTerurut}
            stackOffset={proporsi ? "expand" : "none"}
            margin={{ top: 18, right: 12, left: 0, bottom: 8 }}
            barCategoryGap="18%"
          >
            <CartesianGrid
              vertical={false}
              stroke="var(--line)"
              strokeDasharray="3 3"
            />
            <XAxis
              dataKey="label"
              interval={0}
              angle={-45}
              textAnchor="end"
              height={96}
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--line)" }}
            />
            <YAxis
              {...(proporsi
                ? {
                    domain: [0, 1] as [number, number],
                    ticks: [0, 0.25, 0.5, 0.75, 1],
                    tickFormatter: (nilai: number) => `${Math.round(nilai * 100)}%`,
                  }
                : { allowDecimals: false })}
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickLine={false}
              axisLine={false}
              width={44}
            />
            <Tooltip
              cursor={{ fill: "var(--brand-soft)", opacity: 0.45 }}
              content={(props) => <TooltipBatasKabKota {...props} />}
            />
            <BarStack radius={4}>
              {URUTAN_KATEGORI.map((kategori) => (
                <Bar
                  key={kategori.kunci}
                  dataKey={kategori.kunci}
                  name={kategori.label}
                  fill={WARNA_KATEGORI[kategori.kunci]}
                  stroke="var(--surface)"
                  strokeWidth={1}
                  isAnimationActive={false}
                />
              ))}
            </BarStack>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );

  const legenda = (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {URUTAN_KATEGORI.map((kategori) => (
        <span key={kategori.kunci} className="inline-flex items-center gap-1.5">
          <TitikWarna warna={WARNA_KATEGORI[kategori.kunci]} />
          {kategori.label}
        </span>
      ))}
    </div>
  );

  if (layarPenuh) {
    return (
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="judul-grafik-batas"
        className="fixed inset-0 z-50 flex flex-col bg-paper"
      >
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-line bg-surface px-4 py-3">
          <span aria-hidden="true" />
          <div className="text-center">
            <h2
              id="judul-grafik-batas"
              className="text-sm font-bold text-ink sm:text-base"
            >
              {JUDUL_GRAFIK}
            </h2>
            {diperbarui ? (
              <p className="mt-0.5 text-xs text-muted">
                Diperbarui {diperbarui} WIB
              </p>
            ) : null}
          </div>
          <button
            ref={tombolTutupRef}
            type="button"
            aria-label="Tutup layar penuh"
            title="Tutup layar penuh"
            onClick={() => setLayarPenuh(false)}
            className="inline-flex h-9 w-9 items-center justify-center justify-self-end rounded-lg border border-line-strong bg-surface text-ink transition-colors hover:border-brand hover:text-brand-strong"
          >
            <IkonKeluarLayarPenuh />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          {kontrolUrut}
          {bagan("h-[75vh]")}
          {legenda}
        </div>
      </div>
    );
  }

  return (
    <div className="p-kartu">
      <div className="flex flex-wrap items-start justify-between gap-2">
        {kontrolUrut}
        <button
          type="button"
          aria-label="Tampilkan layar penuh"
          title="Layar penuh"
          onClick={() => setLayarPenuh(true)}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-line-strong bg-surface text-ink transition-colors hover:border-brand hover:text-brand-strong"
        >
          <IkonLayarPenuh />
        </button>
      </div>
      {bagan("h-[400px]")}
      {legenda}
    </div>
  );
}
