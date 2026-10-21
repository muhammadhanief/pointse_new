"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { EmptyState, Panel, TautanAksi } from "@/components/dashboard/ui";
import { adalahBatal, ambilJson, pesanKesalahan } from "@/lib/api/klien";
import type { ProgresB, Ringkasan } from "@/lib/api/types";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";
import {
  kodeKabupaten,
  namaKabupatenTampil,
} from "@/lib/wilayah/kabupaten";

type Seri = {
  kode: string;
  nama: string;
  baris: ProgresB["baris"];
};

type Titik = Record<string, number>;

const WARNA = [
  "#1d4f78",
  "#2c6a4d",
  "#9f3a32",
  "#a96617",
  "#5c6672",
  "#0f766e",
  "#7c3aed",
  "#be123c",
  "#0369a1",
  "#4d7c0f",
];

function waktuMs(nilai: string): number {
  const iso = /[zZ]$|[+-]\d{2}:\d{2}$/.test(nilai) ? nilai : `${nilai}Z`;
  return Date.parse(iso);
}

function TooltipProvinsi({
  active,
  payload,
  label,
}: TooltipContentProps) {
  if (!active || !payload?.length) {
    return null;
  }

  const isi = payload.filter((satu) => typeof satu.value === "number");
  const waktu = Number(label);

  return (
    <div className="max-h-64 overflow-y-auto rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="font-semibold text-ink">
        {Number.isFinite(waktu)
          ? formatWaktu(new Date(waktu).toISOString())
          : String(label ?? "-")}
      </p>
      <div className="mt-1 space-y-0.5">
        {isi.map((satu) => (
          <p key={String(satu.dataKey)} className="text-muted">
            <span
              className="mr-1.5 inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: satu.color }}
            />
            {satu.name}: {formatAngka(Number(satu.value))}%
          </p>
        ))}
      </div>
    </div>
  );
}

