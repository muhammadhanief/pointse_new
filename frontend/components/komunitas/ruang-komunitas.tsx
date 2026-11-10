"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import { IkonTutup } from "@/components/dashboard/icons";
import { adalahBatal, ambilJson, pesanKesalahan } from "@/lib/api/klien";
import type {
  DaftarKomunitasTopik,
  KategoriKomunitas,
  KomunitasTopik,
  KomunitasTopikDetail,
  RuleTargetKomunitas,
  StatusKomunitas,
} from "@/lib/api/types";
import { PERAN_ADMIN_PROVINSI, kodeWilayah } from "@/lib/auth/peran";
import { formatAngka, formatWaktu } from "@/lib/format";
import { namaKabupaten } from "@/lib/wilayah/kabupaten";

const PILIHAN_KATEGORI: { kode: KategoriKomunitas; label: string; singkat: string }[] = [
  {
    kode: "peta_2026_s1",
    label: "Peta SLS 2026 S1 (Validasi)",
    singkat: "Peta SLS 2026 S1",
  },
  {
    kode: "peta_2025_s2",
    label: "Peta SLS 2025 S2 (Identifikasi)",
    singkat: "Peta SLS 2025 S2",
  },
  {
    kode: "geotagging",
    label: "Titik Geotagging (Pengecekan)",
    singkat: "Titik Geotagging",
  },
  { kode: "lainnya", label: "Lainnya", singkat: "Lainnya" },
];

const PILIHAN_STATUS: { kode: StatusKomunitas; label: string }[] = [
  { kode: "terbuka", label: "Belum Ada Solusi" },
  { kode: "terpecahkan", label: "Sudah Ada Solusi" },
  { kode: "jadi_rule", label: "Dijadikan Rule PointSE" },
];

const PILIHAN_RULE_TARGET: {
  kode: RuleTargetKomunitas;
  label: string;
  singkat: string;
  href: string;
}[] = [
  {
    kode: "identifikasi",
    label: "Rule Identifikasi (Proses A - Peta 2025 S2)",
    singkat: "Rule Identifikasi",
    href: "/proses/identifikasi",
  },
  {
    kode: "pengecekan",
    label: "Rule Pengecekan (Proses B - Titik Geotagging)",
    singkat: "Rule Pengecekan",
    href: "/proses/pengecekan",
  },
  {
    kode: "validasi",
    label: "Rule Validasi (Proses V - Peta SLS 2026 S1)",
    singkat: "Rule Validasi",
    href: "/proses/validasi",
  },
];

function formatNomorTiket(id: number): string {
  return `#${String(id).padStart(4, "0")}`;
}

function labelKategori(kode: string, singkat = false): string {
  const temuan = PILIHAN_KATEGORI.find((item) => item.kode === kode);
  if (!temuan) {
    return kode;
  }
  return singkat ? temuan.singkat : temuan.label;
}

function infoRuleTarget(kode: string | null) {
  if (!kode) {
    return null;
  }
  return PILIHAN_RULE_TARGET.find((item) => item.kode === kode) ?? null;
}

