"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { TombolAksi } from "@/components/dashboard/ui";
import { IkonTutup } from "@/components/dashboard/icons";
import { ambilJson, pesanKesalahan } from "@/lib/api/klien";
import type {
  ValidasiRingkasanBaris,
  ValidasiUnmatch,
  ValidasiUnmatchBaris,
} from "@/lib/api/types";
import { PERAN_ADMIN_PROVINSI, kodeWilayah } from "@/lib/auth/peran";
import { formatAngka, formatWaktu } from "@/lib/format";
import { namaKabupaten } from "@/lib/wilayah/kabupaten";

import { BadgeStatus } from "./badge-status";

const UKURAN_HALAMAN = 100;

const PILIHAN_JENIS: { kode: string; label: string }[] = [
  { kode: "", label: "Semua jenis temuan" },
  { kode: "tidak_di_peta", label: "Tidak di peta" },
  { kode: "tidak_di_master", label: "Tidak di master" },
  { kode: "ganda", label: "Ganda di peta" },
  { kode: "nama_beda", label: "Nama SLS berbeda" },
  { kode: "tidak_konsisten", label: "Kode tidak konsisten" },
  { kode: "geom_gap", label: "Topologi: Gap (celah)" },
  { kode: "geom_overlap", label: "Topologi: Overlap (tumpang tindih)" },
  { kode: "geom_duplikat", label: "Topologi: Duplikat geometri" },
  { kode: "geom_invalid", label: "Topologi: Geometri tidak valid" },
];

const PILIHAN_STATUS_KONFIRMASI: { kode: string; label: string }[] = [
  { kode: "", label: "Semua status konfirmasi" },
  { kode: "belum", label: "Belum dikonfirmasi" },
  { kode: "akan_diperbaiki", label: "Akan Diperbaiki" },
  { kode: "sesuai_kenyataan", label: "Sesuai Kondisi Kenyataan (Semua)" },
  { kode: "menunggu_persetujuan", label: "Menunggu Persetujuan Provinsi" },
  { kode: "disetujui", label: "Disetujui Provinsi" },
  { kode: "ditolak", label: "Ditolak Provinsi" },
];