export function PerjalananBProvinsi({ kdprov }: { kdprov: string }) {
  const [seri, setSeri] = useState<Seri[]>([]);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [tersembunyi, setTersembunyi] = useState<Set<string>>(
    () => new Set(),
  );

  const muat = useCallback(
    async (signal: AbortSignal) => {
      setMemuat(true);
      setGalat(null);
      try {
        const ringkasan = await ambilJson<Ringkasan>("/ringkasan?dasar=tugas", {
          signal,
        });
        const kandidat = ringkasan.baris.filter(
          (satu) =>
            !satu.belum_ada_upload_tipe_b &&
            satu.terakhir.some((item) => item.tipe === "B"),
        );

        const hasil = await Promise.all(
          kandidat.map(async (satu) => {
            const kode = kodeKabupaten(kdprov, satu.kdkab);
            try {
              const progres = await ambilJson<ProgresB>(
                `/progres-b?kdkab=${encodeURIComponent(kode)}`,
                { signal },
              );
              if (!progres.target || progres.baris.length === 0) {
                return null;
              }
              return {
                kode,
                nama:
                  namaKabupatenTampil(
                    kode,
                    progres.nmkab ?? satu.nmkab ?? null,
                  ) ?? kode,
                baris: progres.baris,
              } satisfies Seri;
            } catch (kesalahan) {
              if (adalahBatal(kesalahan)) {
                throw kesalahan;
              }
              return null;
            }
          }),
        );

        if (!signal.aborted) {
          setSeri(hasil.filter((satu): satu is Seri => satu !== null));
        }
      } catch (kesalahan) {
        if (!adalahBatal(kesalahan)) {
          setGalat(pesanKesalahan(kesalahan));
        }
      } finally {
        if (!signal.aborted) {
          setMemuat(false);
        }
      }
    },
    [kdprov],
  );

  useEffect(() => {
    const controller = new AbortController();
    void muat(controller.signal);
    return () => controller.abort();
  }, [muat]);

  function alihkanSeri(kode: string) {
    setTersembunyi((lama) => {
      const baru = new Set(lama);
      if (baru.has(kode)) {
        baru.delete(kode);
      } else {
        baru.add(kode);
      }
      return baru;
    });
  }

  const { data, kunci } = useMemo(() => {
    const peta = new Map<number, Titik>();
    const kunci: { kode: string; nama: string }[] = [];

    for (const satu of seri) {
      kunci.push({ kode: satu.kode, nama: satu.nama });
      for (const baris of satu.baris) {
        const waktu = waktuMs(
          baris.selesai_pada ?? `${baris.tanggal_data}T00:00:00Z`,
        );
        if (!Number.isFinite(waktu)) {
          continue;
        }
        const titik = peta.get(waktu) ?? { waktu };
        titik[satu.kode] = baris.persen ?? 0;
        peta.set(waktu, titik);
      }
    }

    return {
      data: [...peta.values()].sort(
        (kiri, kanan) => Number(kiri.waktu) - Number(kanan.waktu),
      ),
      kunci,
    };
  }, [seri]);

  return (
    <Panel
      judul="Tren"
      deskripsi="Semua kabupaten/kota yang sudah punya upload Proses B ditampilkan sebagai garis terpisah."
    >
      {memuat ? (
        <p className="mt-3 text-sm text-muted" role="status">
          Membaca tren Proses B kabupaten/kota...
        </p>
      ) : null}

      {galat ? (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
        >
          {galat}
        </div>
      ) : null}

      {!memuat && !galat && seri.length === 0 ? (
        <EmptyState
          judul="Belum ada upload Proses B"
          aksi={
            <TautanAksi href="/proses/pengecekan" varian="sekunder">
              Buka Proses B
            </TautanAksi>
          }
        >
          Setelah kabupaten/kota mengunggah titik hasil perbaikan, garis progres
          akan tampil di sini.
        </EmptyState>
      ) : null}

      {!memuat && !galat && seri.length > 0 ? (
        <>
          <div className="mt-3 overflow-x-auto">
            <div className="h-[380px] min-w-[1000px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={data}
                  margin={{ top: 18, right: 18, left: 0, bottom: 8 }}
                >
                  <CartesianGrid
                    vertical={false}
                    stroke="var(--line)"
                    strokeDasharray="3 3"
                  />
                  <XAxis
                    dataKey="waktu"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    scale="time"
                    minTickGap={28}
                    tickFormatter={(nilai) =>
                      formatTanggal(new Date(Number(nilai)).toISOString())
                    }
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
                    content={(props) => <TooltipProvinsi {...props} />}
                  />
                  {kunci.map((satu, indeks) =>
                    tersembunyi.has(satu.kode) ? null : (
                      <Line
                        key={satu.kode}
                        type="linear"
                        dataKey={satu.kode}
                        name={`${satu.kode} ${satu.nama}`}
                        stroke={WARNA[indeks % WARNA.length]}
                        strokeWidth={2}
                        dot={{ r: 2 }}
                        activeDot={{ r: 4 }}
                        connectNulls
                        isAnimationActive={false}
                      />
                    ),
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div
            className="mt-2 flex max-h-28 flex-wrap gap-x-3 gap-y-1 overflow-y-auto pr-1"
            role="group"
            aria-label="Legenda kabupaten/kota"
          >
            {kunci.map((satu, indeks) => {
              const aktif = !tersembunyi.has(satu.kode);
              return (
                <button
                  key={satu.kode}
                  type="button"
                  onClick={() => alihkanSeri(satu.kode)}
                  aria-pressed={aktif}
                  title={`${aktif ? "Sembunyikan" : "Tampilkan"} ${satu.kode} ${satu.nama}`}
                  className={`inline-flex items-center gap-1.5 rounded px-1 py-0.5 text-[11px] transition-colors ${
                    aktif
                      ? "text-ink hover:bg-paper"
                      : "text-muted line-through opacity-50"
                  }`}
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{
                      backgroundColor: WARNA[indeks % WARNA.length],
                    }}
                  />
                  <span className="font-mono text-[10px]">{satu.kode}</span>
                  <span>{satu.nama}</span>
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-muted">
            {kunci.length} kabupaten/kota dengan upload Proses B. Klik legenda
            untuk menyembunyikan atau menampilkan garis.
          </p>
        </>
      ) : null}
    </Panel>
  );
}
