"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

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
import type { SheetData } from "write-excel-file/browser";
import { formatAngka, formatTanggal } from "@/lib/format";
import {
  daftarKabupaten,
  kodeKabupaten,
  namaKabupatenTampil,
} from "@/lib/wilayah/kabupaten";

import { GrafikBatang } from "./grafik-batang";

type Tingkat = "kabupaten" | "kecamatan" | "desa";
type KolomSort =
  | "wilayah"
  | "kode"
  | "jumlah"
  | "target"
  | "selesai"
  | "sisa"
  | "persen"
  | "pengunggah"
  | "status";
type ArahSort = "asc" | "desc";
type Sort = { kolom: KolomSort; arah: ArahSort };

const LABEL_STATUS: Record<string, string> = {
  belum_b: "Belum Unggah Titik Hasil Perbaikan",
  berjalan: "Berjalan",
  parsial: "B Parsial",
  tidak_lengkap: "B Tidak Lengkap",
  selesai: "Selesai",
  mundur: "Mundur",
  tanpa_target: "Belum Unggah Peta SLS/SubSLS Final",
};

function gayaStatus(status: string): string {
  switch (status) {
    case "selesai":
      return "border-success/30 bg-success-soft text-success";
    case "berjalan":
      return "border-brand/25 bg-brand-soft text-brand-strong";
    case "parsial":
    case "tidak_lengkap":
      return "border-accent/30 bg-accent-soft text-accent-strong";
    case "mundur":
      return "border-danger/30 bg-danger-soft text-danger";
    case "tanpa_target":
      return "border-line bg-paper text-muted";
    default:
      return "border-accent/30 bg-accent-soft text-accent-strong";
  }
}

