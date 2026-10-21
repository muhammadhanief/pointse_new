"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  BadgeStatus,
  Panel,
  TombolAksi,
} from "@/components/dashboard/ui";
import { Modal } from "@/components/dashboard/modal";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
} from "@/lib/api/klien";
import type { DaftarMaster, MasterGeotag } from "@/lib/api/types";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";
import {
  daftarKabupaten,
  namaKabupatenTampil,
} from "@/lib/wilayah/kabupaten";

import { DetailMaster } from "./detail-master";
import { FormMaster } from "./form-master";

type Detail = { kdkab: string; nama: string };
type KolomSort =
  | "kode"
  | "wilayah"
  | "status"
  | "versi"
  | "tanggal"
  | "diunggah"
  | "baris";
type ArahSort = "asc" | "desc";
type Sort = { kolom: KolomSort; arah: ArahSort };
type BarisMaster = { kode: string; nama: string; latest?: MasterGeotag };

function nilaiSort(baris: BarisMaster, kolom: KolomSort): string | number {
  switch (kolom) {
    case "kode":
      return baris.kode;
    case "wilayah":
      return baris.nama;
    case "status":
      return baris.latest ? 1 : 0;
    case "versi":
      return baris.latest?.nomor_versi ?? -1;
    case "tanggal":
      return baris.latest?.tanggal_data ?? "";
    case "diunggah":
      return baris.latest?.created_at ?? "";
    case "baris":
      return baris.latest?.jumlah_baris ?? -1;
    default:
      return "";
  }
}

