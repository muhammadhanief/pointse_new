"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
  unduhBerkas,
} from "@/lib/api/klien";
import type { Run, ValidasiRingkasan, ValidasiRingkasanBaris } from "@/lib/api/types";
import { PERAN_ADMIN_PROVINSI, kodeWilayah } from "@/lib/auth/peran";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";
import { daftarKabupaten, namaKabupaten } from "@/lib/wilayah/kabupaten";

import { BadgeStatus } from "./badge-status";
import { DetailJob } from "./detail-job";

const INTERVAL_MUAT_ULANG = 15000;

const JENIS_TOPOLOGI = new Set([
  "geom_gap",
  "geom_overlap",
  "geom_duplikat",
  "geom_invalid",
]);

function labelJenis(jenis: string): string {
  switch (jenis) {
    case "tidak_di_peta":
      return "Tidak di peta";
    case "tidak_di_master":
      return "Tidak di master";
    case "ganda":
      return "Ganda";
    case "nama_beda":
      return "Nama beda";
    case "tidak_konsisten":
      return "Tidak konsisten";
    case "geom_gap":
      return "Gap";
    case "geom_overlap":
      return "Overlap";
    case "geom_duplikat":
      return "Duplikat";
    case "geom_invalid":
      return "Invalid";
    default:
      return jenis;
  }
}