function BadgeStatusKomunitas({ status }: { status: string }) {
  if (status === "jadi_rule") {
    return (
      <span className="inline-flex items-center rounded-md border border-brand/40 bg-brand-soft px-2 py-0.5 text-xs font-semibold text-brand-strong">
        Dijadikan Rule PointSE
      </span>
    );
  }
  if (status === "terpecahkan") {
    return (
      <span className="inline-flex items-center rounded-md border border-success/40 bg-success-soft px-2 py-0.5 text-xs font-semibold text-success">
        Sudah Ada Solusi
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-md border border-warning/40 bg-warning/10 px-2 py-0.5 text-xs font-semibold text-warning">
      Belum Ada Solusi
    </span>
  );
}

function labelAsalWilayah(kdprov: string, kdkab: string | null, peran: string) {
  if (peran === PERAN_ADMIN_PROVINSI || !kdkab) {
    return `Provinsi (${kdprov})`;
  }
  const nama = namaKabupaten(kdprov, kdkab);
  const kode = kodeWilayah(kdprov, kdkab);
  return nama ? `${kode} · ${nama}` : kode;
}

export function RuangKomunitas({
  peran,
}: {
  kdprov: string;
  kdkab: string | null;
  peran: string;
}) {
  const adalahAdminProvinsi = peran === PERAN_ADMIN_PROVINSI;

  const [data, setData] = useState<DaftarKomunitasTopik>({
    total: 0,
    terbuka: 0,
    terpecahkan: 0,
    jadi_rule: 0,
    baris: [],
  });
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);

  const [filterKategori, setFilterKategori] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterRuleTarget, setFilterRuleTarget] = useState<string>("");
  const [kataKunci, setKataKunci] = useState<string>("");

  const [tiketDisalinId, setTiketDisalinId] = useState<number | null>(null);
  const [menghapusId, setMenghapusId] = useState<number | null>(null);

  // State modal form buat topik baru
  const [bukaFormBaru, setBukaFormBaru] = useState(false);
  const [kategoriBaru, setKategoriBaru] =
    useState<KategoriKomunitas>("peta_2026_s1");
  const [judulBaru, setJudulBaru] = useState("");
  const [errorTxtBaru, setErrorTxtBaru] = useState("");
  const [namaFileTxt, setNamaFileTxt] = useState<string | null>(null);
  const [deskripsiBaru, setDeskripsiBaru] = useState("");
  const [solusiAwalBaru, setSolusiAwalBaru] = useState("");
  const [menyimpanBaru, setMenyimpanBaru] = useState(false);
  const [galatBaru, setGalatBaru] = useState<string | null>(null);

  // State modal detail topik & diskusi
  const [detail, setDetail] = useState<KomunitasTopikDetail | null>(null);
  const [memuatDetail, setMemuatDetail] = useState(false);
  const [isiKomentar, setIsiKomentar] = useState("");
  const [tandaiSolusiKomentar, setTandaiSolusiKomentar] = useState(false);
  const [menyimpanKomentar, setMenyimpanKomentar] = useState(false);
  const [galatDetail, setGalatDetail] = useState<string | null>(null);

  // State panel admin provinsi (status & rule target)
  const [statusAdmin, setStatusAdmin] = useState<StatusKomunitas>("terbuka");
  const [ruleTargetAdmin, setRuleTargetAdmin] = useState<string>("");
  const [ruleCatatanAdmin, setRuleCatatanAdmin] = useState<string>("");
  const [menyimpanRule, setMenyimpanRule] = useState(false);

  const dialogBuatRef = useRef<HTMLDialogElement | null>(null);
  const dialogDetailRef = useRef<HTMLDialogElement | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const muatDaftar = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setMemuat(true);
    setGalat(null);
    try {
      const param = new URLSearchParams({ limit: "100" });
      if (filterKategori) {
        param.set("kategori", filterKategori);
      }
      if (filterStatus) {
        param.set("status", filterStatus);
      }
      if (filterRuleTarget) {
        param.set("rule_target", filterRuleTarget);
      }
      if (kataKunci.trim()) {
        param.set("q", kataKunci.trim());
      }
      const hasil = await ambilJson<DaftarKomunitasTopik>(
        `/komunitas/topik?${param.toString()}`,
        { signal: controller.signal },
      );
      if (controller.signal.aborted) {
        return;
      }
      setData(hasil);
    } catch (err) {
      if (adalahBatal(err) || controller.signal.aborted) {
        return;
      }
      setGalat(pesanKesalahan(err));
    } finally {
      if (!controller.signal.aborted) {
        setMemuat(false);
      }
    }
  }, [filterKategori, filterStatus, filterRuleTarget, kataKunci]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void muatDaftar();
    }, 200);
    return () => {
      window.clearTimeout(timer);
      controllerRef.current?.abort();
    };
  }, [muatDaftar]);

  useEffect(() => {
    const el = dialogBuatRef.current;
    if (!el) {
      return;
    }
    if (bukaFormBaru) {
      if (!el.open) {
        el.showModal();
      }
    } else if (el.open) {
      el.close();
    }
  }, [bukaFormBaru]);

  useEffect(() => {
    const el = dialogDetailRef.current;
    if (!el) {
      return;
    }
    if (detail) {
      if (!el.open) {
        el.showModal();
      }
    } else if (el.open) {
      el.close();
    }
  }, [detail]);

  async function salinRujukanWa(topik: Pick<KomunitasTopik, "id" | "judul">) {
    const teks = `${formatNomorTiket(topik.id)} — ${topik.judul}`;
    try {
      await navigator.clipboard.writeText(teks);
      setTiketDisalinId(topik.id);
      window.setTimeout(() => {
        setTiketDisalinId((sebelumnya) =>
          sebelumnya === topik.id ? null : sebelumnya,
        );
      }, 1800);
    } catch {
      // Abaikan bila clipboard tidak diizinkan browser
    }
  }

  async function bukaDetailTopik(topikId: number) {
    setMemuatDetail(true);
    setGalatDetail(null);
    try {
      const hasil = await ambilJson<KomunitasTopikDetail>(
        `/komunitas/topik/${topikId}`,
      );
      setDetail(hasil);
      setStatusAdmin((hasil.status as StatusKomunitas) || "terbuka");
      setRuleTargetAdmin(hasil.rule_target ?? "");
      setRuleCatatanAdmin(hasil.rule_catatan ?? "");
      setIsiKomentar("");
      setTandaiSolusiKomentar(false);
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setMemuatDetail(false);
    }
  }

  function saatPilihBerkasTxt(event: ChangeEvent<HTMLInputElement>) {
    const berkas = event.target.files?.[0];
    if (!berkas) {
      return;
    }
    setNamaFileTxt(berkas.name);
    const pembaca = new FileReader();
    pembaca.onload = () => {
      const teks = typeof pembaca.result === "string" ? pembaca.result : "";
      setErrorTxtBaru(teks.slice(0, 15000));
      if (!judulBaru.trim()) {
        const barisPertama = teks
          .split(/\r?\n/)
          .map((b) => b.trim())
          .find((b) => b.length > 5);
        if (barisPertama) {
          setJudulBaru(barisPertama.slice(0, 160));
        }
      }
    };
    pembaca.readAsText(berkas);
  }

  async function kirimTopikBaru() {
    if (judulBaru.trim().length < 5) {
      setGalatBaru("Judul masalah minimal 5 karakter.");
      return;
    }
    if (deskripsiBaru.trim().length < 5) {
      setGalatBaru("Deskripsi kondisi/masalah minimal 5 karakter.");
      return;
    }
    setMenyimpanBaru(true);
    setGalatBaru(null);
    try {
      const hasil = await ambilJson<KomunitasTopikDetail>("/komunitas/topik", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          kategori: kategoriBaru,
          judul: judulBaru.trim(),
          error_txt: errorTxtBaru.trim() || null,
          deskripsi: deskripsiBaru.trim(),
          solusi_awal: solusiAwalBaru.trim() || null,
        }),
      });
      setJudulBaru("");
      setErrorTxtBaru("");
      setNamaFileTxt(null);
      setDeskripsiBaru("");
      setSolusiAwalBaru("");
      setBukaFormBaru(false);
      await muatDaftar();
      setDetail(hasil);
      setStatusAdmin((hasil.status as StatusKomunitas) || "terbuka");
      setRuleTargetAdmin(hasil.rule_target ?? "");
      setRuleCatatanAdmin(hasil.rule_catatan ?? "");
    } catch (err) {
      setGalatBaru(pesanKesalahan(err));
    } finally {
      setMenyimpanBaru(false);
    }
  }

  async function hapusTopik(topik: Pick<KomunitasTopik, "id" | "judul">) {
    const nomor = formatNomorTiket(topik.id);
    if (
      !window.confirm(
        `Hapus bahasan ${nomor} "${topik.judul}" beserta seluruh komentarnya?`,
      )
    ) {
      return;
    }
    setMenghapusId(topik.id);
    setGalat(null);
    try {
      await ambilJson<{ dihapus: boolean; id: number }>(
        `/komunitas/topik/${topik.id}`,
        { method: "DELETE" },
      );
      if (detail?.id === topik.id) {
        setDetail(null);
      }
      await muatDaftar();
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setMenghapusId(null);
    }
  }

  async function hapusKomentar(komentarId: number) {
    if (!detail) {
      return;
    }
    if (!window.confirm("Hapus balasan/komentar ini?")) {
      return;
    }
    setGalatDetail(null);
    try {
      const hasil = await ambilJson<KomunitasTopikDetail>(
        `/komunitas/topik/${detail.id}/komentar/${komentarId}`,
        { method: "DELETE" },
      );
      setDetail(hasil);
      setStatusAdmin((hasil.status as StatusKomunitas) || "terbuka");
      await muatDaftar();
    } catch (err) {
      setGalatDetail(pesanKesalahan(err));
    }
  }

  async function kirimKomentar() {
    if (!detail) {
      return;
    }
    if (isiKomentar.trim().length < 2) {
      setGalatDetail("Isi balasan/solusi tidak boleh kosong.");
      return;
    }
    setMenyimpanKomentar(true);
    setGalatDetail(null);
    try {
      const hasil = await ambilJson<KomunitasTopikDetail>(
        `/komunitas/topik/${detail.id}/komentar`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            isi: isiKomentar.trim(),
            tandai_sebagai_solusi: tandaiSolusiKomentar,
          }),
        },
      );
      setDetail(hasil);
      setStatusAdmin((hasil.status as StatusKomunitas) || "terbuka");
      setIsiKomentar("");
      setTandaiSolusiKomentar(false);
      await muatDaftar();
    } catch (err) {
      setGalatDetail(pesanKesalahan(err));
    } finally {
      setMenyimpanKomentar(false);
    }
  }

  async function toggleSolusi(komentarId: number) {
    if (!detail) {
      return;
    }
    setGalatDetail(null);
    try {
      const hasil = await ambilJson<KomunitasTopikDetail>(
        `/komunitas/topik/${detail.id}/komentar/${komentarId}/solusi`,
        { method: "POST" },
      );
      setDetail(hasil);
      setStatusAdmin((hasil.status as StatusKomunitas) || "terbuka");
      await muatDaftar();
    } catch (err) {
      setGalatDetail(pesanKesalahan(err));
    }
  }

  async function toggleDukungan(topik: KomunitasTopik) {
    try {
      const hasil = await ambilJson<KomunitasTopikDetail>(
        `/komunitas/topik/${topik.id}/dukungan`,
        { method: "POST" },
      );
      if (detail && detail.id === topik.id) {
        setDetail(hasil);
      }
      await muatDaftar();
    } catch (err) {
      setGalat(pesanKesalahan(err));
    }
  }

  async function simpanRuleAdmin() {
    if (!detail) {
      return;
    }
    if (statusAdmin === "jadi_rule" && !ruleTargetAdmin) {
      setGalatDetail(
        "Pilih modul target rule (Identifikasi, Pengecekan, atau Validasi).",
      );
      return;
    }
    setMenyimpanRule(true);
    setGalatDetail(null);
    try {
      const hasil = await ambilJson<KomunitasTopikDetail>(
        `/komunitas/topik/${detail.id}/rule`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            status: statusAdmin,
            rule_target: ruleTargetAdmin || null,
            rule_catatan: ruleCatatanAdmin.trim() || null,
          }),
        },
      );
      setDetail(hasil);
      await muatDaftar();
    } catch (err) {
      setGalatDetail(pesanKesalahan(err));
    } finally {
      setMenyimpanRule(false);
    }
  }

  const totalSeluruh = data.terbuka + data.terpecahkan + data.jadi_rule;

  return (
    <div className="space-y-field">
      <Panel
        judul="Daftar Bahasan Error Web GS Pusat (dataspasial.bps.go.id/gs)"
        deskripsi="Gunakan nomor tiket (mis. #0001) untuk merujuk bahasan saat berdiskusi di grup WhatsApp. Klik tombol '+ Bagikan Error GS / Solusi Baru' untuk membuka form laporan."
      >
        {/* Baris Ringkas Status (Chip Filter) + Tombol Modal Buat Bahasan */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <button
              type="button"
              onClick={() => setFilterStatus("")}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-semibold transition-colors ${
                filterStatus === ""
                  ? "border-brand bg-brand-soft text-brand-strong"
                  : "border-line bg-paper text-muted hover:border-line-strong hover:text-ink"
              }`}
            >
              <span>Semua</span>
              <span className="rounded bg-surface px-1.5 py-0.2 tabular-nums text-ink">
                {formatAngka(totalSeluruh)}
              </span>
            </button>

            <button
              type="button"
              onClick={() =>
                setFilterStatus((s) => (s === "terbuka" ? "" : "terbuka"))
              }
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-semibold transition-colors ${
                filterStatus === "terbuka"
                  ? "border-warning bg-warning/15 text-warning"
                  : "border-line bg-paper text-muted hover:border-warning/50 hover:text-ink"
              }`}
            >
              <span>Belum Ada Solusi</span>
              <span className="rounded bg-surface px-1.5 py-0.2 tabular-nums text-warning">
                {formatAngka(data.terbuka)}
              </span>
            </button>

            <button
              type="button"
              onClick={() =>
                setFilterStatus((s) =>
                  s === "terpecahkan" ? "" : "terpecahkan",
                )
              }
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-semibold transition-colors ${
                filterStatus === "terpecahkan"
                  ? "border-success bg-success-soft text-success"
                  : "border-line bg-paper text-muted hover:border-success/50 hover:text-ink"
              }`}
            >
              <span>Sudah Ada Solusi</span>
              <span className="rounded bg-surface px-1.5 py-0.2 tabular-nums text-success">
                {formatAngka(data.terpecahkan)}
              </span>
            </button>

            <button
              type="button"
              onClick={() =>
                setFilterStatus((s) => (s === "jadi_rule" ? "" : "jadi_rule"))
              }
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-semibold transition-colors ${
                filterStatus === "jadi_rule"
                  ? "border-brand bg-brand-soft text-brand-strong"
                  : "border-line bg-paper text-muted hover:border-brand/50 hover:text-ink"
              }`}
            >
              <span>Dijadikan Rule PointSE</span>
              <span className="rounded bg-surface px-1.5 py-0.2 tabular-nums text-brand-strong">
                {formatAngka(data.jadi_rule)}
              </span>
            </button>
          </div>

          <TombolAksi
            onClick={() => {
              setGalatBaru(null);
              setBukaFormBaru(true);
            }}
          >
            + Bagikan Error GS / Solusi Baru
          </TombolAksi>
        </div>

        {/* Baris Kontrol Pencarian & Filter */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={kataKunci}
            onChange={(e) => setKataKunci(e.target.value)}
            placeholder="Cari no. tiket (#0001), potongan error .txt, judul, atau kab/kota..."
            className="min-h-9 min-w-[16rem] flex-1 rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-muted focus:border-brand focus:outline-none"
          />
          <select
            value={filterKategori}
            onChange={(e) => setFilterKategori(e.target.value)}
            className="min-h-9 rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
          >
            <option value="">Semua Kategori</option>
            {PILIHAN_KATEGORI.map((k) => (
              <option key={k.kode} value={k.kode}>
                {k.label}
              </option>
            ))}
          </select>
          <select
            value={filterRuleTarget}
            onChange={(e) => setFilterRuleTarget(e.target.value)}
            className="min-h-9 rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
          >
            <option value="">Semua Target Rule</option>
            {PILIHAN_RULE_TARGET.map((r) => (
              <option key={r.kode} value={r.kode}>
                {r.label}
              </option>
            ))}
          </select>
        </div>

        {galat ? (
          <div
            role="alert"
            className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-xs text-danger"
          >
            {galat}
          </div>
        ) : null}

        {/* Tabel Daftar Bahasan Komunitas */}
        <div className="mt-3">
          {memuat && data.baris.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted">
              Memuat tabel bahasan komunitas...
            </p>
          ) : data.baris.length === 0 ? (
            <EmptyState judul="Belum ada bahasan yang cocok">
              Klik tombol <strong>+ Bagikan Error GS / Solusi Baru</strong> di
              kanan atas untuk menambahkan bahasan pertama.
            </EmptyState>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full border-collapse text-left text-xs">
                <thead className="border-b border-line bg-paper text-[11px] font-semibold uppercase tracking-wide text-muted">
                  <tr>
                    <th className="w-40 px-3 py-2.5">No. Tiket &amp; Aksi</th>
                    <th className="w-36 px-3 py-2.5">Kategori</th>
                    <th className="px-3 py-2.5">
                      Judul Masalah &amp; Cuplikan Error{" "}
                      <code className="font-mono">.txt</code>
                    </th>
                    <th className="w-40 px-3 py-2.5">Pelapor (Wilayah)</th>
                    <th className="w-40 px-3 py-2.5">Status &amp; Rule</th>
                    <th className="w-32 px-3 py-2.5 text-center">
                      Serupa &amp; Balasan
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-surface">
                  {data.baris.map((topik) => {
                    const nomorTiket = formatNomorTiket(topik.id);
                    const infoRule = infoRuleTarget(topik.rule_target);
                    return (
                      <tr
                        key={topik.id}
                        className="align-top transition-colors hover:bg-paper/60"
                      >
                        <td className="px-3 py-2.5">
                          <div className="flex flex-col items-start gap-1.5">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => void bukaDetailTopik(topik.id)}
                                className="rounded border border-brand/40 bg-brand-soft/60 px-2 py-0.5 font-mono text-xs font-bold text-brand-strong hover:bg-brand-soft"
                                title="Klik untuk membuka detail bahasan"
                              >
                                {nomorTiket}
                              </button>
                              <button
                                type="button"
                                onClick={() => void salinRujukanWa(topik)}
                                className="rounded border border-line bg-paper px-1.5 py-0.5 text-[11px] font-medium text-muted hover:border-brand hover:text-brand-strong"
                                title="Salin nomor tiket & judul untuk ditempel di WhatsApp"
                              >
                                {tiketDisalinId === topik.id
                                  ? "Disalin"
                                  : "Salin WA"}
                              </button>
                            </div>

                            <div className="flex flex-wrap items-center gap-1">
                              <button
                                type="button"
                                onClick={() => void bukaDetailTopik(topik.id)}
                                className="inline-flex min-h-7 items-center justify-center rounded-md border border-line-strong bg-surface px-2.5 text-xs font-semibold text-ink transition-colors hover:border-brand hover:text-brand-strong"
                              >
                                {memuatDetail && detail?.id === topik.id
                                  ? "Memuat..."
                                  : "Diskusi"}
                              </button>
                              {adalahAdminProvinsi ? (
                                <button
                                  type="button"
                                  disabled={menghapusId === topik.id}
                                  onClick={() => void hapusTopik(topik)}
                                  className="inline-flex min-h-7 items-center justify-center rounded-md border border-danger/40 bg-danger-soft/50 px-2 text-xs font-semibold text-danger transition-colors hover:bg-danger hover:text-white disabled:opacity-50"
                                  title="Hapus topik bahasan ini (Khusus Admin Provinsi)"
                                >
                                  {menghapusId === topik.id ? "..." : "Hapus"}
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </td>

                        <td className="px-3 py-2.5">
                          <span className="inline-flex items-center rounded-md border border-line-strong bg-paper px-2 py-0.5 text-xs font-medium text-ink">
                            {labelKategori(topik.kategori, true)}
                          </span>
                        </td>

                        <td className="px-3 py-2.5">
                          <button
                            type="button"
                            onClick={() => void bukaDetailTopik(topik.id)}
                            className="text-left text-sm font-semibold text-ink hover:text-brand-strong hover:underline"
                          >
                            {topik.judul}
                          </button>
                          <p className="mt-0.5 line-clamp-2 text-xs text-muted">
                            {topik.deskripsi}
                          </p>
                          {topik.error_txt ? (
                            <pre className="mt-1.5 line-clamp-2 max-w-xl overflow-hidden rounded border border-line bg-paper px-2 py-1 font-mono text-[11px] text-ink">
                              {topik.error_txt}
                            </pre>
                          ) : null}
                          {topik.solusi_awal ? (
                            <p className="mt-1 line-clamp-1 text-[11px] font-medium text-success">
                              Solusi awal: {topik.solusi_awal}
                            </p>
                          ) : null}
                        </td>

                        <td className="px-3 py-2.5">
                          <p className="font-semibold text-ink">{topik.oleh}</p>
                          <p className="text-[11px] text-muted">
                            {labelAsalWilayah(
                              topik.kdprov,
                              topik.kdkab,
                              topik.peran,
                            )}
                          </p>
                          <p className="mt-0.5 text-[11px] text-muted">
                            {formatWaktu(topik.created_at)}
                          </p>
                        </td>

                        <td className="px-3 py-2.5">
                          <div className="flex flex-col items-start gap-1">
                            <BadgeStatusKomunitas status={topik.status} />
                            {infoRule ? (
                              <Link
                                href={infoRule.href}
                                className="inline-flex items-center rounded border border-brand/40 bg-brand-soft/60 px-1.5 py-0.5 text-[11px] font-semibold text-brand-strong hover:underline"
                              >
                                {infoRule.singkat}
                              </Link>
                            ) : null}
                          </div>
                        </td>

                        <td className="px-3 py-2.5 text-center">
                          <div className="flex flex-col items-center gap-1">
                            <button
                              type="button"
                              onClick={() => void toggleDukungan(topik)}
                              title="Tandai bahwa kabupaten/kota Anda juga mengalami error serupa"
                              className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums transition-colors ${
                                topik.didukung_saya
                                  ? "border-brand bg-brand-soft text-brand-strong"
                                  : "border-line-strong bg-paper text-ink hover:border-brand"
                              }`}
                            >
                              <span>+1 Serupa</span>
                              <span>({formatAngka(topik.jumlah_dukungan)})</span>
                            </button>
                            <span className="text-[11px] text-muted tabular-nums">
                              {formatAngka(topik.jumlah_komentar)} balasan
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Panel>

      {/* Modal Popup: Form Bagikan Error GS / Solusi Baru */}
      <dialog
        ref={dialogBuatRef}
        aria-labelledby="judul-modal-buat-komunitas"
        onClose={() => setBukaFormBaru(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget && !menyimpanBaru) {
            setBukaFormBaru(false);
          }
        }}
        className="m-auto w-[min(48rem,calc(100vw-1.5rem))] max-h-[90vh] overflow-hidden rounded-xl border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-ink/40"
      >
        {bukaFormBaru ? (
          <div className="flex max-h-[90vh] flex-col">
            <div className="sticky top-0 z-20 flex items-start justify-between gap-3 border-b border-line bg-surface px-4 py-3">
              <div>
                <h2
                  id="judul-modal-buat-komunitas"
                  className="text-base font-semibold text-ink"
                >
                  Bagikan Error GS Pusat / Solusi Baru
                </h2>
                <p className="text-xs text-muted">
                  Setiap bahasan otomatis mendapat nomor tiket (mis. #0001) agar
                  mudah dirujuk di WhatsApp.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setBukaFormBaru(false)}
                disabled={menyimpanBaru}
                aria-label="Tutup form"
                className="grid h-9 w-9 place-items-center rounded-lg text-muted hover:bg-paper hover:text-ink"
              >
                <IkonTutup className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
              {galatBaru ? (
                <div
                  role="alert"
                  className="rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-xs text-danger"
                >
                  {galatBaru}
                </div>
              ) : null}

              <div className="grid gap-3 sm:grid-cols-12">
                <div className="sm:col-span-4">
                  <label className="block text-xs font-semibold text-ink">
                    Kategori Peta / Data
                  </label>
                  <select
                    value={kategoriBaru}
                    onChange={(e) =>
                      setKategoriBaru(e.target.value as KategoriKomunitas)
                    }
                    className="mt-1 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs text-ink"
                  >
                    {PILIHAN_KATEGORI.map((k) => (
                      <option key={k.kode} value={k.kode}>
                        {k.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="sm:col-span-8">
                  <label className="block text-xs font-semibold text-ink">
                    Judul Masalah / Ringkasan Error *
                  </label>
                  <input
                    type="text"
                    value={judulBaru}
                    onChange={(e) => setJudulBaru(e.target.value)}
                    placeholder="Contoh: Ditolak GS Pusat karena Poligon Self-Intersection pada kode SubSLS..."
                    className="mt-1 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs text-ink placeholder:text-muted focus:border-brand focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="block text-xs font-semibold text-ink">
                    Isi Pesan Error <code className="font-mono">.txt</code> dari
                    Web GS Pusat (Opsional, memudahkan pencarian)
                  </label>
                  <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-line-strong bg-paper px-2.5 py-1 text-xs font-medium text-ink hover:border-brand">
                    <span>Pilih Berkas .txt</span>
                    <input
                      type="file"
                      accept=".txt,text/plain"
                      onChange={saatPilihBerkasTxt}
                      className="hidden"
                    />
                  </label>
                </div>
                {namaFileTxt ? (
                  <p className="mt-0.5 text-[11px] text-brand-strong">
                    Dimuat dari berkas: {namaFileTxt}
                  </p>
                ) : null}
                <textarea
                  rows={4}
                  value={errorTxtBaru}
                  onChange={(e) => setErrorTxtBaru(e.target.value)}
                  placeholder="Tempel (paste) isi file .txt error yang diunduh dari http://dataspasial.bps.go.id/gs di sini..."
                  className="mt-1 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 font-mono text-xs text-ink placeholder:font-sans placeholder:text-muted focus:border-brand focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink">
                  Kronologi / Deskripsi Masalah *
                </label>
                <textarea
                  rows={3}
                  value={deskripsiBaru}
                  onChange={(e) => setDeskripsiBaru(e.target.value)}
                  placeholder="Jelaskan kondisi peta/titik saat diunggah ke GS Pusat dan apa kendalanya..."
                  className="mt-1 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs text-ink placeholder:text-muted focus:border-brand focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink">
                  Solusi / Cara Mengatasi (Opsional — isi bila sudah menemukan
                  solusinya)
                </label>
                <textarea
                  rows={3}
                  value={solusiAwalBaru}
                  onChange={(e) => setSolusiAwalBaru(e.target.value)}
                  placeholder="Jika sudah berhasil diatasi (misal langkah perbaikan di QGIS), bagikan di sini agar otomatis berstatus 'Sudah Ada Solusi'..."
                  className="mt-1 w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs text-ink placeholder:text-muted focus:border-brand focus:outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-line bg-paper px-4 py-3">
              <TombolAksi
                varian="sekunder"
                onClick={() => setBukaFormBaru(false)}
                disabled={menyimpanBaru}
              >
                Batal
              </TombolAksi>
              <TombolAksi
                onClick={() => void kirimTopikBaru()}
                disabled={menyimpanBaru}
              >
                {menyimpanBaru ? "Menyimpan..." : "Terbitkan Bahasan"}
              </TombolAksi>
            </div>
          </div>
        ) : null}
      </dialog>

      {/* Modal Popup: Detail Topik, Diskusi, dan Pengaturan Rule */}
      <dialog
        ref={dialogDetailRef}
        aria-labelledby="judul-detail-komunitas"
        onClose={() => setDetail(null)}
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            setDetail(null);
          }
        }}
        className="m-auto w-[min(72rem,calc(100vw-1.5rem))] max-h-[90vh] overflow-hidden rounded-xl border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-ink/40"
      >
        {detail ? (
          <div className="flex max-h-[90vh] flex-col">
            <div className="sticky top-0 z-20 flex items-start justify-between gap-3 border-b border-line bg-surface px-4 py-3">
              <div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded border border-brand/40 bg-brand-soft px-2 py-0.5 font-mono text-xs font-bold text-brand-strong">
                    {formatNomorTiket(detail.id)}
                  </span>
                  <button
                    type="button"
                    onClick={() => void salinRujukanWa(detail)}
                    className="rounded border border-line-strong bg-paper px-2 py-0.5 text-[11px] font-semibold text-ink hover:border-brand hover:text-brand-strong"
                  >
                    {tiketDisalinId === detail.id
                      ? "Tersalin untuk WA"
                      : "Salin Rujukan WA"}
                  </button>
                  <BadgeStatusKomunitas status={detail.status} />
                  <span className="inline-flex items-center rounded-md border border-line-strong bg-paper px-2 py-0.5 text-xs font-medium text-ink">
                    {labelKategori(detail.kategori)}
                  </span>
                  <span className="text-xs text-muted">
                    Dilaporkan oleh{" "}
                    <strong className="text-ink">{detail.oleh}</strong> (
                    {labelAsalWilayah(
                      detail.kdprov,
                      detail.kdkab,
                      detail.peran,
                    )}
                    ) · {formatWaktu(detail.created_at)}
                  </span>
                </div>
                <h2
                  id="judul-detail-komunitas"
                  className="mt-1 text-base font-semibold text-ink"
                >
                  {detail.judul}
                </h2>
              </div>

              <div className="flex items-center gap-2">
                {adalahAdminProvinsi ? (
                  <button
                    type="button"
                    disabled={menghapusId === detail.id}
                    onClick={() => void hapusTopik(detail)}
                    className="inline-flex min-h-8 items-center justify-center rounded-lg border border-danger/40 bg-danger-soft/50 px-2.5 text-xs font-semibold text-danger transition-colors hover:bg-danger hover:text-white disabled:opacity-50"
                  >
                    {menghapusId === detail.id ? "Menghapus..." : "Hapus Topik"}
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => setDetail(null)}
                  aria-label="Tutup diskusi"
                  className="grid h-9 w-9 place-items-center rounded-lg text-muted hover:bg-paper hover:text-ink"
                >
                  <IkonTutup className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {galatDetail ? (
                <div
                  role="alert"
                  className="rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-xs text-danger"
                >
                  {galatDetail}
                </div>
              ) : null}

              {/* Deskripsi & Error TXT */}
              <div className="rounded-xl border border-line bg-paper p-3.5 space-y-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    Deskripsi Masalah
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-ink">
                    {detail.deskripsi}
                  </p>
                </div>

                {detail.error_txt ? (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                      Output Error <code className="font-mono">.txt</code> dari
                      Web GS Pusat (dataspasial.bps.go.id/gs)
                    </p>
                    <pre className="mt-1 max-h-60 overflow-auto rounded-lg border border-line-strong bg-surface p-3 font-mono text-xs leading-5 text-ink">
                      {detail.error_txt}
                    </pre>
                  </div>
                ) : null}

                {detail.solusi_awal ? (
                  <div className="rounded-lg border border-success/40 bg-success-soft/50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-success">
                      Solusi Awal dari Pelapor
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-xs text-ink">
                      {detail.solusi_awal}
                    </p>
                  </div>
                ) : null}

                {detail.rule_target ? (
                  <div className="rounded-lg border border-brand/40 bg-brand-soft/40 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-brand-strong">
                      Tindak Lanjut Rule PointSE:{" "}
                      {infoRuleTarget(detail.rule_target)?.label ??
                        detail.rule_target}
                    </p>
                    {detail.rule_catatan ? (
                      <p className="mt-1 whitespace-pre-wrap text-xs text-ink">
                        {detail.rule_catatan}
                      </p>
                    ) : null}
                    {detail.rule_oleh ? (
                      <p className="mt-1 text-[11px] text-muted">
                        Ditetapkan oleh {detail.rule_oleh}
                        {detail.rule_pada
                          ? ` · ${formatWaktu(detail.rule_pada)}`
                          : ""}
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>

              {/* Panel Khusus Admin Provinsi: Angkat Jadi Rule Baru */}
              {adalahAdminProvinsi ? (
                <div className="rounded-xl border border-brand/40 bg-brand-soft/20 p-3.5 space-y-2.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-brand-strong">
                    Panel Admin Provinsi: Status Masalah &amp; Tambahan Rule
                    PointSE
                  </p>
                  <p className="text-xs text-muted">
                    Apabila pola error dari GS Pusat ini dapat dicegah otomatis
                    di PointSE, tandai target modulnya agar ditambahkan ke rule{" "}
                    <Link
                      href="/proses/identifikasi"
                      className="font-semibold underline"
                    >
                      Identifikasi
                    </Link>
                    ,{" "}
                    <Link
                      href="/proses/pengecekan"
                      className="font-semibold underline"
                    >
                      Pengecekan
                    </Link>
                    , atau{" "}
                    <Link
                      href="/proses/validasi"
                      className="font-semibold underline"
                    >
                      Validasi
                    </Link>
                    .
                  </p>

                  <div className="grid gap-2.5 sm:grid-cols-12">
                    <div className="sm:col-span-4">
                      <label className="block text-xs font-medium text-ink">
                        Status Topik
                      </label>
                      <select
                        value={statusAdmin}
                        onChange={(e) =>
                          setStatusAdmin(e.target.value as StatusKomunitas)
                        }
                        className="mt-1 w-full rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
                      >
                        {PILIHAN_STATUS.map((s) => (
                          <option key={s.kode} value={s.kode}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="sm:col-span-8">
                      <label className="block text-xs font-medium text-ink">
                        Target Penambahan Rule di PointSE
                      </label>
                      <select
                        value={ruleTargetAdmin}
                        onChange={(e) => setRuleTargetAdmin(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-line-strong bg-surface px-2.5 py-1.5 text-xs text-ink"
                      >
                        <option value="">
                          — Belum / Tidak dijadikan rule otomatis —
                        </option>
                        {PILIHAN_RULE_TARGET.map((r) => (
                          <option key={r.kode} value={r.kode}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div>
                    <input
                      type="text"
                      value={ruleCatatanAdmin}
                      onChange={(e) => setRuleCatatanAdmin(e.target.value)}
                      placeholder="Catatan spesifikasi rule baru (mis. Cek poligon multipolygon terpisah atau atribut wajib)..."
                      className="w-full rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-xs text-ink placeholder:text-muted"
                    />
                  </div>

                  <div>
                    <TombolAksi
                      onClick={() => void simpanRuleAdmin()}
                      disabled={menyimpanRule}
                      className="min-h-8 px-3 text-xs"
                    >
                      {menyimpanRule
                        ? "Menyimpan..."
                        : "Simpan Status & Target Rule"}
                    </TombolAksi>
                  </div>
                </div>
              ) : null}

              {/* Daftar Balasan / Solusi */}
              <div className="space-y-2.5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Diskusi &amp; Solusi ({formatAngka(detail.komentar.length)})
                </h3>

                {detail.komentar.length === 0 ? (
                  <p className="rounded-lg border border-line bg-paper px-3 py-4 text-center text-xs text-muted">
                    Belum ada balasan. Bagikan pengalaman atau solusi Anda di
                    bawah ini.
                  </p>
                ) : (
                  detail.komentar.map((k) => (
                    <div
                      key={k.id}
                      className={`rounded-xl border p-3 ${
                        k.adalah_solusi
                          ? "border-success bg-success-soft/40"
                          : "border-line bg-surface"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          {k.adalah_solusi ? (
                            <span className="rounded bg-success px-2 py-0.5 text-[11px] font-semibold text-white">
                              Solusi Terverifikasi
                            </span>
                          ) : null}
                          <strong className="text-ink">{k.oleh}</strong>
                          <span className="text-muted">
                            ({labelAsalWilayah(k.kdprov, k.kdkab, k.peran)}) ·{" "}
                            {formatWaktu(k.created_at)}
                          </span>
                        </div>

                        {adalahAdminProvinsi ? (
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => void toggleSolusi(k.id)}
                              className="rounded border border-line-strong bg-paper px-2 py-0.5 text-[11px] font-semibold text-ink hover:border-success hover:text-success"
                            >
                              {k.adalah_solusi
                                ? "Batalkan Tanda Solusi"
                                : "Tandai sebagai Solusi"}
                            </button>
                            <button
                              type="button"
                              onClick={() => void hapusKomentar(k.id)}
                              className="rounded border border-danger/40 bg-danger-soft/50 px-2 py-0.5 text-[11px] font-semibold text-danger hover:bg-danger hover:text-white"
                            >
                              Hapus
                            </button>
                          </div>
                        ) : null}
                      </div>
                      <p className="mt-1.5 whitespace-pre-wrap text-xs leading-5 text-ink">
                        {k.isi}
                      </p>
                    </div>
                  ))
                )}
              </div>

              {/* Form Tambah Balasan */}
              <div className="rounded-xl border border-line bg-paper p-3.5 space-y-2.5">
                <label className="block text-xs font-semibold text-ink">
                  Tulis Balasan / Bagikan Solusi
                </label>
                <textarea
                  rows={3}
                  value={isiKomentar}
                  onChange={(e) => setIsiKomentar(e.target.value)}
                  placeholder="Tuliskan langkah perbaikan di QGIS atau pengalaman mengatasi error ini..."
                  className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-xs text-ink placeholder:text-muted focus:border-brand focus:outline-none"
                />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-ink">
                    <input
                      type="checkbox"
                      checked={tandaiSolusiKomentar}
                      onChange={(e) =>
                        setTandaiSolusiKomentar(e.target.checked)
                      }
                      className="accent-brand"
                    />
                    <span>
                      Tandai balasan ini sebagai{" "}
                      <strong>Solusi Terverifikasi</strong> (jika Anda pembuat
                      topik / Admin Provinsi)
                    </span>
                  </label>

                  <TombolAksi
                    onClick={() => void kirimKomentar()}
                    disabled={menyimpanKomentar}
                    className="min-h-8 px-3 text-xs"
                  >
                    {menyimpanKomentar ? "Mengirim..." : "Kirim Balasan"}
                  </TombolAksi>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </dialog>
    </div>
  );
}
