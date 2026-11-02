"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { MultiPilih } from "@/components/dashboard/multi-pilih";
import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
  unduhBerkas,
} from "@/lib/api/klien";
import type { DaftarGeserRun, Geser, GeserBaris, GeserRun } from "@/lib/api/types";
import { formatAngka, formatTanggal } from "@/lib/format";
import { daftarKabupaten } from "@/lib/wilayah/kabupaten";

const BATAS = 50;
/** Ukuran halaman yang bisa dipilih; "semua" menampilkan seluruh baris. */
const PILIHAN_BATAS = [10, 20, 50] as const;
/** Batas maksimum baris per permintaan ``/geser`` (API: le=500). */
const BATAS_PERMINTAAN = 500;
/** Lantai ambang: pergeseran di bawah ini tidak pernah disimpan saat job. */
const AMBANG_BAWAAN = 10;

const KELAS_HEAD =
  "sticky top-0 z-10 bg-paper px-3 py-2 font-semibold after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-line";
const KELAS_HEAD_KIRI =
  "sticky top-0 z-20 bg-paper px-3 py-2 font-semibold after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-line";
const KELAS_KIRI =
  "sticky left-0 z-10 whitespace-nowrap border-r border-line bg-surface px-3 py-2 text-muted";

type UkuranHalaman = number | "semua";