export function ProgresValidasi({
  kdprov,
  kdkab,
  peran,
}: {
  kdprov: string;
  kdkab: string | null;
  peran: string;
}) {
  const [baris, setBaris] = useState<ValidasiRingkasanBaris[]>([]);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [sibuk, setSibuk] = useState<number | null>(null);
  const [diperbarui, setDiperbarui] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("semua");
  const [detail, setDetail] = useState<Run | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async (senyap = false) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    if (!senyap) {
      setMemuat(true);
      setGalat(null);
    }

    try {
      const hasil = await ambilJson<ValidasiRingkasan>(
        "/validasi-sls/ringkasan",
        { signal: controller.signal },
      );
      if (controller.signal.aborted) {
        return;
      }
      setBaris(hasil.baris);
      setGalat(null);
      setDiperbarui(formatWaktu(new Date().toISOString()));
    } catch (kesalahan) {
      if (!adalahBatal(kesalahan)) {
        setGalat(pesanKesalahan(kesalahan));
      }
    } finally {
      if (!controller.signal.aborted) {
        setMemuat(false);
      }
    }
  }, []);

  useEffect(() => {
    void muat();

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void muat(true);
      }
    }, INTERVAL_MUAT_ULANG);

    function saatTerlihat() {
      if (document.visibilityState === "visible") {
        void muat(true);
      }
    }

    document.addEventListener("visibilitychange", saatTerlihat);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", saatTerlihat);
      controllerRef.current?.abort();
    };
  }, [muat]);

  async function unduh(runId: number, kode: string) {
    setSibuk(runId);
    try {
      await unduhBerkas(
        `/runs/${runId}/ekspor/unmatch-v.xlsx`,
        `${kode}_validasi_sls_2026_s1.xlsx`,
      );
    } catch {
      // Biarkan tombol kembali normal; unduhan detail ada di riwayat.
    } finally {
      setSibuk(null);
    }
  }

  async function bukaDetail(runId: number) {
    try {
      const run = await ambilJson<Run>(`/runs/${runId}`);
      setDetail(run);
    } catch {
      // Biarkan tetap tertutup; detail lengkap ada di riwayat.
    }
  }

  const tampilSemua = (() => {
    const peta = new Map(baris.map((satu) => [satu.kdkab, satu]));
    // Kabupaten/kota yang belum pernah mengunggah tetap dibuatkan baris
    // (status "Belum unggah") supaya terpantau.
    const daftar =
      peran === PERAN_ADMIN_PROVINSI
        ? daftarKabupaten(kdprov)
        : [{ kode: kodeWilayah(kdprov, kdkab), nama: "" }];
    const gabung = daftar.map((wilayah) => {
      const ada = peta.get(wilayah.kode);
      if (ada) {
        return ada;
      }
      const kosong: ValidasiRingkasanBaris = {
        kdprov,
        kdkab: wilayah.kode,
        run_id: null,
        status: "belum_unggah",
        tanggal_data: "",
        semester: null,
        selesai_pada: null,
        petugas: null,
        total: 0,
        per_jenis: {},
        target: null,
        selesai: null,
        sisa: null,
      };
      return kosong;
    });
    // Provinsi di luar Jateng tidak punya daftar statis: tampilkan apa adanya.
    if (gabung.length === 0) {
      return baris;
    }
    return gabung;
  })();

  const tampil =
    filterStatus === "semua"
      ? tampilSemua
      : filterStatus === "berjalan"
        ? tampilSemua.filter(
            (satu) => satu.status === "menunggu" || satu.status === "jalan",
          )
        : tampilSemua.filter((satu) => satu.status === filterStatus);
  const sudahUnggah = tampilSemua.filter((satu) => satu.run_id !== null).length;

  return (
    <Panel
      judul="Progres validasi per kabupaten/kota"
      deskripsi="Run validasi (tipe V) terakhir tiap kabupaten/kota beserta temuan yang belum diperbaiki. Diperbarui otomatis."
    >
      <div className="mt-3 flex flex-col gap-field sm:flex-row sm:items-end sm:justify-between">
        <p className="text-sm text-muted" aria-live="polite">
          {tampil.length} kabupaten/kota
          {filterStatus !== "semua"
            ? " sesuai filter"
            : ` (${sudahUnggah} sudah mengunggah)`}
          {diperbarui ? `. Diperbarui ${diperbarui}` : ""}.
        </p>
        <div className="flex flex-wrap items-center gap-field">
          <label className="text-sm text-muted">
            Status{" "}
            <select
              value={filterStatus}
              onChange={(event) => setFilterStatus(event.target.value)}
              className="min-h-9 rounded-lg border border-line-strong bg-surface px-2 py-1 text-sm text-ink"
            >
              <option value="semua">Semua</option>
              <option value="sukses">Lolos</option>
              <option value="belum_clean">Belum clean</option>
              <option value="gagal">Gagal</option>
              <option value="belum_unggah">Belum unggah</option>
              <option value="berjalan">Diproses</option>
            </select>
          </label>
          <TombolAksi varian="sekunder" onClick={() => void muat()}>
            {memuat ? "Memuat..." : "Muat ulang"}
          </TombolAksi>
        </div>
      </div>

      {galat ? (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
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

      {memuat && baris.length === 0 ? (
        <p className="mt-3 text-sm leading-normal text-muted" role="status">
          Memuat progres validasi...
        </p>
      ) : null}

      {!memuat && !galat && baris.length === 0 ? (
        <EmptyState judul="Belum ada unggahan validasi">
          Unggah peta SLS/SubSLS 2026 Semester 1 lewat halaman validasi untuk
          mulai memantau progres kabupaten/kota.
        </EmptyState>
      ) : null}

      {!memuat && !galat && baris.length > 0 && tampil.length === 0 ? (
        <EmptyState judul="Tidak ada baris sesuai filter">
          Ubah saringan status atau pilih "Semua".
        </EmptyState>
      ) : null}

      {tampil.length > 0 ? (
        <div className="relative mt-3 max-h-[70vh] overflow-auto overscroll-contain">
          <table className="w-full min-w-[74rem] border-collapse text-[13px]">
            <caption className="sr-only">
              Progres validasi SLS 2026 Semester 1 per kabupaten/kota
            </caption>
            <thead>
              <tr className="border-b border-line/60 text-left text-[11px] uppercase tracking-wide text-muted">
                <th
                  scope="col"
                  rowSpan={2}
                  className="sticky top-0 z-10 bg-paper px-3 py-2 align-bottom font-semibold"
                >
                  Kode
                </th>
                <th
                  scope="col"
                  rowSpan={2}
                  className="sticky top-0 z-10 bg-paper px-3 py-2 align-bottom font-semibold"
                >
                  Kabupaten/kota
                </th>
                <th
                  scope="col"
                  rowSpan={2}
                  className="sticky top-0 z-10 bg-paper px-3 py-2 align-bottom font-semibold"
                >
                  Status
                </th>
                <th
                  scope="col"
                  rowSpan={2}
                  className="sticky top-0 z-10 bg-paper px-3 py-2 align-bottom font-semibold"
                >
                  Run terakhir
                </th>
                <th
                  scope="colgroup"
                  colSpan={3}
                  className="sticky top-0 z-10 border-x border-line/60 bg-paper px-3 py-1.5 text-center font-semibold"
                >
                  Kecocokan Master MFD
                </th>
                <th
                  scope="col"
                  rowSpan={2}
                  className="sticky top-0 z-10 bg-paper px-3 py-2 align-bottom font-semibold"
                >
                  Temuan Atribut
                </th>
                <th
                  scope="col"
                  rowSpan={2}
                  className="sticky top-0 z-10 bg-paper px-3 py-2 align-bottom font-semibold"
                >
                  Temuan Topologi (QGIS)
                </th>
                <th
                  scope="col"
                  rowSpan={2}
                  className="sticky top-0 z-10 bg-paper px-3 py-2 text-right align-bottom font-semibold"
                >
                  Total Temuan
                </th>
                <th
                  scope="col"
                  rowSpan={2}
                  className="sticky top-0 z-10 bg-paper px-3 py-2 text-right align-bottom font-semibold"
                >
                  Aksi
                </th>
              </tr>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-muted">
                <th
                  scope="col"
                  className="sticky top-7 z-10 border-l border-line/60 bg-paper px-2.5 py-1.5 text-right font-semibold"
                  title="Jumlah pasangan SLS/SubSLS pada Master MFD 2026 S1"
                >
                  Master
                </th>
                <th
                  scope="col"
                  className="sticky top-7 z-10 bg-paper px-2.5 py-1.5 text-right font-semibold"
                  title="Jumlah baris poligon SLS/SubSLS pada berkas peta yang diunggah"
                >
                  Peta
                </th>
                <th
                  scope="col"
                  className="sticky top-7 z-10 border-r border-line/60 bg-paper px-2.5 py-1.5 text-right font-semibold"
                  title="Jumlah pasangan Master MFD yang cocok bersih di peta"
                >
                  Cocok
                </th>
              </tr>
            </thead>
            <tbody>
              {tampil.map((satu) => {
                const kode = kodeWilayah(satu.kdprov, satu.kdkab);
                const runId = satu.run_id;
                const belumUnggah = runId === null;
                const entriAtribut = Object.entries(satu.per_jenis).filter(
                  ([jenis, jumlah]) => !JENIS_TOPOLOGI.has(jenis) && jumlah > 0,
                );
                const entriTopologi = Object.entries(satu.per_jenis).filter(
                  ([jenis, jumlah]) => JENIS_TOPOLOGI.has(jenis) && jumlah > 0,
                );
                const totalAtribut = entriAtribut.reduce(
                  (akum, [, jumlah]) => akum + jumlah,
                  0,
                );
                const totalTopologi = entriTopologi.reduce(
                  (akum, [, jumlah]) => akum + jumlah,
                  0,
                );
                const jumlahPeta =
                  satu.target !== null && satu.selesai !== null
                    ? satu.target -
                      (satu.per_jenis.tidak_di_peta ?? 0) +
                      (satu.per_jenis.tidak_di_master ?? 0) +
                      (satu.per_jenis.ganda ?? 0) +
                      (satu.per_jenis.tidak_konsisten ?? 0)
                    : null;
                const petaKlop =
                  jumlahPeta !== null &&
                  satu.target !== null &&
                  jumlahPeta === satu.target &&
                  totalAtribut === 0;
                const cocokKlop =
                  satu.selesai !== null &&
                  satu.target !== null &&
                  satu.selesai === satu.target &&
                  totalAtribut === 0;
                return (
                  <tr
                    key={`${satu.kdprov}-${satu.kdkab}`}
                    className="border-b border-line/70 last:border-0 hover:bg-brand-soft/20"
                  >
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums text-ink">
                      {kode}
                    </td>
                    <td className="px-3 py-2">
                      <p className="font-medium text-ink">
                        {namaKabupaten(satu.kdprov, satu.kdkab)?.replace(
                          /^kabupaten\s+/i,
                          "",
                        ) ?? "-"}
                      </p>
                    </td>
                    <td className="px-3 py-2">
                      <BadgeStatus status={satu.status} rata="start" />
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                      {belumUnggah ? (
                        "—"
                      ) : (
                        <>
                          <span className="text-ink">
                            {satu.selesai_pada
                              ? formatWaktu(satu.selesai_pada)
                              : formatTanggal(satu.tanggal_data)}
                          </span>
                          <span className="block text-xs text-muted">
                            {satu.petugas ?? "—"}
                            {satu.semester ? ` · ${satu.semester}` : ""}
                          </span>
                        </>
                      )}
                    </td>
                    <td className="border-l border-line/50 px-2.5 py-2 text-right tabular-nums text-muted">
                      {satu.target !== null ? formatAngka(satu.target) : "—"}
                    </td>
                    <td className="px-2.5 py-2 text-right tabular-nums font-medium">
                      {jumlahPeta === null ? (
                        <span className="font-normal text-muted">—</span>
                      ) : petaKlop ? (
                        <span className="text-success">
                          {formatAngka(jumlahPeta)}
                        </span>
                      ) : (
                        <span className="text-danger">
                          {formatAngka(jumlahPeta)}
                        </span>
                      )}
                    </td>
                    <td className="border-r border-line/50 px-2.5 py-2 text-right tabular-nums font-semibold">
                      {satu.selesai === null ? (
                        <span className="font-normal text-muted">—</span>
                      ) : cocokKlop ? (
                        <span className="text-success">
                          {formatAngka(satu.selesai)}
                        </span>
                      ) : (
                        <span className="text-warning">
                          {formatAngka(satu.selesai)}
                        </span>
                      )}
                    </td>
                    <td className="max-w-[16rem] px-3 py-2 text-xs leading-5">
                      {belumUnggah ? (
                        <span className="text-muted">—</span>
                      ) : totalAtribut === 0 ? (
                        <span className="font-medium text-success">
                          0 (Clean)
                        </span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {entriAtribut.map(([jenis, jumlah]) => (
                            <span
                              key={jenis}
                              className="inline-flex items-center rounded border border-danger/25 bg-danger-soft/50 px-1.5 py-0.5 text-[11px] font-medium text-ink tabular-nums"
                            >
                              {labelJenis(jenis)}:{" "}
                              <strong className="ml-1 text-danger">
                                {formatAngka(jumlah)}
                              </strong>
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="max-w-[16rem] px-3 py-2 text-xs leading-5">
                      {belumUnggah ? (
                        <span className="text-muted">—</span>
                      ) : totalTopologi === 0 ? (
                        <span className="font-medium text-success">
                          0 (Clean)
                        </span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {entriTopologi.map(([jenis, jumlah]) => (
                            <span
                              key={jenis}
                              className="inline-flex items-center rounded border border-warning/40 bg-warning-soft/50 px-1.5 py-0.5 text-[11px] font-medium text-ink tabular-nums"
                            >
                              {labelJenis(jenis)}:{" "}
                              <strong className="ml-1 text-ink">
                                {formatAngka(jumlah)}
                              </strong>
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-semibold">
                      {belumUnggah ? (
                        <span className="text-muted">—</span>
                      ) : (
                        <>
                          <span
                            className={
                              satu.total > 0 ? "text-danger" : "text-success"
                            }
                          >
                            {formatAngka(satu.total)}
                          </span>{" "}
                          <span className="block text-[11px] font-normal text-muted">
                            {satu.total > 0 ? "Perlu tindakan" : "Beres"}
                          </span>
                        </>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      {belumUnggah ? (
                        <span className="text-xs text-muted">—</span>
                      ) : (
                        <>
                          <TombolAksi
                            varian="sekunder"
                            className="min-h-8 px-3 text-xs"
                            onClick={() => void bukaDetail(runId)}
                          >
                            Detail
                          </TombolAksi>{" "}
                          <TombolAksi
                            varian="sekunder"
                            className="min-h-8 px-3 text-xs"
                            onClick={() => void unduh(runId, kode)}
                            disabled={sibuk !== null || satu.total === 0}
                            title={
                              satu.total === 0
                                ? "Tidak ada temuan untuk diunduh"
                                : "Unduh daftar temuan sebagai Excel"
                            }
                          >
                            {sibuk === runId
                              ? "Menyiapkan..."
                              : "Unduh Excel"}
                          </TombolAksi>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <DetailJob run={detail} onTutup={() => setDetail(null)} />
    </Panel>
  );
}