function SelSort({
  label,
  kolom,
  sort,
  onSort,
  rata = "left",
}: {
  label: string;
  kolom: KolomSort;
  sort: Sort | null;
  onSort: (kolom: KolomSort) => void;
  rata?: "left" | "right";
}) {
  const aktif = sort?.kolom === kolom;
  const arah = aktif ? sort.arah : null;
  const ariaSort: "none" | "ascending" | "descending" =
    arah === "asc" ? "ascending" : arah === "desc" ? "descending" : "none";

  return (
    <th
      scope="col"
      aria-sort={ariaSort}
      className={`sticky top-0 z-20 border-b border-line bg-paper px-3 py-2 font-semibold ${
        rata === "right" ? "text-right" : "text-left"
      }`}
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

export function MasterClient({ kdprov }: { kdprov: string }) {
  const [master, setMaster] = useState<MasterGeotag[]>([]);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [uploadTerbuka, setUploadTerbuka] = useState(false);
  const [kdkabUpload, setKdkabUpload] = useState<string | undefined>();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [sort, setSort] = useState<Sort | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setMemuat(true);
    setGalat(null);
    try {
      const hasil = await ambilJson<DaftarMaster>("/geotag-master?limit=500", {
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setMaster(hasil.baris);
      }
    } catch (galatAmbil) {
      if (!adalahBatal(galatAmbil)) {
        setGalat(pesanKesalahan(galatAmbil));
      }
    } finally {
      if (!controller.signal.aborted) {
        setMemuat(false);
      }
    }
  }, []);

  useEffect(() => {
    void muat();
    return () => controllerRef.current?.abort();
  }, [muat, refreshKey]);

  const terbaru = useMemo(() => {
    const peta = new Map<string, MasterGeotag>();
    for (const satu of master) {
      if (!peta.has(satu.kdkab)) {
        peta.set(satu.kdkab, satu);
      }
    }
    return peta;
  }, [master]);

  const kabupaten = useMemo(() => daftarKabupaten(kdprov), [kdprov]);
  const jumlahAda = kabupaten.filter((satu) => terbaru.has(satu.kode)).length;

  const barisTabel = useMemo<BarisMaster[]>(
    () =>
      kabupaten.map((satu) => ({
        kode: satu.kode,
        nama: (
          namaKabupatenTampil(satu.kode, satu.nama) ?? satu.nama
        ).toLocaleUpperCase("id-ID"),
        latest: terbaru.get(satu.kode),
      })),
    [kabupaten, terbaru],
  );

  const terurut = useMemo(() => {
    if (!sort) {
      return barisTabel;
    }

    return [...barisTabel].sort((kiri, kanan) => {
      const a = nilaiSort(kiri, sort.kolom);
      const b = nilaiSort(kanan, sort.kolom);
      let hasil =
        typeof a === "number" && typeof b === "number"
          ? a - b
          : String(a).localeCompare(String(b), "id-ID");

      if (hasil === 0) {
        hasil = kiri.kode.localeCompare(kanan.kode, "id-ID");
      }
      return sort.arah === "asc" ? hasil : -hasil;
    });
  }, [barisTabel, sort]);

  function gantiSort(kolom: KolomSort) {
    setSort((lama) => {
      if (lama?.kolom === kolom) {
        return { kolom, arah: lama.arah === "asc" ? "desc" : "asc" };
      }
      return {
        kolom,
        arah:
          kolom === "versi" ||
          kolom === "tanggal" ||
          kolom === "diunggah" ||
          kolom === "baris"
            ? "desc"
            : "asc",
      };
    });
  }

  function bukaUpload(kdkab?: string) {
    setDetail(null);
    setKdkabUpload(kdkab);
    setUploadTerbuka(true);
  }

  function selesaiUpload() {
    setUploadTerbuka(false);
    setKdkabUpload(undefined);
    setRefreshKey((nilai) => nilai + 1);
  }

  return (
    <div className="space-y-field">
      <Panel
        judul="Status master per kabupaten/kota"
        deskripsi="Semua kabupaten/kota di provinsi ditampilkan. Buka detail untuk melihat seluruh versi master."
      >
        <div className="mt-3 flex flex-wrap items-center justify-between gap-field">
          <p className="text-xs text-muted" role="status">
            {memuat
              ? "Memuat status master..."
              : `${jumlahAda} dari ${kabupaten.length} kabupaten/kota sudah punya master.`}
          </p>
          <div className="flex flex-wrap gap-field">
            <TombolAksi
              varian="sekunder"
              onClick={() => void muat()}
              disabled={memuat}
            >
              Muat ulang
            </TombolAksi>
            <TombolAksi onClick={() => bukaUpload()}>Unggah master</TombolAksi>
          </div>
        </div>

        {galat ? (
          <div
            role="alert"
            className="mt-3 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger"
          >
            <p>{galat}</p>
            <button
              type="button"
              onClick={() => void muat()}
              className="mt-1 min-h-9 rounded-lg border border-danger/30 bg-surface px-tombol text-sm font-semibold text-danger"
            >
              Coba lagi
            </button>
          </div>
        ) : null}

        {memuat && master.length === 0 ? (
          <p className="mt-3 text-sm text-muted" role="status">
            Memuat status master...
          </p>
        ) : null}

        {!memuat && !galat && kabupaten.length === 0 ? (
          <p className="mt-3 text-sm text-muted">
            Daftar kabupaten/kota untuk provinsi ini belum tersedia.
          </p>
        ) : null}

        {kabupaten.length > 0 && !(memuat && master.length === 0) ? (
          <div className="relative mt-3 max-h-[70vh] overflow-auto overscroll-contain">
            <table className="w-full min-w-[52rem] border-collapse text-[13px]">
              <caption className="sr-only">
                Status master geotag per kabupaten/kota.
              </caption>
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted">
                  <SelSort
                    label="Kode"
                    kolom="kode"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Kabupaten/kota"
                    kolom="wilayah"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Status"
                    kolom="status"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Versi terbaru"
                    kolom="versi"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Tanggal data"
                    kolom="tanggal"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Diunggah"
                    kolom="diunggah"
                    sort={sort}
                    onSort={gantiSort}
                  />
                  <SelSort
                    label="Baris"
                    kolom="baris"
                    sort={sort}
                    onSort={gantiSort}
                    rata="right"
                  />
                  <th className="sticky top-0 z-20 border-b border-line bg-paper px-3 py-2 text-right font-semibold">
                    Aksi
                  </th>
                </tr>
              </thead>
              <tbody>
                {terurut.map((satu) => {
                  const latest = satu.latest;
                  const nama = satu.nama;
                  return (
                    <tr
                      key={satu.kode}
                      className="border-b border-line/70 last:border-0 hover:bg-brand-soft/20"
                    >
                      <td className="px-3 py-2 tabular-nums text-muted">
                        {satu.kode}
                      </td>
                      <td className="px-3 py-2 font-medium text-ink">{nama}</td>
                      <td className="px-3 py-2">
                        <BadgeStatus status={latest ? "ada" : "belum"} />
                      </td>
                      <td className="px-3 py-2 text-muted">
                        {latest?.nomor_versi
                          ? `ke-${latest.nomor_versi}`
                          : "-"}
                      </td>
                      <td className="px-3 py-2 text-muted">
                        {latest ? formatTanggal(latest.tanggal_data) : "-"}
                      </td>
                      <td className="px-3 py-2 text-muted">
                        {latest ? formatWaktu(latest.created_at) : "-"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-muted">
                        {latest ? formatAngka(latest.jumlah_baris) : "-"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <TombolAksi
                          varian="sekunder"
                          className="min-h-8 px-3 text-xs"
                          onClick={() => setDetail({ kdkab: satu.kode, nama })}
                        >
                          Detail
                        </TombolAksi>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>

      <Modal
        terbuka={uploadTerbuka}
        judul="Unggah master geotag"
        onTutup={() => setUploadTerbuka(false)}
      >
        {uploadTerbuka ? (
          <FormMaster
            kdprov={kdprov}
            kdkabAwal={kdkabUpload}
            onSelesai={selesaiUpload}
          />
        ) : null}
      </Modal>

      <Modal
        terbuka={detail !== null}
        judul={detail ? `Master ${detail.nama}` : "Detail master"}
        onTutup={() => setDetail(null)}
        ukuran="lg"
      >
        {detail ? (
          <DetailMaster
            kdkab={detail.kdkab}
            refreshKey={refreshKey}
            onUnggah={() => bukaUpload(detail.kdkab)}
          />
        ) : null}
      </Modal>
    </div>
  );
}