function labelStatus(baris: TabulasiProgresBaris): string {
  const label = LABEL_STATUS[baris.status] ?? baris.status;
  if (
    (baris.status === "parsial" || baris.status === "tidak_lengkap") &&
    baris.cakupan_total > 0
  ) {
    return `${label} ${baris.cakupan_ada}/${baris.cakupan_total} ${baris.cakupan_unit ?? "wilayah"}`;
  }
  return label;
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
    <div className="flex items-center justify-end gap-2">
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

function nilaiSort(
  baris: TabulasiProgresBaris,
  kolom: KolomSort,
): string | number {
  switch (kolom) {
    case "wilayah":
      return (
        (baris.level === "kabupaten"
          ? namaKabupatenTampil(baris.kode ?? "", baris.nama)
          : baris.nama) ?? ""
      );
    case "kode":
      return baris.kode ?? "";
    case "jumlah":
      return baris.jumlah;
    case "target":
      return baris.target;
    case "selesai":
      return baris.selesai;
    case "sisa":
      return baris.sisa;
    case "persen":
      return baris.persen ?? -1;
    case "pengunggah":
      return baris.pengunggah ?? "";
    case "status":
      return labelStatus(baris);
    default:
      return "";
  }
}

function SelSort({
  label,
  kolom,
  sort,
  onSort,
  rata = "right",
  kiri = false,
  className = "",
}: {
  label: string;
  kolom: KolomSort;
  sort: Sort | null;
  onSort: (kolom: KolomSort) => void;
  rata?: "left" | "right";
  kiri?: boolean;
  className?: string;
}) {
  const aktif = sort?.kolom === kolom;
  const arah = sort && sort.kolom === kolom ? sort.arah : null;
  const ariaSort: "none" | "ascending" | "descending" =
    arah === "asc" ? "ascending" : arah === "desc" ? "descending" : "none";
  return (
    <th
      scope="col"
      aria-sort={ariaSort}
      className={`sticky top-0 border-b border-line bg-paper px-3 py-2 font-semibold ${
        kiri ? "left-0 z-30" : "z-20"
      } ${rata === "right" ? "text-right" : "text-left"} ${className}`}
    >
      <button
        type="button"
        onClick={() => onSort(kolom)}
        className={`inline-flex items-center gap-1.5 rounded hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
          rata === "right" ? "w-full justify-end" : ""
        }`}
      >
        <span>{label}</span>
        <span
          aria-hidden="true"
          className={aktif ? "text-brand-strong" : "text-muted/60"}
        >
          {arah === "asc" ? "↑" : arah === "desc" ? "↓" : "↕"}
        </span>
      </button>
    </th>
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
    pengunggah: null,
    cakupan_ada: 0,
    cakupan_total: 0,
    cakupan_unit: null,
  };
}

export function TabulasiRekap({
  kdprov,
  kdkabAwal,
  tampilan = "tabel",
  kontrol,
}: {
  kdprov: string;
  kdkabAwal: string | null;
  tampilan?: "tabel" | "grafik";
  kontrol?: ReactNode;
}) {
  const tingkatAwal: Tingkat = kdkabAwal ? "kecamatan" : "kabupaten";
  const [tingkat, setTingkat] = useState<Tingkat>(tingkatAwal);
  const [kdkab, setKdkab] = useState<string | null>(kdkabAwal);
  const [kdkec, setKdkec] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort | null>(null);
  const [data, setData] = useState<TabulasiProgres | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [mengekspor, setMengekspor] = useState(false);
  const [galatEkspor, setGalatEkspor] = useState<string | null>(null);

  const muat = useCallback(
    async (isyarat: AbortSignal) => {
      setMemuat(true);
      setGalat(null);
      setData(null);
      const parameter = new URLSearchParams({
        tingkat,
        dasar: "tugas",
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
    [kdprov, kdkab, kdkec, tingkat],
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

  const terurut = useMemo(() => {
    const hasil = [...daftarBaris];
    if (!sort) {
      return hasil;
    }
    hasil.sort((a, b) => {
      const kiri = nilaiSort(a, sort.kolom);
      const kanan = nilaiSort(b, sort.kolom);
      const banding =
        typeof kiri === "number" && typeof kanan === "number"
          ? kiri - kanan
          : String(kiri).localeCompare(String(kanan), "id-ID", {
              numeric: true,
              sensitivity: "base",
            });
      if (banding === 0) {
        return (a.kode ?? "").localeCompare(b.kode ?? "", "id-ID", {
          numeric: true,
        });
      }
      return sort.arah === "asc" ? banding : -banding;
    });
    return hasil;
  }, [daftarBaris, sort]);

  function gantiSort(kolom: KolomSort) {
    setSort((lama) => {
      if (!lama || lama.kolom !== kolom) {
        return { kolom, arah: "asc" };
      }
      return { kolom, arah: lama.arah === "asc" ? "desc" : "asc" };
    });
  }

  const total = useMemo(() => {
    return terurut.reduce(
      (jumlah, baris) => ({
        jumlah: jumlah.jumlah + baris.jumlah,
        target: jumlah.target + baris.target,
        selesai: jumlah.selesai + baris.selesai,
        sisa: jumlah.sisa + baris.sisa,
      }),
      { jumlah: 0, target: 0, selesai: 0, sisa: 0 },
    );
  }, [terurut]);

  const persenTotal =
    total.target > 0 ? (total.selesai / total.target) * 100 : null;

  function bukaBaris(baris: TabulasiProgresBaris) {
    if (!baris.kode || tingkat === "desa") {
      return;
    }
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

  async function eksporXlsx() {
    if (terurut.length === 0 || mengekspor) {
      return;
    }

    setMengekspor(true);
    setGalatEkspor(null);

    try {
      const { default: writeXlsxFile } = await import(
        "write-excel-file/browser"
      );
      const garis = {
        borderColor: "#d5dde3",
        borderStyle: "thin" as const,
      };
      const kepala = {
        ...garis,
        backgroundColor: "#eef3f6",
        fontWeight: "bold" as const,
        align: "center" as const,
      };
      const kiri = { ...garis, align: "left" as const };
      const kanan = { ...garis, align: "right" as const };

      const wilayah =
        tingkat === "kabupaten"
          ? (data?.nmprov ?? `Provinsi ${kdprov}`)
          : tingkat === "kecamatan"
            ? (namaKabTampil ?? kdprov)
            : (data?.nmkec ?? namaKabTampil ?? kdprov);
      const infoTarget = data?.target
        ? `Target: A ke-${data.target.nomor_urut ?? "-"} (${formatTanggal(data.target.tanggal_data)})`
        : "Target belum tersedia";
      const isi: SheetData = [
        [
          {
            value: `${judulTabel} — ${wilayah}`,
            fontWeight: "bold",
            fontSize: 14,
            columnSpan: 9,
          },
        ],
        [
          {
            value: infoTarget,
            fontSize: 10,
            textColor: "#5c6672",
            columnSpan: 9,
          },
        ],
        [],
        [
          { value: "Kode", ...kepala },
          { value: "Wilayah", ...kepala },
          { value: "Jumlah titik", ...kepala },
          { value: "Target", ...kepala },
          { value: "Selesai", ...kepala },
          { value: "Sisa", ...kepala },
          { value: "Penyelesaian", ...kepala },
          { value: "Pengunggah terakhir", ...kepala },
          { value: "Status", ...kepala },
        ],
      ];

      for (const baris of terurut) {
        const nama =
          baris.level === "kabupaten"
            ? namaKabupatenTampil(baris.kode ?? "", baris.nama)
            : baris.nama;
        isi.push([
          { value: baris.kode ?? "-", ...kiri },
          { value: nama ?? baris.kode ?? "-", ...kiri },
          { value: baris.jumlah, ...kanan },
          { value: baris.target, ...kanan },
          { value: baris.selesai, ...kanan },
          { value: baris.sisa, ...kanan },
          {
            value: baris.persen == null ? "-" : baris.persen / 100,
            ...kanan,
            ...(baris.persen == null ? {} : { format: "0.0%" }),
          },
          { value: baris.pengunggah ?? "-", ...kiri },
          {
            value: labelStatus(baris),
            ...kiri,
          },
        ]);
      }

      isi.push([
        { value: "Total", ...kiri, fontWeight: "bold" },
        { value: `${terurut.length} wilayah`, ...kiri, fontWeight: "bold" },
        { value: total.jumlah, ...kanan, fontWeight: "bold" },
        { value: total.target, ...kanan, fontWeight: "bold" },
        { value: total.selesai, ...kanan, fontWeight: "bold" },
        { value: total.sisa, ...kanan, fontWeight: "bold" },
        {
          value: persenTotal == null ? "-" : persenTotal / 100,
          ...kanan,
          fontWeight: "bold",
          ...(persenTotal == null ? {} : { format: "0.0%" }),
        },
        { value: "", ...kiri },
        { value: "", ...kiri },
      ]);

      const kodeBerkas =
        tingkat === "desa"
          ? (kdkec ?? kdkab ?? kdprov)
          : (kdkab ?? kdprov);
      const namaBerkas = `progres_edit_titik_${tingkat}_${kodeBerkas}`
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "");

      await writeXlsxFile(isi, {
        columns: [
          { width: 10 },
          { width: 28 },
          { width: 15 },
          { width: 12 },
          { width: 12 },
          { width: 10 },
          { width: 16 },
          { width: 22 },
          { width: 34 },
        ],
        sheet: "Tabulasi",
      }).toFile(`${namaBerkas}.xlsx`);
    } catch (kesalahan) {
      if (!adalahBatal(kesalahan)) {
        setGalatEkspor(pesanKesalahan(kesalahan));
      }
    } finally {
      setMengekspor(false);
    }
  }

  return (
    <section className="space-y-field">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
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

        <div className="flex flex-wrap items-center gap-1.5">
          {kontrol}
          {bisaKembali ? (
            <TombolAksi
              varian="sekunder"
              className="min-h-8 px-tombol"
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
        </div>
      </div>

      <div className="rounded-xl border border-line bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line px-3 py-2 sm:px-3">
          <div>
            <h2 className="font-display text-base font-semibold tracking-tight text-ink">
              {judulTabel}
            </h2>
            {tingkat !== "kabupaten" ? (
              <p className="mt-1 text-[11px] text-muted">
                Target dari Proses A terbaru, sisa dari Proses B terakhir.
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {data && (data.target || data.pembanding) ? (
              <p className="text-[11px] text-muted">
                {data.target
                  ? `Target: A ke-${data.target.nomor_urut ?? "-"} (${formatTanggal(data.target.tanggal_data)})`
                  : "Target belum tersedia"}
                {data.pembanding
                  ? ` · B ke-${data.pembanding.nomor_urut ?? "-"} (${formatTanggal(data.pembanding.tanggal_data)})`
                  : " · Belum ada Proses B"}
              </p>
            ) : null}
            <TombolAksi
              varian="sekunder"
              className="min-h-8 px-2.5 text-xs"
              onClick={() => void eksporXlsx()}
              disabled={memuat || terurut.length === 0 || mengekspor}
              aria-label="Ekspor tabel ke XLSX"
              title="Ekspor tabel ke XLSX"
            >
              {mengekspor ? "Menyiapkan..." : "XLSX"}
            </TombolAksi>
          </div>
        </div>

        {galatEkspor ? (
          <p className="border-b border-line px-3 py-1 text-xs text-danger" role="alert">
            {galatEkspor}
          </p>
        ) : null}

        {galat ? (
          <div className="m-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink">
            <p>{galat}</p>
            <TombolAksi
              varian="sekunder"
              className="mt-1 min-h-9 px-tombol"
              onClick={() => {
                const kendali = new AbortController();
                void muat(kendali.signal);
              }}
            >
              Coba lagi
            </TombolAksi>
          </div>
        ) : memuat && data == null ? (
          <div className="space-y-field p-kartu" aria-label="Memuat tabulasi">
            {[0, 1, 2, 3, 4].map((baris) => (
              <div
                key={baris}
                className="h-11 animate-pulse rounded-lg bg-paper"
              />
            ))}
          </div>
        ) : terurut.length === 0 ? (
          <div className="p-kartu">
            <EmptyState judul={`Belum ada data ${judulTabel.toLocaleLowerCase("id-ID")}`}>
              Belum ada run Proses A yang targetnya bisa dibaca untuk tingkat ini.
            </EmptyState>
          </div>
        ) : tampilan === "grafik" ? (
          <GrafikBatang baris={terurut} tingkat={tingkat} onBuka={bukaBaris} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[60rem] border-collapse text-[13px]">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted">
                  <SelSort
                    label="Kode"
                    kolom="kode"
                    sort={sort}
                    onSort={gantiSort}
                    rata="left"
                    kiri
                    className="sm:px-3"
                  />
                  <SelSort
                    label="Wilayah"
                    kolom="wilayah"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Jumlah titik"
                    kolom="jumlah"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Target"
                    kolom="target"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Selesai"
                    kolom="selesai"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Sisa"
                    kolom="sisa"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Penyelesaian"
                    kolom="persen"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Pengunggah terakhir"
                    kolom="pengunggah"
                    sort={sort}
                    onSort={gantiSort}
                    className="sm:px-3"
                  />
                  <SelSort
                    label="Status"
                    kolom="status"
                    sort={sort}
                    onSort={gantiSort}
                    className="sm:px-3"
                  />
                </tr>
              </thead>
              <tbody>
                {terurut.map((baris) => {
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
                      <td className="sticky left-0 z-10 bg-surface px-3 py-1 font-mono text-[11px] text-muted sm:px-3">
                        {baris.kode ?? "-"}
                      </td>
                      <td className="px-3 py-1 font-medium text-ink">
                        <span className="flex items-center gap-2">
                          {bisaDibuka ? <Chevron /> : <span className="h-4 w-4 shrink-0" />}
                          <span className="min-w-0 block truncate">
                            {nama ?? baris.kode ?? "-"}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-1 text-right tabular-nums text-muted">
                        {formatAngka(baris.jumlah)}
                      </td>
                      <td className="px-3 py-1 text-right font-semibold tabular-nums text-ink">
                        {formatAngka(baris.target)}
                      </td>
                      <td className="px-3 py-1 text-right tabular-nums text-success">
                        {formatAngka(baris.selesai)}
                      </td>
                      <td className="px-3 py-1 text-right tabular-nums text-accent-strong">
                        {formatAngka(baris.sisa)}
                      </td>
                      <td className="px-3 py-1 text-right tabular-nums text-ink">
                        <BarPenyelesaian nilai={baris.persen} />
                      </td>
                      <td className="max-w-[14rem] px-3 py-1 text-muted sm:px-3">
                        <span
                          className="block truncate"
                          title={baris.pengunggah ?? ""}
                        >
                          {baris.pengunggah ?? "-"}
                        </span>
                      </td>
                      <td className="px-3 py-1 text-right sm:px-3">
                        <span
                          className={`inline-flex min-h-6 items-center whitespace-nowrap rounded-full border px-2 text-xs font-semibold ${gayaStatus(baris.status)}`}
                        >
                          {labelStatus(baris)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t border-line bg-paper/70 font-semibold text-ink">
                  <td className="sticky left-0 z-10 bg-paper/95 px-3 py-1 sm:px-3">
                    Total
                  </td>
                  <td className="px-3 py-1">{terurut.length} wilayah</td>
                  <td className="px-3 py-1 text-right tabular-nums">{formatAngka(total.jumlah)}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{formatAngka(total.target)}</td>
                  <td className="px-3 py-1 text-right tabular-nums text-success">
                    {formatAngka(total.selesai)}
                  </td>
                  <td className="px-3 py-1 text-right tabular-nums text-accent-strong">
                    {formatAngka(total.sisa)}
                  </td>
                  <td className="px-3 py-1 text-right tabular-nums">
                    {formatPersen(persenTotal)}
                  </td>
                  <td className="px-3 py-1 sm:px-3" />
                  <td className="px-3 py-1 sm:px-3" />
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        <p className="border-t border-line px-3 py-2 text-xs leading-5 text-muted sm:px-3">
          Klik baris kabupaten/kota untuk melihat kecamatan, lalu klik kecamatan
          untuk melihat desa/kelurahan. Selesai dihitung per SubSLS; wilayah yang
          belum ada di Proses B tetap dihitung belum selesai. Nilai dapat turun
          bila muncul flag baru.
        </p>
      </div>
    </section>
  );
}
