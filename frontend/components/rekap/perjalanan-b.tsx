"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EmptyState, Panel, TautanAksi } from "@/components/dashboard/ui";
import { adalahBatal, ambilJson, pesanKesalahan } from "@/lib/api/klien";
import type { ProgresB } from "@/lib/api/types";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";

function persen(nilai: number | null | undefined): string {
  return nilai == null ? "-" : `${formatAngka(nilai)}%`;
}

function delta(nilai: number): string {
  if (nilai === 0) return "tetap";
  return nilai > 0
    ? `turun ${formatAngka(nilai)}`
    : `naik ${formatAngka(Math.abs(nilai))}`;
}

function urutkanBaris(baris: ProgresB["baris"]): ProgresB["baris"] {
  return [...baris].sort((kiri, kanan) => {
    const waktuKiri = kiri.selesai_pada ?? "";
    const waktuKanan = kanan.selesai_pada ?? "";
    if (waktuKiri !== waktuKanan) {
      return waktuKiri.localeCompare(waktuKanan);
    }
    return kiri.run_id - kanan.run_id;
  });
}

export function PerjalananB({ kdkab }: { kdkab: string }) {
  const [data, setData] = useState<ProgresB | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [pilihan, setPilihan] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async () => {
    if (!kdkab) {
      setMemuat(false);
      setData(null);
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
      const urut = urutkanBaris(hasil.baris);
      setData({ ...hasil, baris: urut });
      setPilihan(urut.at(-1)?.run_id ?? null);
    } catch (kesalahan) {
      if (!adalahBatal(kesalahan)) setGalat(pesanKesalahan(kesalahan));
    } finally {
      if (!controller.signal.aborted) setMemuat(false);
    }
  }, [kdkab]);

  useEffect(() => {
    const timer = window.setTimeout(() => void muat(), 0);
    return () => {
      window.clearTimeout(timer);
      controllerRef.current?.abort();
    };
  }, [muat]);

  const baris = data?.baris ?? [];
  const aktif = useMemo(
    () => baris.find((satu) => satu.run_id === pilihan) ?? null,
    [baris, pilihan],
  );

  if (!kdkab) {
    return (
      <Panel judul="Perjalanan Proses B">
        <EmptyState judul="Pilih kabupaten/kota">
          Progres perjalanan ditampilkan per kabupaten/kota.
        </EmptyState>
      </Panel>
    );
  }

  if (memuat && data === null) {
    return (
      <Panel judul="Perjalanan Proses B">
        <p className="mt-3 text-sm text-muted" role="status">
          Membaca riwayat upload…
        </p>
      </Panel>
    );
  }

  if (galat) {
    return (
      <Panel judul="Perjalanan Proses B">
        <div role="alert" className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink">
          {galat}
        </div>
      </Panel>
    );
  }

  if (!data?.target) {
    return (
      <Panel
        judul="Perjalanan perbaikan"
        deskripsi="Target perbaikan terbentuk dari hasil Proses A terbaru."
      >
        <EmptyState
          judul="Target belum terbentuk"
          aksi={
            <TautanAksi href="/proses/identifikasi" varian="sekunder">
              Jalankan Proses A
            </TautanAksi>
          }
        >
          Setelah Proses A terbaru sukses, jumlah titik dengan flag 1 akan
          menjadi target penyelesaian Proses B.
        </EmptyState>
      </Panel>
    );
  }

  const target = data.target;
  const sisa = baris.at(-1)?.sisa_flag_1 ?? target.flag_1;
  const beres = Math.max(target.flag_1 - sisa, 0);
  const persenSelesai = target.flag_1
    ? Math.round((beres / target.flag_1) * 1000) / 10
    : null;
  const nama = data.nmkab || data.kdkab;

  return (
    <div className="space-y-field">
      <Panel
        judul={`Perjalanan perbaikan ${nama}`}
        deskripsi="Setiap upload Proses B menjadi satu titik waktu. Angka dihitung terhadap target dari Proses A terbaru."
      >
        <div className="mt-3 grid gap-field lg:grid-cols-[minmax(0,1.2fr)_minmax(16rem,0.8fr)] lg:items-end">
          <div>
            <p className="text-xs font-semibold text-muted">Progres target</p>
            <p className="mt-1 font-display text-5xl font-semibold tracking-tight text-ink sm:text-6xl">
              {persenSelesai == null ? "-" : `${formatAngka(persenSelesai)}%`}
            </p>
            <p className="mt-1 text-sm leading-normal text-muted">
              {formatAngka(beres)} dari {formatAngka(target.flag_1)} titik flag 1
              sudah beres.
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-field border-t border-line pt-3 lg:border-t-0 lg:border-l lg:pl-5">
            <div>
              <dt className="text-xs text-muted">Target awal</dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums text-ink">
                {formatAngka(target.flag_1)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Sisa flag 1</dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums text-accent-strong">
                {formatAngka(sisa)}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-xs text-muted">Terakhir diperbarui</dt>
              <dd className="mt-1 text-sm font-medium text-ink">
                {baris.length
                  ? formatWaktu(baris.at(-1)?.selesai_pada)
                  : "Belum ada upload Proses B"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="mt-3 h-4 overflow-hidden rounded-full bg-brand-soft">
          <div
            className="h-full rounded-full bg-brand transition-[width] duration-300 motion-reduce:transition-none"
            style={{ width: `${Math.min(100, Math.max(0, persenSelesai ?? 0))}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-xs text-muted">
          <span>0</span>
          <span>Target {formatAngka(target.flag_1)}</span>
        </div>
      </Panel>

      <Panel
        judul="Rel upload"
        deskripsi="Klik titik untuk melihat rincian upload tersebut. Garis naik berarti titik flag 1 yang sudah beres."
      >
        {baris.length === 0 ? (
          <EmptyState
            judul="Belum ada upload Proses B"
            aksi={
              <TautanAksi href="/proses/pengecekan" varian="sekunder">
                Buka Proses B
              </TautanAksi>
            }
          >
            Target sudah terbentuk. Upload hasil edit untuk mulai mengukur
            perjalanan perbaikan.
          </EmptyState>
        ) : (
          <>
            <RelProgres
              target={target.flag_1}
              baris={baris}
              pilihan={pilihan}
              onPilih={setPilihan}
            />
            {aktif ? (
              <div className="mt-1 flex flex-wrap items-baseline justify-between gap-field border-t border-line pt-3">
                <div>
                  <p className="text-sm font-semibold text-ink">
                    Upload ke-{aktif.nomor_urut ?? "-"} ·{" "}
                    {formatTanggal(aktif.tanggal_data)}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    Selesai {formatWaktu(aktif.selesai_pada)}
                  </p>
                </div>
                <p className="text-sm text-muted">
                  Sisa {formatAngka(aktif.sisa_flag_1)} ·{" "}
                  {delta(aktif.perubahan)} · {persen(aktif.persen)}
                </p>
              </div>
            ) : null}
          </>
        )}
      </Panel>

      {baris.length > 0 ? (
        <Panel
          judul="Riwayat upload"
          deskripsi="Waktu selesai proses, sisa flag 1, dan perubahan dari upload sebelumnya."
        >
          <div className="mt-1 overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="py-2 pl-3 pr-3 font-semibold">Upload</th>
                  <th className="py-2 pr-3 font-semibold">Tanggal data</th>
                  <th className="py-2 pr-3 font-semibold">Selesai diproses</th>
                  <th className="py-2 pr-3 text-right font-semibold">Sisa flag 1</th>
                  <th className="py-2 pr-3 text-right font-semibold">Beres</th>
                  <th className="py-2 text-right font-semibold">Perubahan</th>
                </tr>
              </thead>
              <tbody>
                {baris.map((baris) => (
                  <tr
                    key={baris.run_id}
                    className={`border-b border-line/70 last:border-0 ${
                      baris.run_id === pilihan ? "bg-brand-soft/50" : ""
                    }`}
                  >
                    <td className="py-2 pl-3 pr-3 font-medium text-ink">
                      ke-{baris.nomor_urut ?? "-"}
                    </td>
                    <td className="py-2 pr-3 text-muted">{formatTanggal(baris.tanggal_data)}</td>
                    <td className="py-2 pr-3 text-muted">{formatWaktu(baris.selesai_pada)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums text-ink">
                      {formatAngka(baris.sisa_flag_1)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums text-ink">
                      {formatAngka(baris.beres)} ({persen(baris.persen)})
                    </td>
                    <td className="py-2 text-right text-muted">{delta(baris.perubahan)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function RelProgres({
  target,
  baris,
  pilihan,
  onPilih,
}: {
  target: number;
  baris: ProgresB["baris"];
  pilihan: number | null;
  onPilih: (runId: number) => void;
}) {
  const lebar = 760;
  const tinggi = 240;
  const kiri = 46;
  const kanan = 22;
  const atas = 30;
  const bawah = 48;
  const areaLebar = lebar - kiri - kanan;
  const areaTinggi = tinggi - atas - bawah;
  const jumlah = baris.length;
  const skala = target > 0 ? target : 1;

  const titik = baris.map((satu, indeks) => {
    const x =
      kiri +
      (jumlah === 1
        ? areaLebar / 2
        : (indeks / (jumlah - 1)) * areaLebar);
    const y = atas + areaTinggi - (satu.beres / skala) * areaTinggi;
    const tanggalSebelum = indeks > 0 ? baris[indeks - 1].tanggal_data : null;
    return {
      ...satu,
      x,
      y,
      tampilTanggal:
        indeks === 0 || satu.tanggal_data !== tanggalSebelum,
      turun: satu.perubahan < 0,
    };
  });

  const garis = titik.map((satu) => `${satu.x},${satu.y}`).join(" ");
  const adaTurun = titik.some((satu) => satu.turun);
  const yTarget = target > 0 ? atas : atas + areaTinggi;

  return (
    <div className="mt-3">
      <svg
        viewBox={`0 0 ${lebar} ${tinggi}`}
        role="img"
        aria-label="Grafik perjalanan perbaikan Proses B"
        className="h-auto w-full overflow-visible"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((bagian) => {
          const y = atas + areaTinggi - bagian * areaTinggi;
          return (
            <g key={bagian}>
              <line
                x1={kiri}
                x2={lebar - kanan}
                y1={y}
                y2={y}
                stroke="var(--line)"
                strokeWidth="1"
              />
              <text
                x={kiri - 8}
                y={y + 4}
                textAnchor="end"
                fontSize="11"
                fill="var(--muted)"
              >
                {formatAngka(Math.round(target * bagian))}
              </text>
            </g>
          );
        })}

        <line
          x1={kiri}
          x2={lebar - kanan}
          y1={yTarget}
          y2={yTarget}
          stroke="var(--accent-strong)"
          strokeWidth="1.5"
          strokeDasharray="6 4"
        />
        <text
          x={lebar - kanan}
          y={yTarget - 7}
          textAnchor="end"
          fontSize="11"
          fontWeight="600"
          fill="var(--accent-strong)"
        >
          Target {formatAngka(target)}
        </text>

        {titik.length > 1 ? (
          <polyline
            points={garis}
            fill="none"
            stroke="var(--brand)"
            strokeWidth="3"
            strokeLinejoin="miter"
            strokeLinecap="butt"
          />
        ) : null}

        {titik.map((satu) => (
          <g key={satu.run_id}>
            <circle
              cx={satu.x}
              cy={satu.y}
              r={pilihan === satu.run_id ? 7 : 5}
              fill={
                pilihan === satu.run_id
                  ? "var(--accent)"
                  : satu.turun
                    ? "var(--danger)"
                    : "var(--brand)"
              }
              stroke="var(--surface)"
              strokeWidth="2"
            >
              <title>
                Upload ke-{satu.nomor_urut ?? "-"} ·{" "}
                {formatWaktu(satu.selesai_pada)} · {formatAngka(satu.beres)}{" "}
                beres · {delta(satu.perubahan)}
              </title>
            </circle>
            {satu.tampilTanggal ? (
              <text
                x={satu.x}
                y={tinggi - 12}
                textAnchor="middle"
                fontSize="11"
                fill="var(--muted)"
              >
                {formatTanggal(satu.tanggal_data)}
              </text>
            ) : null}
          </g>
        ))}
      </svg>

      <div className="mt-1 flex flex-wrap gap-field">
        {baris.map((satu) => (
          <button
            key={satu.run_id}
            type="button"
            onClick={() => onPilih(satu.run_id)}
            title={`${formatTanggal(satu.tanggal_data)} · ${formatWaktu(
              satu.selesai_pada,
            )}`}
            className={`min-h-9 rounded-md border px-tombol text-xs font-medium ${
              pilihan === satu.run_id
                ? "border-brand bg-brand-soft text-brand-strong"
                : "border-line bg-surface text-muted hover:border-brand"
            }`}
          >
            ke-{satu.nomor_urut ?? "-"}
          </button>
        ))}
      </div>

      {adaTurun ? (
        <p className="mt-2 flex items-center gap-2 text-xs text-muted">
          <span
            aria-hidden="true"
            className="inline-block h-2 w-2 rounded-full bg-danger"
          />
          Titik merah menandakan progres turun.
        </p>
      ) : null}
    </div>
  );
}