function labelJenisSingkat(jenis: string): string {
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

export function DialogKonfirmasiValidasi({
  sasaran,
  jenisAwal = "",
  peran,
  onTutup,
  onBerubah,
}: {
  sasaran: ValidasiRingkasanBaris | null;
  jenisAwal?: string;
  peran: string;
  onTutup: () => void;
  onBerubah: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const inputCatatanRef = useRef<HTMLTextAreaElement | null>(null);

  const [jenis, setJenis] = useState<string>(jenisAwal);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [halaman, setHalaman] = useState(0);
  const [baris, setBaris] = useState<ValidasiUnmatchBaris[]>([]);
  const [total, setTotal] = useState(0);
  const [memuat, setMemuat] = useState(false);
  const [galat, setGalat] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [terpilih, setTerpilih] = useState<number[]>([]);
  const [statusKonfirmasi, setStatusKonfirmasi] = useState<
    "akan_diperbaiki" | "sesuai_kenyataan"
  >("akan_diperbaiki");
  const [catatanKonfirmasi, setCatatanKonfirmasi] = useState("");
  const [catatanProvinsi, setCatatanProvinsi] = useState("");
  const [menyimpan, setMenyimpan] = useState(false);

  const adalahAdminProvinsi = peran === PERAN_ADMIN_PROVINSI;
  const runId = sasaran?.run_id ?? null;

  useEffect(() => {
    setJenis(jenisAwal);
    setStatusFilter("");
    setHalaman(0);
    setTerpilih([]);
    setCatatanKonfirmasi("");
    setCatatanProvinsi("");
    setGalat(null);
    setInfo(null);
  }, [runId, jenisAwal]);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) {
      return;
    }
    if (sasaran && runId !== null) {
      if (!el.open) {
        el.showModal();
      }
    } else if (el.open) {
      el.close();
    }
  }, [sasaran, runId]);

  const muatDaftar = useCallback(async () => {
    if (runId === null) {
      return;
    }
    setMemuat(true);
    setGalat(null);
    try {
      const param = new URLSearchParams({
        limit: String(UKURAN_HALAMAN),
        offset: String(halaman * UKURAN_HALAMAN),
      });
      if (jenis) {
        param.set("jenis", jenis);
      }
      if (statusFilter) {
        param.set("status_konfirmasi", statusFilter);
      }
      const hasil = await ambilJson<ValidasiUnmatch>(
        `/runs/${runId}/validasi-sls/unmatch?${param.toString()}`,
      );
      setBaris(hasil.baris);
      setTotal(hasil.total);
      setTerpilih((lama) =>
        lama.filter((id) => hasil.baris.some((satu) => satu.id === id)),
      );
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setMemuat(false);
    }
  }, [runId, jenis, statusFilter, halaman]);

  useEffect(() => {
    if (runId !== null) {
      void muatDaftar();
    }
  }, [runId, muatDaftar]);

  function toggleSatu(id: number) {
    setTerpilih((lama) =>
      lama.includes(id) ? lama.filter((x) => x !== id) : [...lama, id],
    );
  }

  function toggleSemuaHalaman() {
    const idsHalaman = baris
      .map((satu) => satu.id)
      .filter((id): id is number => typeof id === "number");
    const semuaTerpilih =
      idsHalaman.length > 0 &&
      idsHalaman.every((id) => terpilih.includes(id));
    if (semuaTerpilih) {
      setTerpilih((lama) => lama.filter((id) => !idsHalaman.includes(id)));
    } else {
      setTerpilih((lama) => Array.from(new Set([...lama, ...idsHalaman])));
    }
  }

  function pilihBarisUntukIsi(item: ValidasiUnmatchBaris) {
    setTerpilih([item.id]);
    if (item.konfirmasi) {
      setStatusKonfirmasi(
        item.konfirmasi.status === "sesuai_kenyataan"
          ? "sesuai_kenyataan"
          : "akan_diperbaiki",
      );
      setCatatanKonfirmasi(item.konfirmasi.catatan ?? "");
    }
    setTimeout(() => {
      inputCatatanRef.current?.focus();
    }, 50);
  }

  async function simpanKonfirmasi(statusTarget: string) {
    if (runId === null) {
      return;
    }
    if (terpilih.length === 0) {
      setGalat("Pilih minimal satu baris temuan pada tabel terlebih dahulu.");
      return;
    }
    const alasan = catatanKonfirmasi.trim();
    if (statusTarget === "sesuai_kenyataan" && !alasan) {
      setGalat(
        "Alasan wajib diisi untuk konfirmasi 'Sesuai Kondisi Kenyataan'.",
      );
      inputCatatanRef.current?.focus();
      return;
    }
    setMenyimpan(true);
    setGalat(null);
    setInfo(null);
    try {
      const hasil = await ambilJson<{ jumlah: number }>(
        `/runs/${runId}/validasi-sls/konfirmasi`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            unmatch_ids: terpilih,
            status: statusTarget,
            catatan: alasan || null,
          }),
        },
      );
      setInfo(
        statusTarget === "batal"
          ? `Konfirmasi pada ${hasil.jumlah} temuan dibatalkan.`
          : `Berhasil menyimpan konfirmasi untuk ${hasil.jumlah} temuan.`,
      );
      setTerpilih([]);
      await muatDaftar();
      onBerubah();
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setMenyimpan(false);
    }
  }

  async function simpanPersetujuan(
    keputusan: "disetujui" | "ditolak",
    idsTarget?: number[],
  ) {
    if (runId === null) {
      return;
    }
    const daftarId = idsTarget ?? terpilih;
    if (daftarId.length === 0) {
      setGalat(
        "Pilih minimal satu temuan berstatus 'Sesuai Kondisi Kenyataan'.",
      );
      return;
    }
    setMenyimpan(true);
    setGalat(null);
    setInfo(null);
    try {
      const hasil = await ambilJson<{ jumlah: number }>(
        `/runs/${runId}/validasi-sls/persetujuan`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            unmatch_ids: daftarId,
            keputusan,
            catatan: catatanProvinsi.trim() || null,
          }),
        },
      );
      setInfo(
        keputusan === "disetujui"
          ? `Disetujui Provinsi untuk ${hasil.jumlah} temuan.`
          : `Ditolak Provinsi untuk ${hasil.jumlah} temuan.`,
      );
      if (!idsTarget) {
        setTerpilih([]);
      }
      await muatDaftar();
      onBerubah();
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setMenyimpan(false);
    }
  }

  const totalHalaman = Math.max(1, Math.ceil(total / UKURAN_HALAMAN));
  const terpilihSesuaiKenyataan = baris.filter(
    (satu) =>
      terpilih.includes(satu.id) &&
      satu.konfirmasi?.status === "sesuai_kenyataan",
  ).length;

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="judul-konfirmasi-validasi"
      onClose={onTutup}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onTutup();
        }
      }}
      className="m-auto w-[min(86rem,calc(100vw-1.5rem))] max-h-[90vh] overflow-hidden rounded-xl border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-ink/40"
    >
      {sasaran && runId !== null ? (
        <div className="flex max-h-[90vh] flex-col">
          {/* Header */}
          <div className="sticky top-0 z-20 flex flex-wrap items-start justify-between gap-field border-b border-line bg-surface px-4 py-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                Konfirmasi Temuan Validasi Peta SLS 2026 Semester 1
              </p>
              <h2
                id="judul-konfirmasi-validasi"
                className="mt-0.5 text-base font-semibold tracking-tight text-ink"
              >
                {kodeWilayah(sasaran.kdprov, sasaran.kdkab)} ·{" "}
                {namaKabupaten(sasaran.kdprov, sasaran.kdkab) ?? "-"}
              </h2>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                <span>
                  Total temuan:{" "}
                  <strong className="text-ink">
                    {formatAngka(sasaran.total)}
                  </strong>
                </span>
                <span>·</span>
                <span>
                  Terkonfirmasi:{" "}
                  <strong className="text-ink">
                    {formatAngka(sasaran.terkonfirmasi ?? 0)}
                  </strong>
                </span>
                <span>·</span>
                <span>
                  Akan diperbaiki:{" "}
                  <strong className="text-ink">
                    {formatAngka(sasaran.akan_diperbaiki ?? 0)}
                  </strong>
                </span>
                <span>·</span>
                <span>
                  Sesuai kenyataan:{" "}
                  <strong className="text-ink">
                    {formatAngka(sasaran.sesuai_kenyataan ?? 0)}
                  </strong>{" "}
                  (Disetujui:{" "}
                  <strong className="text-success">
                    {formatAngka(sasaran.disetujui ?? 0)}
                  </strong>
                  , Menunggu:{" "}
                  <strong className="text-warning">
                    {formatAngka(sasaran.menunggu_persetujuan ?? 0)}
                  </strong>
                  {(sasaran.ditolak ?? 0) > 0 ? (
                    <>
                      , Ditolak:{" "}
                      <strong className="text-danger">
                        {formatAngka(sasaran.ditolak ?? 0)}
                      </strong>
                    </>
                  ) : null}
                  )
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <BadgeStatus status={sasaran.status} />
              <button
                type="button"
                onClick={onTutup}
                aria-label="Tutup dialog konfirmasi"
                className="grid h-9 w-9 place-items-center rounded-lg text-muted transition-colors hover:bg-paper hover:text-ink"
              >
                <IkonTutup className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {/* Panel Form Konfirmasi & Persetujuan */}
            <div className="grid gap-3 lg:grid-cols-12">
              <div
                className={`rounded-xl border border-line bg-paper p-3 ${
                  adalahAdminProvinsi ? "lg:col-span-7" : "lg:col-span-12"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    Form Konfirmasi Temuan (Kabupaten/Kota & Provinsi)
                  </p>
                  <span className="text-xs font-medium text-brand-strong">
                    {terpilih.length} baris dipilih
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap gap-2">
                  <label
                    className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      statusKonfirmasi === "akan_diperbaiki"
                        ? "border-brand bg-brand-soft text-brand-strong"
                        : "border-line-strong bg-surface text-ink"
                    }`}
                  >
                    <input
                      type="radio"
                      name="status_konfirmasi_validasi"
                      value="akan_diperbaiki"
                      checked={statusKonfirmasi === "akan_diperbaiki"}
                      onChange={() => setStatusKonfirmasi("akan_diperbaiki")}
                      className="accent-brand"
                    />
                    Akan Diperbaiki
                  </label>
                  <label
                    className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      statusKonfirmasi === "sesuai_kenyataan"
                        ? "border-brand bg-brand-soft text-brand-strong"
                        : "border-line-strong bg-surface text-ink"
                    }`}
                  >
                    <input
                      type="radio"
                      name="status_konfirmasi_validasi"
                      value="sesuai_kenyataan"
                      checked={statusKonfirmasi === "sesuai_kenyataan"}
                      onChange={() => setStatusKonfirmasi("sesuai_kenyataan")}
                      className="accent-brand"
                    />
                    Sesuai Kondisi Kenyataan (Wajib alasan)
                  </label>
                </div>

                <div className="mt-2">
                  <textarea
                    ref={inputCatatanRef}
                    rows={2}
                    value={catatanKonfirmasi}
                    onChange={(e) => setCatatanKonfirmasi(e.target.value)}
                    placeholder={
                      statusKonfirmasi === "sesuai_kenyataan"
                        ? "Tuliskan alasan sesuai kondisi kenyataan lapangan (wajib diisi)..."
                        : "Catatan perbaikan (opsional)..."
                    }
                    className="w-full rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-xs text-ink placeholder:text-muted focus:border-brand focus:outline-none"
                  />
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <TombolAksi
                    onClick={() => void simpanKonfirmasi(statusKonfirmasi)}
                    disabled={menyimpan || terpilih.length === 0}
                    className="min-h-8 px-3 text-xs"
                  >
                    {menyimpan
                      ? "Menyimpan..."
                      : `Simpan Konfirmasi (${terpilih.length})`}
                  </TombolAksi>
                  <TombolAksi
                    varian="sekunder"
                    onClick={() => void simpanKonfirmasi("batal")}
                    disabled={menyimpan || terpilih.length === 0}
                    className="min-h-8 px-3 text-xs"
                  >
                    Batalkan Konfirmasi
                  </TombolAksi>
                </div>
              </div>

              {adalahAdminProvinsi ? (
                <div className="rounded-xl border border-brand/30 bg-brand-soft/20 p-3 lg:col-span-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-brand-strong">
                      Persetujuan Admin Provinsi
                    </p>
                    <span className="text-xs text-muted">
                      {terpilihSesuaiKenyataan} terpilih &ldquo;Sesuai
                      Kondisi&rdquo;
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    Tinjau alasan &ldquo;Sesuai Kondisi Kenyataan&rdquo;. Bila
                    seluruh temuan kab/kota berstatus Sesuai Kondisi dan
                    disetujui, status progres menjadi{" "}
                    <strong className="text-success">
                      Sukses dengan catatan
                    </strong>
                    .
                  </p>
                  <div className="mt-2">
                    <input
                      type="text"
                      value={catatanProvinsi}
                      onChange={(e) => setCatatanProvinsi(e.target.value)}
                      placeholder="Catatan persetujuan / alasan penolakan provinsi (opsional)..."
                      className="w-full rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-xs text-ink placeholder:text-muted focus:border-brand focus:outline-none"
                    />
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={menyimpan || terpilihSesuaiKenyataan === 0}
                      onClick={() => void simpanPersetujuan("disetujui")}
                      className="min-h-8 rounded-lg border border-success/40 bg-success-soft px-3 text-xs font-semibold text-success transition-colors hover:bg-success/20 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Setujui ({terpilihSesuaiKenyataan})
                    </button>
                    <button
                      type="button"
                      disabled={menyimpan || terpilihSesuaiKenyataan === 0}
                      onClick={() => void simpanPersetujuan("ditolak")}
                      className="min-h-8 rounded-lg border border-danger/40 bg-danger-soft px-3 text-xs font-semibold text-danger transition-colors hover:bg-danger/20 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Tolak ({terpilihSesuaiKenyataan})
                    </button>
                  </div>
                </div>
              ) : null}
            </div>

            {galat ? (
              <div
                role="alert"
                className="rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-xs text-danger"
              >
                {galat}
              </div>
            ) : null}

            {info ? (
              <div
                role="status"
                className="rounded-lg border border-success/30 bg-success-soft/60 px-3 py-2 text-xs text-success"
              >
                {info}
              </div>
            ) : null}

            {/* Baris Saringan & Paging */}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={jenis}
                  onChange={(e) => {
                    setJenis(e.target.value);
                    setHalaman(0);
                  }}
                  className="min-h-8 rounded-lg border border-line-strong bg-surface px-2.5 py-1 text-xs text-ink"
                >
                  {PILIHAN_JENIS.map((p) => (
                    <option key={p.kode} value={p.kode}>
                      {p.label}
                    </option>
                  ))}
                </select>

                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setHalaman(0);
                  }}
                  className="min-h-8 rounded-lg border border-line-strong bg-surface px-2.5 py-1 text-xs text-ink"
                >
                  {PILIHAN_STATUS_KONFIRMASI.map((p) => (
                    <option key={p.kode} value={p.kode}>
                      {p.label}
                    </option>
                  ))}
                </select>

                <span className="text-xs text-muted">
                  Menampilkan {baris.length} dari {formatAngka(total)} temuan
                </span>
              </div>

              {totalHalaman > 1 ? (
                <div className="flex items-center gap-1.5 text-xs">
                  <button
                    type="button"
                    disabled={halaman <= 0 || memuat}
                    onClick={() => setHalaman((h) => Math.max(0, h - 1))}
                    className="rounded border border-line-strong bg-surface px-2 py-1 disabled:opacity-40"
                  >
                    Sebelumnya
                  </button>
                  <span className="tabular-nums text-muted">
                    Hal. {halaman + 1} / {totalHalaman}
                  </span>
                  <button
                    type="button"
                    disabled={halaman >= totalHalaman - 1 || memuat}
                    onClick={() =>
                      setHalaman((h) => Math.min(totalHalaman - 1, h + 1))
                    }
                    className="rounded border border-line-strong bg-surface px-2 py-1 disabled:opacity-40"
                  >
                    Berikutnya
                  </button>
                </div>
              ) : null}
            </div>

            {/* Tabel Rincian Temuan */}
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full min-w-[68rem] border-collapse text-xs">
                <thead>
                  <tr className="border-b border-line bg-paper text-left text-[11px] uppercase tracking-wide text-muted">
                    <th className="w-9 px-2.5 py-2 text-center">
                      <input
                        type="checkbox"
                        aria-label="Pilih semua di halaman ini"
                        checked={
                          baris.length > 0 &&
                          baris.every((satu) => terpilih.includes(satu.id))
                        }
                        onChange={toggleSemuaHalaman}
                        className="accent-brand"
                      />
                    </th>
                    <th className="px-2.5 py-2 font-semibold">Jenis</th>
                    <th className="px-2.5 py-2 font-semibold">
                      idsls / idsubsls Peta
                    </th>
                    <th className="px-2.5 py-2 font-semibold">
                      idsls / idsubsls Master
                    </th>
                    <th className="px-2.5 py-2 font-semibold">
                      Nama SLS & Keterangan
                    </th>
                    <th className="px-2.5 py-2 font-semibold">
                      Konfirmasi & Alasan
                    </th>
                    <th className="px-2.5 py-2 font-semibold">
                      Persetujuan Provinsi
                    </th>
                    <th className="px-2.5 py-2 text-right font-semibold">
                      Aksi
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {memuat && baris.length === 0 ? (
                    <tr>
                      <td
                        colSpan={8}
                        className="px-4 py-6 text-center text-muted"
                      >
                        Memuat daftar temuan...
                      </td>
                    </tr>
                  ) : baris.length === 0 ? (
                    <tr>
                      <td
                        colSpan={8}
                        className="px-4 py-6 text-center text-muted"
                      >
                        Tidak ada temuan untuk saringan ini.
                      </td>
                    </tr>
                  ) : (
                    baris.map((item) => {
                      const dicentang = terpilih.includes(item.id);
                      const konf = item.konfirmasi;
                      return (
                        <tr
                          key={item.id}
                          className={`border-b border-line/60 last:border-0 ${
                            dicentang
                              ? "bg-brand-soft/30"
                              : "hover:bg-paper/70"
                          }`}
                        >
                          <td className="px-2.5 py-2 text-center align-top">
                            <input
                              type="checkbox"
                              checked={dicentang}
                              onChange={() => toggleSatu(item.id)}
                              className="accent-brand"
                            />
                          </td>
                          <td className="whitespace-nowrap px-2.5 py-2 align-top">
                            <span className="inline-block rounded border border-line-strong bg-paper px-1.5 py-0.5 text-[11px] font-medium text-ink">
                              {labelJenisSingkat(item.jenis)}
                            </span>
                          </td>
                          <td className="whitespace-nowrap px-2.5 py-2 align-top font-mono text-[11px]">
                            <div>{item.idsls_peta ?? "—"}</div>
                            <div className="text-muted">
                              {item.idsubsls_peta ?? "—"}
                            </div>
                          </td>
                          <td className="whitespace-nowrap px-2.5 py-2 align-top font-mono text-[11px]">
                            <div>{item.idsls_master ?? "—"}</div>
                            <div className="text-muted">
                              {item.idsubsls_master ?? "—"}
                            </div>
                          </td>
                          <td className="max-w-[16rem] px-2.5 py-2 align-top">
                            <div className="font-medium text-ink">
                              {item.nmsls ?? "—"}
                            </div>
                            {item.catatan ? (
                              <div className="mt-0.5 text-[11px] text-muted">
                                {item.catatan}
                              </div>
                            ) : null}
                          </td>
                          <td className="max-w-[18rem] px-2.5 py-2 align-top">
                            {!konf ? (
                              <span className="text-muted">
                                Belum dikonfirmasi
                              </span>
                            ) : (
                              <div>
                                <span
                                  className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                                    konf.status === "sesuai_kenyataan"
                                      ? "bg-brand-soft text-brand-strong"
                                      : "bg-warning/15 text-warning"
                                  }`}
                                >
                                  {konf.label}
                                </span>
                                {konf.catatan ? (
                                  <p className="mt-1 whitespace-pre-wrap text-ink">
                                    {konf.catatan}
                                  </p>
                                ) : null}
                                <p className="mt-0.5 text-[10px] text-muted">
                                  Oleh {konf.oleh ?? konf.username ?? "—"}
                                  {konf.pada
                                    ? ` · ${formatWaktu(konf.pada)}`
                                    : ""}
                                </p>
                              </div>
                            )}
                          </td>
                          <td className="max-w-[16rem] px-2.5 py-2 align-top">
                            {konf?.status !== "sesuai_kenyataan" ? (
                              <span className="text-muted">—</span>
                            ) : konf.persetujuan_status === "disetujui" ? (
                              <div>
                                <span className="inline-block rounded border border-success/30 bg-success-soft px-1.5 py-0.5 text-[11px] font-semibold text-success">
                                  Disetujui Provinsi
                                </span>
                                {konf.persetujuan_catatan ? (
                                  <p className="mt-1 text-ink">
                                    {konf.persetujuan_catatan}
                                  </p>
                                ) : null}
                                <p className="mt-0.5 text-[10px] text-muted">
                                  Oleh {konf.persetujuan_oleh ?? "Provinsi"}
                                  {konf.persetujuan_pada
                                    ? ` · ${formatWaktu(konf.persetujuan_pada)}`
                                    : ""}
                                </p>
                              </div>
                            ) : konf.persetujuan_status === "ditolak" ? (
                              <div>
                                <span className="inline-block rounded border border-danger/30 bg-danger-soft px-1.5 py-0.5 text-[11px] font-semibold text-danger">
                                  Ditolak Provinsi
                                </span>
                                {konf.persetujuan_catatan ? (
                                  <p className="mt-1 text-danger">
                                    {konf.persetujuan_catatan}
                                  </p>
                                ) : null}
                                <p className="mt-0.5 text-[10px] text-muted">
                                  Oleh {konf.persetujuan_oleh ?? "Provinsi"}
                                  {konf.persetujuan_pada
                                    ? ` · ${formatWaktu(konf.persetujuan_pada)}`
                                    : ""}
                                </p>
                              </div>
                            ) : (
                              <span className="inline-block rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[11px] font-medium text-warning">
                                Menunggu Persetujuan
                              </span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-2.5 py-2 text-right align-top">
                            <div className="inline-flex flex-wrap justify-end gap-1">
                              <button
                                type="button"
                                onClick={() => pilihBarisUntukIsi(item)}
                                className="rounded border border-line-strong bg-surface px-2 py-1 text-[11px] font-semibold text-ink hover:border-brand hover:text-brand-strong"
                              >
                                {konf ? "Ubah" : "Konfirmasi"}
                              </button>
                              {adalahAdminProvinsi &&
                              konf?.status === "sesuai_kenyataan" ? (
                                <>
                                  <button
                                    type="button"
                                    disabled={
                                      menyimpan ||
                                      konf.persetujuan_status === "disetujui"
                                    }
                                    onClick={() =>
                                      void simpanPersetujuan("disetujui", [
                                        item.id,
                                      ])
                                    }
                                    className="rounded border border-success/40 bg-success-soft px-2 py-1 text-[11px] font-semibold text-success hover:bg-success/20 disabled:opacity-40"
                                  >
                                    Setujui
                                  </button>
                                  <button
                                    type="button"
                                    disabled={
                                      menyimpan ||
                                      konf.persetujuan_status === "ditolak"
                                    }
                                    onClick={() =>
                                      void simpanPersetujuan("ditolak", [
                                        item.id,
                                      ])
                                    }
                                    className="rounded border border-danger/40 bg-danger-soft px-2 py-1 text-[11px] font-semibold text-danger hover:bg-danger/20 disabled:opacity-40"
                                  >
                                    Tolak
                                  </button>
                                </>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </dialog>
  );
}
