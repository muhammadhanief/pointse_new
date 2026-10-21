"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, TombolAksi } from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
} from "@/lib/api/klien";
import type {
  TabulasiProgres,
  TabulasiProgresBaris,
} from "@/lib/api/types";
import { formatAngka, formatTanggal } from "@/lib/format";
import {
  daftarKabupaten,
  kodeKabupaten,
  namaKabupatenTampil,
} from "@/lib/wilayah/kabupaten";

type Tingkat = "kabupaten" | "kecamatan" | "desa";
type Dasar = "tugas" | "posisi";

const LABEL_STATUS: Record<string, string> = {
  belum_b: "Belum ada B",
  berjalan: "Berjalan",
  selesai: "Selesai",
  mundur: "Mundur",
  tanpa_target: "Tanpa target",
};

function gayaStatus(status: string): string {
  switch (status) {
    case "selesai":
      return "border-success/30 bg-success-soft text-success";
    case "berjalan":
      return "border-brand/25 bg-brand-soft text-brand-strong";
    case "mundur":
      return "border-danger/30 bg-danger-soft text-danger";
    case "tanpa_target":
      return "border-line bg-paper text-muted";
    default:
      return "border-accent/30 bg-accent-soft text-accent-strong";
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

function Chevron() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      className="h-4 w-4 shrink-0 text-muted"
    >
      <path
        d="m7 4 6 6-6 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function BarPenyelesaian({ nilai }: { nilai: number | null }) {
  const lebar = nilai == null ? 0 : Math.max(0, Math.min(100, nilai));
  return (
    <div className="flex items-center justify-end gap-2.5">
      <div
        className="h-1.5 w-16 overflow-hidden rounded-full bg-brand-soft sm:w-20"
        aria-hidden="true"
      >
        <div className="h-full rounded-full bg-brand" style={{ width: `${lebar}%` }} />
      </div>
      <span className="w-14 text-right tabular-nums">{formatPersen(nilai)}</span>
    </div>
  );
}

function barisKosong(kode: string, nama: string): TabulasiProgresBaris {
  return {
    kode,
    induk: null,
    nama,
    level: "kabupaten",
    jumlah: 0,
    target: 0,
    selesai: 0,
    sisa: 0,
    persen: null,
    status: "tanpa_target",
    ada_b: false,
  };
}

export function TabulasiRekap({
  kdprov,
  kdkabAwal,
}: {
  kdprov: string;
  kdkabAwal: string | null;
}) {
  const tingkatAwal: Tingkat = kdkabAwal ? "kecamatan" : "kabupaten";
  const [tingkat, setTingkat] = useState<Tingkat>(tingkatAwal);
  const [kdkab, setKdkab] = useState<string | null>(kdkabAwal);
  const [kdkec, setKdkec] = useState<string | null>(null);
  const [dasar, setDasar] = useState<Dasar>("tugas");
  const [cari, setCari] = useState("");
  const [data, setData] = useState<TabulasiProgres | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);

  const muat = useCallback(
    async (isyarat: AbortSignal) => {
      setMemuat(true);
      setGalat(null);
      setData(null);
      const parameter = new URLSearchParams({
        tingkat,
        dasar,
        kdprov,
      });
      if (kdkab) {
        parameter.set("kdkab", kdkab);
      }
      if (kdkec) {
        parameter.set("kdkec", kdkec);
      }

      try {
        const hasil = await ambilJson<TabulasiProgres>(
          `/tabulasi-progres?${parameter.toString()}`,
          { signal: isyarat },
        );
        setData(hasil);
      } catch (kesalahan) {
        if (adalahBatal(kesalahan)) {
          return;
        }
        setGalat(pesanKesalahan(kesalahan));
      } finally {
        if (!isyarat.aborted) {
          setMemuat(false);
        }
      }
    },
    [dasar, kdprov, kdkab, kdkec, tingkat],
  );

  useEffect(() => {
    const kendali = new AbortController();
    void muat(kendali.signal);
    return () => kendali.abort();
  }, [muat]);

  const daftarBaris = useMemo(() => {
    const barisApi = data?.baris ?? [];
    if (tingkat !== "kabupaten") {
      return barisApi;
    }
    const opsi = daftarKabupaten(kdprov);
    if (opsi.length === 0) {
      return barisApi;
    }
    const peta = new Map<string, TabulasiProgresBaris>();
    for (const baris of barisApi) {
      if (baris.kode) {
        peta.set(baris.kode, baris);
      }
    }
    const hasil = opsi.map(
      (satu) => peta.get(satu.kode) ?? barisKosong(satu.kode, satu.nama),
    );
    const dikenal = new Set(opsi.map((satu) => satu.kode));
    for (const baris of barisApi) {
      if (!baris.kode || !dikenal.has(baris.kode)) {
        hasil.push(baris);
      }
    }
    return hasil;
  }, [data, kdprov, tingkat]);

  const tersaring = useMemo(() => {
    const kata = cari.trim().toLocaleLowerCase("id-ID");
    if (!kata) {
      return daftarBaris;
    }
    return daftarBaris.filter((baris) =>
      `${baris.nama ?? ""} ${baris.kode ?? ""}`
        .toLocaleLowerCase("id-ID")
        .includes(kata),
    );
  }, [cari, daftarBaris]);

  const total = useMemo(() => {
    return tersaring.reduce(
      (jumlah, baris) => ({
        jumlah: jumlah.jumlah + baris.jumlah,
        target: jumlah.target + baris.target,
        selesai: jumlah.selesai + baris.selesai,
        sisa: jumlah.sisa + baris.sisa,
      }),
      { jumlah: 0, target: 0, selesai: 0, sisa: 0 },
    );
  }, [tersaring]);

  const persenTotal =
    total.target > 0 ? (total.selesai / total.target) * 100 : null;

  function bukaBaris(baris: TabulasiProgresBaris) {
    if (!baris.kode || tingkat === "desa") {
      return;
    }
    setCari("");
    if (tingkat === "kabupaten") {
      setKdkab(baris.kode);
      setKdkec(null);
      setTingkat("kecamatan");
      return;
    }
    setKdkec(baris.kode);
    setTingkat("desa");
  }

  function keKabupaten() {
    setCari("");
    setKdkec(null);
    if (!kdkabAwal) {
      setKdkab(null);
      setTingkat("kabupaten");
    } else {
      setKdkab(kdkabAwal);
      setTingkat("kecamatan");
    }
  }

  function keKecamatan() {
    if (tingkat === "desa" && kdkab) {
      setCari("");
      setKdkec(null);
      setTingkat("kecamatan");
    }
  }

  const bisaKembali =
    tingkat === "desa" || (tingkat === "kecamatan" && !kdkabAwal);

  const judulTabel =
    tingkat === "kabupaten"
      ? "Progres Edit Titik Bangunan"
      : tingkat === "kecamatan"
        ? "Kecamatan"
        : "Desa/kelurahan";

  const namaKabTampil = data?.nmkab
    ? namaKabupatenTampil(kodeKabupaten(kdprov, data.kdkab), data.nmkab)
    : null;

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <button
            type="button"
            onClick={keKabupaten}
            className="font-semibold text-brand-strong hover:underline"
          >
            {data?.nmprov ?? `Provinsi ${kdprov}`}
          </button>
          {namaKabTampil ? (
            <>
              <span className="text-line-strong" aria-hidden="true">
                /
              </span>
              <button
                type="button"
                onClick={keKecamatan}
                className={`font-semibold ${
                  tingkat === "kecamatan"
                    ? "text-ink"
                    : "text-brand-strong hover:underline"
                }`}
              >
                {namaKabTampil}
              </button>
            </>
          ) : null}
          {data?.nmkec ? (
            <>
              <span className="text-line-strong" aria-hidden="true">
                /
              </span>
              <span className="font-semibold text-ink">{data.nmkec}</span>
            </>
          ) : null}
        </div>

        <div className="flex flex-col gap-3 border-t border-line pt-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex flex-wrap items-end gap-3">
            {bisaKembali ? (
              <TombolAksi
                varian="sekunder"
                className="min-h-10 px-3"
                onClick={() => {
                  if (tingkat === "desa") {
                    keKecamatan();
                  } else {
                    keKabupaten();
                  }
                }}
              >
                Kembali
              </TombolAksi>
            ) : null}
            <label className="text-xs font-semibold uppercase tracking-wide text-muted">
              Dasar
              <select
                value={dasar}
                onChange={(event) => setDasar(event.target.value as Dasar)}
                className="mt-1 block min-h-10 min-w-[13rem] rounded-lg border border-line-strong bg-surface px-3 text-sm font-normal normal-case tracking-normal text-ink"
              >
                <option value="tugas">Wilayah penugasan</option>
                <option value="posisi">Posisi titik</option>
              </select>
              <span className="mt-1 block max-w-[18rem] text-[11px] font-normal normal-case leading-4 tracking-normal text-muted">
                {dasar === "tugas"
                  ? "Mengikuti kode SubSLS pada data titik."
                  : "Mengikuti wilayah hasil join peta."}
              </span>
            </label>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[13rem] flex-1 text-xs font-semibold uppercase tracking-wide text-muted sm:flex-none">
              Cari wilayah
              <input
                type="search"
                value={cari}
                onChange={(event) => setCari(event.target.value)}
                placeholder="Nama atau kode"
                className="mt-1 block min-h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm font-normal normal-case tracking-normal text-ink sm:w-56"
              />
            </label>
            <TombolAksi
              varian="sekunder"
              className="min-h-10 px-3"
              onClick={() => {
                const kendali = new AbortController();
                void muat(kendali.signal);
              }}
              disabled={memuat}
            >
              {memuat ? "Memuat..." : "Muat ulang"}
            </TombolAksi>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-line bg-surface">
        <div className="flex flex-wrap items-end justify-between gap-2 border-b border-line px-4 py-3 sm:px-5">
          <div>
            <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
              {judulTabel}
            </h2>
            {tingkat !== "kabupaten" ? (
              <p className="mt-0.5 text-xs text-muted">
                Target dari Proses A pertama, sisa dari Proses B terakhir.
              </p>
            ) : null}
          </div>
          {data && (data.target || data.pembanding) ? (
            <p className="text-xs text-muted">
              {data.target
                ? `Target: A ke-${data.target.nomor_urut ?? "-"} (${formatTanggal(data.target.tanggal_data)})`
                : "Target belum tersedia"}
              {data.pembanding
                ? ` · B ke-${data.pembanding.nomor_urut ?? "-"} (${formatTanggal(data.pembanding.tanggal_data)})`
                : " · Belum ada Proses B"}
            </p>
          ) : null}
        </div>

        {galat ? (
          <div className="m-4 rounded-lg border border-danger/30 bg-danger-soft/50 px-4 py-3 text-sm text-ink">
            <p>{galat}</p>
            <TombolAksi
              varian="sekunder"
              className="mt-3 min-h-9 px-3"
              onClick={() => {
                const kendali = new AbortController();
                void muat(kendali.signal);
              }}
            >
              Coba lagi
            </TombolAksi>
          </div>
        ) : memuat && data == null ? (
          <div className="space-y-2 p-4 sm:p-5" aria-label="Memuat tabulasi">
            {[0, 1, 2, 3, 4].map((baris) => (
              <div
                key={baris}
                className="h-11 animate-pulse rounded-lg bg-paper"
              />
            ))}
          </div>
        ) : tersaring.length === 0 ? (
          <div className="p-4 sm:p-5">
            <EmptyState judul={`Belum ada data ${judulTabel.toLocaleLowerCase("id-ID")}`}>
              {cari
                ? "Tidak ada wilayah yang cocok dengan pencarian."
                : "Belum ada run Proses A yang targetnya bisa dibaca untuk tingkat ini."}
            </EmptyState>
          </div>
        ) : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[46rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line bg-paper/70 text-left text-xs uppercase tracking-wide text-muted">
                  <th className="sticky left-0 z-10 bg-paper/95 px-4 py-2.5 font-semibold sm:px-5">
                    Wilayah
                  </th>
                  <th className="px-3 py-2.5 text-right font-semibold">Jumlah titik</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Target</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Selesai</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Sisa</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Penyelesaian</th>
                  <th className="px-4 py-2.5 text-right font-semibold sm:px-5">Status</th>
                </tr>
              </thead>
              <tbody>
                {tersaring.map((baris) => {
                  const bisaDibuka = Boolean(
                    baris.kode && tingkat !== "desa",
                  );
                  const nama =
                    baris.level === "kabupaten"
                      ? namaKabupatenTampil(baris.kode ?? "", baris.nama)
                      : baris.nama;
                  return (
                    <tr
                      key={`${baris.level}-${baris.kode ?? "null"}`}
                      tabIndex={bisaDibuka ? 0 : undefined}
                      role={bisaDibuka ? "button" : undefined}
                      aria-label={
                        bisaDibuka
                          ? `Buka ${nama ?? baris.kode}`
                          : undefined
                      }
                      onClick={() => bukaBaris(baris)}
                      onKeyDown={(event) => {
                        if (!bisaDibuka) {
                          return;
                        }
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          bukaBaris(baris);
                        }
                      }}
                      className={`border-b border-line/70 last:border-0 ${
                        bisaDibuka
                          ? "cursor-pointer transition-colors hover:bg-brand-soft/45 focus-visible:bg-brand-soft/45"
                          : ""
                      }`}
                    >
                      <td className="sticky left-0 z-10 bg-surface px-4 py-2.5 font-medium text-ink sm:px-5">
                        <span className="flex items-center gap-2">
                          {bisaDibuka ? <Chevron /> : <span className="h-4 w-4 shrink-0" />}
                          <span className="min-w-0">
                            <span className="block truncate">{nama ?? baris.kode ?? "-"}</span>
                            {baris.kode ? (
                              <span className="block font-mono text-[11px] font-normal text-muted">
                                {baris.kode}
                              </span>
                            ) : null}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-muted">
                        {formatAngka(baris.jumlah)}
                      </td>
                      <td className="px-3 py-2.5 text-right font-semibold tabular-nums text-ink">
                        {formatAngka(baris.target)}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-success">
                        {formatAngka(baris.selesai)}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-accent-strong">
                        {formatAngka(baris.sisa)}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-ink">
                        <BarPenyelesaian nilai={baris.persen} />
                      </td>
                      <td className="px-4 py-2.5 text-right sm:px-5">
                        <span
                          className={`inline-flex min-h-7 items-center rounded-full border px-2.5 text-xs font-semibold ${gayaStatus(baris.status)}`}
                        >
                          {LABEL_STATUS[baris.status] ?? baris.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t border-line bg-paper/70 font-semibold text-ink">
                  <td className="sticky left-0 z-10 bg-paper/95 px-4 py-3 sm:px-5">
                    Total {tersaring.length} wilayah
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatAngka(total.jumlah)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatAngka(total.target)}</td>
                  <td className="px-3 py-3 text-right tabular-nums text-success">
                    {formatAngka(total.selesai)}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-accent-strong">
                    {formatAngka(total.sisa)}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    {formatPersen(persenTotal)}
                  </td>
                  <td className="px-4 py-3 sm:px-5" />
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        <p className="border-t border-line px-4 py-3 text-xs leading-5 text-muted sm:px-5">
          Klik baris kabupaten/kota untuk melihat kecamatan, lalu klik kecamatan
          untuk melihat desa/kelurahan. Angka selesai = target dikurangi sisa;
          nilai dapat turun bila muncul flag baru.
        </p>
      </div>
    </section>
  );
}
