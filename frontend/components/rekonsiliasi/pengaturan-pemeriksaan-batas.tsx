"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Panel, TombolAksi } from "@/components/dashboard/ui";
import { ambilJson, pesanKesalahan } from "@/lib/api/klien";
import type { RekonsiliasiBatasPengaturan } from "@/lib/api/types";
import { formatAngka, formatWaktu } from "@/lib/format";

const INTERVAL_PANTAU = 3000;

const NILAI_CEPAT: { label: string; nilai: string; keterangan: string }[] = [
  { label: "Tanpa filter", nilai: "0", keterangan: "Sama dengan Topology Checker QGIS" },
  { label: "1 mm²", nilai: "0.000001", keterangan: "Buang gesekan desimal koordinat" },
  { label: "1 cm²", nilai: "0.0001", keterangan: "Hanya sliver yang terlihat" },
  { label: "1 m²", nilai: "1", keterangan: "Hanya temuan yang terukur" },
];

function labelStatus(status: string): string {
  switch (status) {
    case "menunggu":
      return "Menunggu antrean worker";
    case "jalan":
      return "Sedang diperiksa";
    case "sukses":
      return "Selesai";
    case "gagal":
      return "Gagal";
    default:
      return status;
  }
}

export function PengaturanPemeriksaanBatas({
  onSelesai,
}: {
  onSelesai: () => void;
}) {
  const [data, setData] = useState<RekonsiliasiBatasPengaturan | null>(null);
  const [nilai, setNilai] = useState("0");
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [sedangSimpan, setSedangSimpan] = useState(false);
  const [sedangJalankan, setSedangJalankan] = useState(false);
  const statusSebelumnya = useRef<string | null>(null);
  const luasTersimpan = useRef<number | null>(null);
  const onSelesaiRef = useRef(onSelesai);

  useEffect(() => {
    onSelesaiRef.current = onSelesai;
  }, [onSelesai]);

  const terapkan = useCallback((hasil: RekonsiliasiBatasPengaturan) => {
    setData(hasil);

    // Isi ulang input hanya bila ambang tersimpan benar-benar berubah, supaya
    // ketikan admin tidak tertimpa polling status pemeriksaan.
    if (luasTersimpan.current !== hasil.luas_min_m2) {
      luasTersimpan.current = hasil.luas_min_m2;
      setNilai(String(hasil.luas_min_m2));
    }

    const statusBaru = hasil.jalankan?.status ?? null;
    const sebelumnya = statusSebelumnya.current;
    statusSebelumnya.current = statusBaru;
    if (
      sebelumnya !== null &&
      sebelumnya !== statusBaru &&
      (statusBaru === "sukses" || statusBaru === "gagal")
    ) {
      onSelesaiRef.current();
    }
  }, []);

  const muat = useCallback(() => {
    return ambilJson<RekonsiliasiBatasPengaturan>(
      "/rekonsiliasi-batas/pengaturan",
    )
      .then((hasil) => {
        terapkan(hasil);
        setGalat(null);
      })
      .catch((err: unknown) => {
        setGalat(pesanKesalahan(err));
      })
      .finally(() => {
        setMemuat(false);
      });
  }, [terapkan]);

  useEffect(() => {
    void muat();
  }, [muat]);

  const statusJalankan = data?.jalankan?.status ?? null;
  const sedangBerjalan = statusJalankan === "menunggu" || statusJalankan === "jalan";

  useEffect(() => {
    if (!sedangBerjalan) {
      return;
    }
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void muat();
      }
    }, INTERVAL_PANTAU);
    return () => window.clearInterval(interval);
  }, [sedangBerjalan, muat]);

  async function simpanAmbang() {
    const angka = Number(nilai.replace(",", "."));
    if (!Number.isFinite(angka) || angka < 0) {
      setGalat("Isi angka 0 atau lebih besar, contoh 0 atau 0.000001.");
      return;
    }
    setSedangSimpan(true);
    setGalat(null);
    try {
      const hasil = await ambilJson<RekonsiliasiBatasPengaturan>(
        "/rekonsiliasi-batas/pengaturan",
        {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ luas_min_m2: angka }),
        },
      );
      terapkan(hasil);
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setSedangSimpan(false);
    }
  }

  async function jalankanUlang() {
    if (
      !window.confirm(
        "Periksa ulang seluruh pasangan batas dengan ambang yang tersimpan? Proses ini memakan beberapa menit dan mengganti hasil pemeriksaan sebelumnya.",
      )
    ) {
      return;
    }
    setSedangJalankan(true);
    setGalat(null);
    try {
      const hasil = await ambilJson<{ id: number; status: string }>(
        "/rekonsiliasi-batas/jalankan-ulang",
        { method: "POST" },
      );
      statusSebelumnya.current = hasil.status;
      await muat();
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setSedangJalankan(false);
    }
  }

  const jalankan = data?.jalankan ?? null;
  const totalPasang = jalankan?.total_pasang ?? 0;
  const sudahDiproses = jalankan?.sudah_diproses ?? 0;
  const persen =
    totalPasang > 0
      ? Math.min(100, Math.round((sudahDiproses / totalPasang) * 100))
      : 0;

  return (
    <Panel
      judul="Ambang pemeriksaan batas"
      deskripsi="Dipakai saat menghitung Gap dan Overlap. Ubah ambang, lalu periksa ulang seluruh pasangan tanpa menunggu unggahan peta baru."
    >
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div>
          <label
            htmlFor="ambang-luas-minimum"
            className="block text-xs font-semibold uppercase tracking-wider text-muted"
          >
            Luas minimum temuan (m²)
          </label>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <input
              id="ambang-luas-minimum"
              type="number"
              min={0}
              step="any"
              inputMode="decimal"
              value={nilai}
              onChange={(e) => setNilai(e.target.value)}
              disabled={memuat || sedangSimpan}
              className="min-h-9 w-40 rounded-lg border border-line-strong bg-surface px-3 py-1.5 font-mono text-sm tabular-nums text-ink focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/30 disabled:opacity-60"
            />
            <TombolAksi
              varian="sekunder"
              onClick={() => void simpanAmbang()}
              disabled={memuat || sedangSimpan}
            >
              {sedangSimpan ? "Menyimpan..." : "Simpan ambang"}
            </TombolAksi>
          </div>
          <p className="mt-2 text-xs leading-normal text-muted">
            Isi <span className="font-mono tabular-nums">0</span> agar semua
            temuan dari mesin GEOS dicatat, sama persis dengan Topology Checker
            QGIS. Isi{" "}
            <span className="font-mono tabular-nums">0.000001</span> untuk
            mengabaikan irisan di bawah 1 mm² akibat selisih desimal koordinat.
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {NILAI_CEPAT.map((pilihan) => (
              <button
                key={pilihan.nilai}
                type="button"
                title={pilihan.keterangan}
                onClick={() => setNilai(pilihan.nilai)}
                className={`min-h-9 rounded-md border px-2.5 text-xs font-medium transition-colors ${
                  nilai === pilihan.nilai
                    ? "border-brand bg-brand-soft text-brand-strong"
                    : "border-line bg-surface text-muted hover:border-brand hover:text-brand-strong"
                }`}
              >
                {pilihan.label}
              </button>
            ))}
          </div>
        </div>

        <div className="border-t border-line pt-4 lg:border-t-0 lg:border-l lg:pl-4 lg:pt-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              Pemeriksaan ulang semua pasangan
            </span>
            {jalankan && (
              <span className="font-mono text-xs tabular-nums text-muted">
                #{jalankan.id}
              </span>
            )}
          </div>

          {jalankan ? (
            <div className="mt-2 space-y-2">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs">
                <span className="font-semibold text-ink">
                  {labelStatus(jalankan.status)}
                </span>
                {sedangBerjalan && (
                  <span className="font-mono tabular-nums text-muted">
                    {formatAngka(sudahDiproses)} / {formatAngka(totalPasang)}{" "}
                    pasangan
                  </span>
                )}
                {jalankan.finished_at && (
                  <span className="text-muted">
                    {formatWaktu(jalankan.finished_at)}
                  </span>
                )}
              </div>
              {sedangBerjalan && (
                <div className="h-1.5 overflow-hidden rounded-full bg-paper">
                  <div
                    className="h-full rounded-full bg-brand transition-[width]"
                    style={{ width: `${persen}%` }}
                  />
                </div>
              )}
              {jalankan.pesan && (
                <p
                  className={`text-xs leading-normal ${
                    jalankan.status === "gagal" ? "text-danger" : "text-muted"
                  }`}
                >
                  {jalankan.pesan}
                </p>
              )}
              {jalankan.status === "sukses" && (
                <p className="text-xs text-muted">
                  {formatAngka(jalankan.jumlah_bersih)} clean,{" "}
                  {formatAngka(jalankan.jumlah_belum_clean)} belum clean,{" "}
                  {formatAngka(jalankan.jumlah_gagal)} gagal diperiksa.
                </p>
              )}
            </div>
          ) : (
            <p className="mt-2 text-xs leading-normal text-muted">
              Belum ada pemeriksaan ulang manual. Pemeriksaan otomatis tetap
              berjalan setiap kali run Validasi SLS selesai.
            </p>
          )}

          <TombolAksi
            className="mt-3"
            onClick={() => void jalankanUlang()}
            disabled={memuat || sedangJalankan || sedangBerjalan}
          >
            {sedangJalankan
              ? "Mengantrekan..."
              : sedangBerjalan
                ? "Sedang berjalan"
                : "Periksa ulang semua pasangan"}
          </TombolAksi>
        </div>
      </div>

      {galat && (
        <p role="alert" className="mt-3 text-xs text-danger">
          {galat}
        </p>
      )}
    </Panel>
  );
}