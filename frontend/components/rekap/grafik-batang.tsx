"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import type { TabulasiProgresBaris } from "@/lib/api/types";
import { formatAngka } from "@/lib/format";
import { namaKabupatenTampil } from "@/lib/wilayah/kabupaten";

type Batang = {
  kode: string;
  nama: string;
  nilai: number;
  selesai: number;
  target: number;
  persenLabel: string;
  status: string;
  bisaDibuka: boolean;
  asli: TabulasiProgresBaris;
};

function warnaBatang(status: string): string {
  switch (status) {
    case "selesai":
      return "var(--success)";
    case "berjalan":
      return "var(--brand)";
    case "mundur":
      return "var(--danger)";
    case "belum_b":
      return "var(--accent)";
    default:
      return "var(--line-strong)";
  }
}

function formatPersen(nilai: number | null): string {
  if (nilai == null) {
    return "-";
  }
  return `${nilai.toLocaleString("id-ID", {
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  })}%`;
}

function TooltipBatang({ active, payload }: TooltipContentProps) {
  const data = payload?.[0]?.payload as Batang | undefined;
  if (!active || !data) {
    return null;
  }

  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold text-ink">
        {data.kode} · {data.nama}
      </p>
      <p className="mt-1 text-muted">
        Selesai {formatAngka(data.selesai)} / {formatAngka(data.target)}
      </p>
      <p className="text-muted">Penyelesaian {data.persenLabel}</p>
    </div>
  );
}

export function GrafikBatang({
  baris,
  tingkat,
  onBuka,
}: {
  baris: TabulasiProgresBaris[];
  tingkat: "kabupaten" | "kecamatan" | "desa";
  onBuka: (baris: TabulasiProgresBaris) => void;
}) {
  const data: Batang[] = baris.map((satu) => {
    const nama =
      satu.level === "kabupaten"
        ? namaKabupatenTampil(satu.kode ?? "", satu.nama)
        : satu.nama;
    return {
      kode: satu.kode ?? "-",
      nama: nama ?? "(tanpa wilayah)",
      nilai:
        satu.persen == null ? 0 : Math.max(0, Math.min(100, satu.persen)),
      selesai: satu.selesai,
      target: satu.target,
      persenLabel: formatPersen(satu.persen),
      status: satu.status,
      bisaDibuka: Boolean(satu.kode && tingkat !== "desa"),
      asli: satu,
    };
  });

  if (data.length === 0) {
    return (
      <p className="p-kartu text-sm text-muted">
        Belum ada data untuk ditampilkan.
      </p>
    );
  }

  return (
    <div className="p-kartu">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <p>Panjang batang menunjukkan persen penyelesaian.</p>
        <p>Klik batang untuk turun ke wilayah di bawahnya.</p>
      </div>

      <div className="overflow-x-auto">
        <div className="h-[360px] min-w-[1000px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              margin={{ top: 18, right: 12, left: 0, bottom: 8 }}
              barCategoryGap="18%"
            >
              <CartesianGrid
                vertical={false}
                stroke="var(--line)"
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="kode"
                interval={0}
                angle={-45}
                textAnchor="end"
                height={64}
                tick={{ fontSize: 10, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--line)" }}
              />
              <YAxis
                domain={[0, 100]}
                ticks={[0, 25, 50, 75, 100]}
                tickFormatter={(nilai) => `${nilai}%`}
                tick={{ fontSize: 10, fill: "var(--muted)" }}
                tickLine={false}
                axisLine={false}
                width={42}
              />
              <Tooltip
                cursor={{ fill: "var(--brand-soft)", opacity: 0.45 }}
                content={(props) => <TooltipBatang {...props} />}
              />
              <Bar
                dataKey="nilai"
                name="Penyelesaian"
                radius={[4, 4, 0, 0]}
                maxBarSize={34}
                isAnimationActive={false}
                onClick={(data) => {
                  const row = data?.payload as Batang | undefined;
                  if (row?.bisaDibuka) {
                    onBuka(row.asli);
                  }
                }}
              >
                {data.map((satu) => (
                  <Cell
                    key={`${satu.asli.level}-${satu.kode}`}
                    fill={warnaBatang(satu.status)}
                    cursor={satu.bisaDibuka ? "pointer" : "default"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-success" /> Selesai
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-brand" /> Berjalan
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-danger" /> Mundur
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-accent" /> Belum ada B
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-line-strong" /> Belum siap
        </span>
      </div>
    </div>
  );
}