const formatterJarak = new Intl.NumberFormat("id-ID", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function teks(nilai: string | null | undefined): string {
  return nilai && nilai.trim() !== "" ? nilai : "–";
}

/** Jarak geser dalam meter (desimal koma). */
function teksJarak(nilai: number | null | undefined): string {
  return nilai == null || !Number.isFinite(nilai)
    ? "–"
    : `${formatterJarak.format(nilai)} m`;
}

/** Tombol salin kecil untuk id/kode yang panjang. */
function TombolSalin({ nilai, label }: { nilai: string | null; label: string }) {
  const [tersalin, setTersalin] = useState(false);
  if (!nilai) {
    return null;
  }
  return (
    <button
      type="button"
      title={`Salin ${label}`}
      aria-label={`Salin ${label}`}
      onClick={async (kejadian) => {
        kejadian.stopPropagation();
        try {
          await navigator.clipboard.writeText(nilai);
          setTersalin(true);
          window.setTimeout(() => setTersalin(false), 1200);
        } catch {
          setTersalin(false);
        }
      }}
      className="ml-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] text-muted transition-colors hover:bg-paper hover:text-ink"
    >
      {tersalin ? "✓" : "⧉"}
    </button>
  );
}

export function GeserClient({
  kdprov,
  kdkabAwal,
}: {
  kdprov: string;
  kdkabAwal: string | null;
}) {
  const opsi = daftarKabupaten(kdprov);
  const [kdkabs, setKdkabs] = useState<string[]>(() =>
    kdkabAwal ? [kdkabAwal] : opsi.map((satu) => satu.kode),
  );
  // ``meterDraf`` = isi kotak; ``meter`` = ambang yang sedang dipakai memuat.
  const [meterDraf, setMeterDraf] = useState(String(AMBANG_BAWAAN));
  const [meter, setMeter] = useState(AMBANG_BAWAAN);
  const [cari, setCari] = useState("");
  const [kataKunci, setKataKunci] = useState("");
  const [halaman, setHalaman] = useState(0);
  const [batas, setBatas] = useState<UkuranHalaman>(BATAS);
  const [data, setData] = useState<Geser | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [mengunduh, setMengunduh] = useState(false);
  // Riwayat run B sukses milik kabupaten yang sedang dipilih (dropdown riwayat).
  const [riwayat, setRiwayat] = useState<GeserRun[]>([]);
  // ``null`` = run terakhir (default). Hanya berlaku saat tepat satu kabupaten.
  const [runTerpilih, setRunTerpilih] = useState<number | null>(null);
  const kdkabSatu = kdkabs.length === 1 ? kdkabs[0] : null;

  // Parameter /geser untuk satu permintaan. Limit/offset eksplisit supaya mode
  // "Semua" bisa menyusuri halaman sampai seluruh baris terkumpul.
  const parameter = useCallback(
    (ukuran: number, halamanMuat: number) => {
      const isi = new URLSearchParams({
        kdprov,
        min_meter: String(meter),
        limit: String(ukuran),
        offset: String(halamanMuat * ukuran),
      });
      for (const kode of kdkabs) {
        isi.append("kdkab", kode);
      }
      if (kataKunci) {
        isi.set("q", kataKunci);
      }
      if (kdkabSatu && runTerpilih != null) {
        isi.set("run_b_id", String(runTerpilih));
      }
      return isi;
    },
    [kdprov, kdkabs, meter, kataKunci, kdkabSatu, runTerpilih],
  );

  const muat = useCallback(
    async (signal?: AbortSignal) => {
      if (kdkabs.length === 0) {
        setData(null);
        setMemuat(false);
        return;
      }
      setMemuat(true);
      setGalat(null);
      try {
        if (batas === "semua") {
          const kumpulan: GeserBaris[] = [];
          let dasar: Geser | null = null;
          for (let langkah = 0; ; langkah += 1) {
            const hasil = await ambilJson<Geser>(
              `/geser?${parameter(BATAS_PERMINTAAN, langkah)}`,
              { signal },
            );
            dasar = dasar ?? hasil;
            kumpulan.push(...hasil.baris);
            if (hasil.baris.length === 0 || kumpulan.length >= hasil.total) {
              break;
            }
          }
          if (dasar) {
            setData({ ...dasar, baris: kumpulan });
          }
        } else {
          const hasil = await ambilJson<Geser>(
            `/geser?${parameter(batas, halaman)}`,
            { signal },
          );
          setData(hasil);
        }
      } catch (kesalahan) {
        if (!adalahBatal(kesalahan)) {
          setGalat(pesanKesalahan(kesalahan));
        }
      } finally {
        if (!signal?.aborted) {
          setMemuat(false);
        }
      }
    },
    [kdkabs.length, batas, halaman, parameter],
  );

  useEffect(() => {
    const kendali = new AbortController();
    void muat(kendali.signal);
    return () => kendali.abort();
  }, [muat]);

  // Muat riwayat run kabupaten yang dipilih. Ganti kabupaten/ambang -> balik ke
  // run terakhir (jumlah geser tiap run ikut ambang).
  useEffect(() => {
    setRunTerpilih(null);
    if (!kdkabSatu) {
      setRiwayat([]);
      return;
    }
    const kendali = new AbortController();
    void (async () => {
      try {
        const isi = new URLSearchParams({
          kdprov,
          kdkab: kdkabSatu,
          min_meter: String(meter),
        });
        const hasil = await ambilJson<DaftarGeserRun>(
          `/geser/riwayat?${isi}`,
          { signal: kendali.signal },
        );
        setRiwayat(hasil.baris);
      } catch (kesalahan) {
        if (!adalahBatal(kesalahan)) {
          setRiwayat([]);
        }
      }
    })();
    return () => kendali.abort();
  }, [kdprov, kdkabSatu, meter]);

  const runs = data?.runs ?? (data?.run ? [data.run] : []);
  const total = data?.total ?? 0;
  const ukuranHalaman = batas === "semua" ? total : batas;
  const mulai = total === 0 ? 0 : halaman * ukuranHalaman + 1;
  const akhir = Math.min(total, (halaman + 1) * ukuranHalaman);
  const banyakKabupaten = kdkabs.length > 1;
  const jumlahGeser = runs.reduce((jumlah, satu) => jumlah + satu.jumlah_geser, 0);

  const labelKabupaten = useMemo(() => {
    const peta = new Map(opsi.map((satu) => [satu.kode, satu.nama]));
    return (kode: string | null) => (kode ? (peta.get(kode) ?? kode) : "–");
  }, [opsi]);

  function ubahBatas(nilai: UkuranHalaman) {
    setBatas(nilai);
    setHalaman(0);
  }

  function ubahKabupaten(nilai: string[]) {
    setKdkabs(nilai);
    setHalaman(0);
  }

  function ubahRiwayat(nilai: number | null) {
    setRunTerpilih(nilai);
    setHalaman(0);
  }

  function terapkanAmbang() {
    const angka = Number(meterDraf);
    if (!Number.isFinite(angka) || angka < AMBANG_BAWAAN) {
      setMeterDraf(String(meter));
      return;
    }
    setMeter(angka);
    setHalaman(0);
  }

  async function unduhExcel() {
    if (runs.length === 0) {
      return;
    }
    setMengunduh(true);
    setGalat(null);
    try {
      const isi = new URLSearchParams({ kdprov, min_meter: String(meter) });
      for (const kode of kdkabs) {
        isi.append("kdkab", kode);
      }
      if (kataKunci) {
        isi.set("q", kataKunci);
      }
      if (kdkabSatu && runTerpilih != null) {
        isi.set("run_b_id", String(runTerpilih));
      }
      await unduhBerkas(
        `/geser.xlsx?${isi}`,
        `pergeseran_${meter}m_${kdkabs.join("-")}.xlsx`,
      );
    } catch (kesalahan) {
      setGalat(pesanKesalahan(kesalahan));
    } finally {
      setMengunduh(false);
    }
  }

  return (
    <div className="space-y-field">
      <Panel
        judul="Pergeseran Titik"
        deskripsi="Titik yang sudah benar tetapi bergeser dari titik asal (Master GS). Ini bukan pencermatan: tidak perlu dikonfirmasi. Atur sendiri ambang meter yang ditampilkan (minimal 10 m); angka di bawah 10 m tidak pernah disimpan."
      >
        <div className="mt-3 grid gap-field sm:grid-cols-2 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1.4fr)_auto]">
          {kdkabAwal ? (
            <div>
              <span className="block text-sm font-medium text-ink">
                Kabupaten/kota
              </span>
              <span className="mt-label block min-h-9 text-sm font-medium text-muted">
                {opsi.find((satu) => satu.kode === kdkabAwal)?.nama ?? kdkabAwal}
              </span>
            </div>
          ) : (
            <MultiPilih
              label="Kabupaten/kota"
              labelSemua="Semua kabupaten/kota"
              tempatCari="Cari kode atau nama kabupaten..."
              opsi={opsi.map((satu) => ({
                nilai: satu.kode,
                label: `${satu.kode} · ${satu.nama}`,
              }))}
              terpilih={kdkabs}
              onTerapkan={ubahKabupaten}
            />
          )}

          <form
            className="text-sm font-medium text-ink"
            onSubmit={(kejadian) => {
              kejadian.preventDefault();
              terapkanAmbang();
            }}
          >
            <label htmlFor="ambang-geser" className="block">
              Ambang geser (meter)
            </label>
            <div className="mt-label flex gap-1.5">
              <input
                id="ambang-geser"
                type="number"
                min={AMBANG_BAWAAN}
                step={1}
                inputMode="numeric"
                value={meterDraf}
                onChange={(kejadian) => setMeterDraf(kejadian.target.value)}
                className="block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
              />
              <TombolAksi
                type="submit"
                varian="sekunder"
                className="min-h-9 px-2.5 text-xs"
                disabled={String(meter) === meterDraf}
              >
                Terapkan
              </TombolAksi>
            </div>
          </form>

          <div>
            <label
              htmlFor="riwayat-run"
              className="block text-sm font-medium text-ink"
            >
              Riwayat run
            </label>
            <select
              id="riwayat-run"
              value={
                kdkabSatu ? String(runTerpilih ?? riwayat[0]?.run_id ?? "") : ""
              }
              onChange={(kejadian) =>
                ubahRiwayat(
                  kejadian.target.value ? Number(kejadian.target.value) : null,
                )
              }
              disabled={!kdkabSatu || riwayat.length === 0}
              title={
                !kdkabSatu
                  ? "Pilih tepat satu kabupaten/kota untuk membuka riwayat run"
                  : undefined
              }
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            >
              {kdkabSatu && riwayat.length > 0 ? (
                riwayat.map((satu) => (
                  <option key={satu.run_id} value={satu.run_id}>
                    {`#${satu.run_id} · ${formatTanggal(satu.tanggal_data)} · ${formatAngka(
                      satu.jumlah_geser,
                    )} titik${satu.pengunggah ? ` · ${satu.pengunggah}` : ""}`}
                  </option>
                ))
              ) : (
                <option value="">
                  {kdkabSatu
                    ? "Run terakhir (otomatis)"
                    : "Run terakhir (semua kabupaten)"}
                </option>
              )}
            </select>
          </div>

          <form
            className="text-sm font-medium text-ink"
            onSubmit={(kejadian) => {
              kejadian.preventDefault();
              setHalaman(0);
              setKataKunci(cari.trim());
            }}
          >
            <span className="block">Cari</span>
            <div className="mt-label flex gap-1.5">
              <input
                type="search"
                value={cari}
                onChange={(kejadian) => setCari(kejadian.target.value)}
                placeholder="assignment_id / bangunan / kode"
                className="block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
              />
              <TombolAksi
                type="submit"
                varian="sekunder"
                className="min-h-9 px-2.5 text-xs"
              >
                Cari
              </TombolAksi>
            </div>
          </form>

          <div>
            <span
              aria-hidden="true"
              className="invisible block text-sm font-medium text-ink"
            >
              Unduh
            </span>
            <TombolAksi
              varian="sekunder"
              className="mt-label min-h-9 px-2.5 text-xs"
              onClick={() => void unduhExcel()}
              disabled={runs.length === 0 || mengunduh || total === 0}
              title={
                runs.length === 0
                  ? "Belum ada Proses B yang sukses"
                  : "Unduh pergeseran sesuai filter sebagai Excel"
              }
            >
              {mengunduh ? "Menyiapkan..." : "Unduh Excel"}
            </TombolAksi>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 text-xs text-muted">
          {runs.length === 1 ? (
            <>
              <span>
                Proses B <strong className="text-ink">#{runs[0].run_id}</strong> ·{" "}
                {formatTanggal(runs[0].tanggal_data)}
                {runs[0].pengunggah ? ` · ${runs[0].pengunggah}` : ""}
              </span>
              <span>
                Selesai{" "}
                <strong className="text-ink">{formatAngka(runs[0].selesai)}</strong>{" "}
                dari {formatAngka(runs[0].target)}
              </span>
            </>
          ) : null}
          {runs.length > 1 ? (
            <span>
              <strong className="text-ink">{formatAngka(runs.length)}</strong>{" "}
              kabupaten/kota dengan Proses B sukses
            </span>
          ) : null}
          <span className="font-medium text-ink">
            <strong className="font-bold">{formatAngka(total)}</strong> titik
            bergeser ≥ {formatAngka(meter)} m
            {total !== jumlahGeser && runs.length === 1
              ? ` · ${formatAngka(jumlahGeser)} di seluruh data tersimpan`
              : ""}
          </span>
        </div>

        {galat ? (
          <div
            role="alert"
            className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
          >
            {galat}
          </div>
        ) : null}

        {memuat && data == null ? (
          <div className="mt-3 space-y-2" aria-label="Memuat pergeseran titik">
            {[0, 1, 2, 3].map((baris) => (
              <div
                key={baris}
                className="h-11 animate-pulse rounded-lg bg-paper"
              />
            ))}
          </div>
        ) : null}

        {!memuat && data != null && runs.length === 0 ? (
          <EmptyState judul="Belum ada Proses B yang sukses">
            Pergeseran titik dihitung saat job Proses B selesai. Unggah titik
            hasil perbaikan untuk kabupaten/kota ini lebih dulu.
          </EmptyState>
        ) : null}

        {runs.length > 0 && data && data.baris.length === 0 ? (
          <EmptyState
            judul={
              meter > AMBANG_BAWAAN
                ? "Tidak ada titik yang bergeser sejauh itu"
                : "Tidak ada titik yang bergeser"
            }
          >
            {meter > AMBANG_BAWAAN
              ? "Turunkan ambang meter (minimal 10 m) untuk melihat pergeseran yang lebih pendek."
              : "Semua titik target cocok dengan titik asalnya (pergeseran <10 m atau tidak bergeser)."}
          </EmptyState>
        ) : null}

        {data && data.baris.length > 0 ? (
          <>
            <div className="mt-3 max-h-[70vh] overflow-auto rounded-lg border border-line">
              <table className="w-full min-w-[72rem] border-collapse text-[13px]">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted">
                    {banyakKabupaten ? (
                      <th className={`${KELAS_HEAD_KIRI} left-0`}>
                        Kabupaten/kota
                      </th>
                    ) : null}
                    <th className={KELAS_HEAD}>Assignment ID</th>
                    <th className={KELAS_HEAD}>Bangunan</th>
                    <th className={KELAS_HEAD}>level_6_fullcode Master GS</th>
                    <th className={KELAS_HEAD}>
                      level_6_fullcode Geotag Kabkot
                    </th>
                    <th className={KELAS_HEAD}>Wilayah</th>
                    <th className={KELAS_HEAD}>Latitude</th>
                    <th className={KELAS_HEAD}>Longitude</th>
                    <th className={KELAS_HEAD}>Jarak</th>
                    <th className={KELAS_HEAD}>Flag unggah / model</th>
                    <th className={KELAS_HEAD}>Keterangan</th>
                  </tr>
                </thead>
                <tbody>
                  {data.baris.map((baris, indeks) => (
                    <tr
                      key={`${baris.id ?? "x"}-${baris.kdkab}-${baris.assignment_id}-${indeks}`}
                      className="border-b border-line/70 last:border-0"
                    >
                      {banyakKabupaten ? (
                        <td className={KELAS_KIRI}>
                          {labelKabupaten(baris.kdkab)}
                        </td>
                      ) : null}
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-ink">
                        <span className="inline-flex items-center">
                          {teks(baris.assignment_id)}
                          <TombolSalin
                            nilai={baris.assignment_id}
                            label="Assignment ID"
                          />
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                        <span className="inline-flex items-center">
                          {teks(baris.unique_bang)}
                          <TombolSalin
                            nilai={baris.unique_bang}
                            label="ID bangunan"
                          />
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                        <span className="inline-flex items-center">
                          {teks(baris.level_6_full_code)}
                          <TombolSalin
                            nilai={baris.level_6_full_code}
                            label="kode SLS Master GS"
                          />
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                        <span className="inline-flex items-center">
                          {teks(baris.level_6_full_code_b)}
                          <TombolSalin
                            nilai={baris.level_6_full_code_b}
                            label="kode SLS Geotag Kabkot"
                          />
                        </span>
                      </td>
                      <td className="px-3 py-2 text-muted">{teks(baris.wilayah)}</td>
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                        {baris.latitude ?? "–"}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                        {baris.longitude ?? "–"}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-right font-semibold tabular-nums text-ink">
                        {teksJarak(baris.jarak_geser_m)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                        {baris.flag_unggah ?? "–"} / {baris.flag_model ?? "–"}
                      </td>
                      <td className="px-3 py-2 text-muted">
                        {teks(baris.keterangan)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span>
                  {formatAngka(mulai)}–{formatAngka(akhir)} dari{" "}
                  {formatAngka(total)}
                </span>
                <label className="flex items-center gap-1.5">
                  <span>Baris per halaman</span>
                  <select
                    value={batas === "semua" ? "semua" : String(batas)}
                    onChange={(kejadian) =>
                      ubahBatas(
                        kejadian.target.value === "semua"
                          ? "semua"
                          : Number(kejadian.target.value),
                      )
                    }
                    disabled={memuat}
                    className="min-h-8 rounded-lg border border-line-strong bg-surface px-2 py-1 text-xs text-ink disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {PILIHAN_BATAS.map((nilai) => (
                      <option key={nilai} value={nilai}>
                        {nilai}
                      </option>
                    ))}
                    <option value="semua">Semua</option>
                  </select>
                </label>
              </div>
              {batas === "semua" ? null : (
                <div className="flex gap-1.5">
                  <TombolAksi
                    varian="sekunder"
                    className="min-h-8 px-2.5 text-xs"
                    onClick={() => setHalaman((lama) => Math.max(0, lama - 1))}
                    disabled={halaman === 0 || memuat}
                  >
                    Sebelumnya
                  </TombolAksi>
                  <TombolAksi
                    varian="sekunder"
                    className="min-h-8 px-2.5 text-xs"
                    onClick={() => setHalaman((lama) => lama + 1)}
                    disabled={akhir >= total || memuat}
                  >
                    Berikutnya
                  </TombolAksi>
                </div>
              )}
            </div>
          </>
        ) : null}
      </Panel>
    </div>
  );
}
