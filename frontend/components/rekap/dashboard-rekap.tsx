"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  BarProgres,
  EmptyState,
  Panel,
  TautanAksi,
  TombolAksi,
} from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
  unduhBerkas,
} from "@/lib/api/klien";
import type {
  Rekap,
  RekapDetail,
  Ringkasan,
  RingkasanBaris,
  TipeRun,
} from "@/lib/api/types";
import { formatAngka, formatTanggal } from "@/lib/format";
import { labelTipe } from "@/lib/istilah";
import { labelKabupaten } from "@/lib/wilayah/kabupaten";

type Dasar = "tugas" | "posisi";
type Tingkat = "kabupaten" | "kecamatan" | "desa" | "sls" | "subsls";

const TINGKAT: { nilai: Tingkat; label: string }[] = [
  { nilai: "kabupaten", label: "Kabupaten/kota" },
  { nilai: "kecamatan", label: "Kecamatan" },
  { nilai: "desa", label: "Desa" },
  { nilai: "sls", label: "SLS" },
  { nilai: "subsls", label: "SubSLS" },
];

function persen(belum: number, ditindak: number): number | null {
  const total = belum + ditindak;
  return total > 0 ? Math.round((ditindak / total) * 1000) / 10 : null;
}

function Progres({ nilai }: { nilai: number | null }) {
  return nilai == null ? (
    <span className="text-muted">-</span>
  ) : (
    <BarProgres nilai={Math.round(nilai)} />
  );
}

function pilihTipe(baris: RingkasanBaris, tipe: TipeRun) {
  return baris.terakhir.find((satu) => satu.tipe === tipe) ?? null;
}

export function DashboardRekap() {
  const [tipe, setTipe] = useState<TipeRun>("A");
  const [dasar, setDasar] = useState<Dasar>("tugas");
  const [ringkasan, setRingkasan] = useState<RingkasanBaris[]>([]);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [cari, setCari] = useState("");

  const [pilihan, setPilihan] = useState<RingkasanBaris | null>(null);
  const [tingkat, setTingkat] = useState<Tingkat>("desa");
  const [detail, setDetail] = useState<Rekap | RekapDetail | null>(null);
  const [memuatDetail, setMemuatDetail] = useState(false);
  const [galatDetail, setGalatDetail] = useState<string | null>(null);
  const [mengunduh, setMengunduh] = useState(false);

  const controllerRef = useRef<AbortController | null>(null);
  const controllerDetailRef = useRef<AbortController | null>(null);

  const muatRingkasan = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setMemuat(true);
    setGalat(null);
    try {
      const data = await ambilJson<Ringkasan>(
        `/ringkasan?tipe=${encodeURIComponent(tipe)}&dasar=${dasar}`,
        { signal: controller.signal },
      );
      setRingkasan(data.baris);
      setPilihan(null);
      setDetail(null);
    } catch (kesalahan) {
      if (!adalahBatal(kesalahan)) {
        setGalat(pesanKesalahan(kesalahan));
      }
    } finally {
      if (!controller.signal.aborted) {
        setMemuat(false);
      }
    }
  }, [tipe, dasar]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void muatRingkasan();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controllerRef.current?.abort();
    };
  }, [muatRingkasan]);

  const muatDetail = useCallback(async () => {
    if (!pilihan) {
      setDetail(null);
      return;
    }
    const run = pilihTipe(pilihan, tipe);
    if (!run) {
      setDetail(null);
      return;
    }
    controllerDetailRef.current?.abort();
    const controller = new AbortController();
    controllerDetailRef.current = controller;
    setMemuatDetail(true);
    setGalatDetail(null);
    try {
      const data = await ambilJson<Rekap | RekapDetail>(
        `/runs/${run.run_id}/rekap?tingkat=${tingkat}&dasar=${dasar}`,
        { signal: controller.signal },
      );
      setDetail(data);
    } catch (kesalahan) {
      if (!adalahBatal(kesalahan)) {
        setGalatDetail(pesanKesalahan(kesalahan));
        setDetail(null);
      }
    } finally {
      if (!controller.signal.aborted) {
        setMemuatDetail(false);
      }
    }
  }, [pilihan, tipe, tingkat, dasar]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void muatDetail();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controllerDetailRef.current?.abort();
    };
  }, [muatDetail]);

  const total = useMemo(() => {
    let belum = 0;
    let ditindak = 0;
    let kabupaten = 0;
    for (const baris of ringkasan) {
      const angka = pilihTipe(baris, tipe);
      if (!angka) continue;
      kabupaten += 1;
      belum += angka.belum;
      ditindak += angka.ditindak;
    }
    return { belum, ditindak, kabupaten, persen: persen(belum, ditindak) };
  }, [ringkasan, tipe]);

  const tersaring = useMemo(() => {
    const kunci = cari.trim().toLowerCase();
    if (!kunci) return ringkasan;
    return ringkasan.filter((baris) =>
      [baris.kdprov, baris.kdkab, baris.nmprov, baris.nmkab, labelKabupaten(baris.kdprov, baris.kdkab)]
        .filter(Boolean)
        .some((nilai) => String(nilai).toLowerCase().includes(kunci)),
    );
  }, [ringkasan, cari]);

  async function unduh(tingkatUnduh: "kabupaten" | "desa") {
    setMengunduh(true);
    try {
      await unduhBerkas(
        `/ekspor/rekap.csv?tingkat=${tingkatUnduh}&tipe=${tipe}&dasar=${dasar}`,
        `rekap-${tingkatUnduh}-${dasar}.csv`,
      );
    } catch (kesalahan) {
      setGalatDetail(pesanKesalahan(kesalahan));
    } finally {
      setMengunduh(false);
    }
  }

  const detailRamping = detail !== null && "ditindak" in detail;
  const bolehEksporDetail =
    pilihan !== null && (tingkat === "kabupaten" || tingkat === "desa");

  return (
    <div className="space-y-field">
      <Panel
        judul="Saringan rekap"
        deskripsi="Angka di bawah berasal dari run sukses terakhir tiap kabupaten/kota. Pilih baris untuk melihat rincian wilayah."
      >
        <div className="mt-3 grid gap-field sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-sm font-medium text-ink">
            Proses
            <select
              value={tipe}
              onChange={(event) => setTipe(event.target.value as TipeRun)}
              className="mt-1 min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              <option value="A">{labelTipe("A")}</option>
              <option value="B">{labelTipe("B")}</option>
            </select>
          </label>
          <label className="text-sm font-medium text-ink">
            Dasar wilayah
            <select
              value={dasar}
              onChange={(event) => setDasar(event.target.value as Dasar)}
              className="mt-1 min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              <option value="tugas">Wilayah penugasan</option>
              <option value="posisi">Posisi titik</option>
            </select>
          </label>
          <label className="text-sm font-medium text-ink">
            Tingkat rincian
            <select
              value={tingkat}
              onChange={(event) => setTingkat(event.target.value as Tingkat)}
              className="mt-1 min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              {TINGKAT.map((satu) => (
                <option key={satu.nilai} value={satu.nilai}>
                  {satu.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium text-ink">
            Cari kabupaten/kota
            <input
              value={cari}
              onChange={(event) => setCari(event.target.value)}
              placeholder="Nama atau kode"
              className="mt-1 min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-field">
          <TombolAksi
            varian="sekunder"
            disabled={mengunduh || memuat}
            onClick={() => void unduh("kabupaten")}
          >
            {mengunduh ? "Menyiapkan…" : "Ekspor rekap kabupaten"}
          </TombolAksi>
          <TombolAksi
            varian="sekunder"
            disabled={mengunduh || memuat}
            onClick={() => void unduh("desa")}
          >
            Ekspor rekap desa
          </TombolAksi>
          <TombolAksi varian="sekunder" onClick={() => void muatRingkasan()}>
            Muat ulang
          </TombolAksi>
        </div>
      </Panel>

      {galat ? (
        <div
          role="alert"
          className="rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
        >
          {galat}
        </div>
      ) : null}

      <div className="grid gap-field sm:grid-cols-2 lg:grid-cols-4">
        <RingkasanKartu label="Kabupaten/kota" nilai={formatAngka(total.kabupaten)} />
        <RingkasanKartu label="Belum" nilai={formatAngka(total.belum)} />
        <RingkasanKartu label="Ditindak" nilai={formatAngka(total.ditindak)} />
        <RingkasanKartu
          label="Progres"
          nilai={total.persen == null ? "-" : `${formatAngka(total.persen)}%`}
        />
      </div>

      <Panel
        judul="Progres per kabupaten/kota"
        deskripsi="Klik rincian pada baris untuk melihat kecamatan, desa, SLS, atau SubSLS dari run terakhir kabupaten/kota tersebut."
      >
        {memuat ? (
          <p className="mt-3 text-sm text-muted">Memuat rekap…</p>
        ) : tersaring.length === 0 ? (
          <EmptyState
            judul="Belum ada rekap"
            aksi={
              <TautanAksi href="/unggah" varian="sekunder">
                Buka halaman unggah
              </TautanAksi>
            }
          >
            Rekap muncul setelah ada job yang selesai diproses dengan proses dan
            dasar wilayah ini.
          </EmptyState>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th className="py-2 pl-3 pr-3 font-semibold">Kabupaten/kota</th>
                  <th className="py-2 pr-3 font-semibold">Tanggal data</th>
                  <th className="py-2 pr-3 text-right font-semibold">Belum</th>
                  <th className="py-2 pr-3 text-right font-semibold">Ditindak</th>
                  <th className="py-2 pr-3 text-right font-semibold">Progres</th>
                  <th className="py-2 text-right font-semibold">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {tersaring.map((baris) => {
                  const angka = pilihTipe(baris, tipe);
                  const terpilih =
                    pilihan?.kdprov === baris.kdprov &&
                    pilihan?.kdkab === baris.kdkab;
                  return (
                    <tr
                      key={`${baris.kdprov}-${baris.kdkab}`}
                      className={`border-b border-line/70 last:border-0 ${
                        terpilih ? "bg-brand-soft/40" : ""
                      }`}
                    >
                      <td className="py-2 pl-3 pr-3">
                        <p className="font-medium text-ink">
                          {baris.nmkab || labelKabupaten(baris.kdprov, baris.kdkab)}
                        </p>
                        <p className="text-xs text-muted">
                          {baris.kdprov}.{baris.kdkab}
                        </p>
                      </td>
                      <td className="py-2 pr-3 text-muted">
                        {angka ? formatTanggal(angka.tanggal_data) : "-"}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {angka ? formatAngka(angka.belum) : "-"}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {angka ? formatAngka(angka.ditindak) : "-"}
                      </td>
                      <td className="py-2 pr-3 text-right">
                        <Progres nilai={angka?.persen_progres ?? null} />
                      </td>
                      <td className="py-2 text-right">
                        <TombolAksi
                          varian="sekunder"
                          className="min-h-9 px-tombol"
                          disabled={!angka}
                          onClick={() => setPilihan(baris)}
                        >
                          Rincian
                        </TombolAksi>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {pilihan ? (
        <Panel
          judul={`Rincian ${pilihan.nmkab || labelKabupaten(pilihan.kdprov, pilihan.kdkab)}`}
          deskripsi={`Run ${pilihTipe(pilihan, tipe)?.run_id ?? "-"} · ${labelTipe(tipe)} · dasar ${dasar}`}
        >
          <div className="mt-1 flex flex-wrap items-center gap-field">
            <TombolAksi
              varian="sekunder"
              disabled={mengunduh || !bolehEksporDetail}
              onClick={() => void unduh(tingkat === "kabupaten" ? "kabupaten" : "desa")}
            >
              Ekspor rincian
            </TombolAksi>
            {!bolehEksporDetail ? (
              <p className="text-xs leading-5 text-muted">
                Ekspor rincian tersedia untuk tingkat kabupaten dan desa.
              </p>
            ) : null}
            <TombolAksi
              varian="sekunder"
              onClick={() => {
                setPilihan(null);
                setDetail(null);
              }}
            >
              Tutup
            </TombolAksi>
          </div>

          {galatDetail ? (
            <div
              role="alert"
              className="mt-1 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
            >
              {galatDetail}
            </div>
          ) : memuatDetail ? (
            <p className="mt-3 text-sm text-muted">Memuat rincian…</p>
          ) : detail ? (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                    <th className="py-2 pl-3 pr-3 font-semibold">Wilayah</th>
                    {detailRamping ? (
                      <>
                        <th className="py-2 pr-3 text-right font-semibold">Belum</th>
                        <th className="py-2 pr-3 text-right font-semibold">Ditindak</th>
                      </>
                    ) : (
                      <>
                        <th className="py-2 pr-3 text-right font-semibold">Jumlah</th>
                        <th className="py-2 pr-3 text-right font-semibold">Belum</th>
                        <th className="py-2 pr-3 text-right font-semibold">Benar awal</th>
                        <th className="py-2 pr-3 text-right font-semibold">Tindak benar</th>
                        <th className="py-2 pr-3 text-right font-semibold">Tindak salah</th>
                        <th className="py-2 pr-3 text-right font-semibold">Digeser</th>
                        <th className="py-2 pr-3 text-right font-semibold">Tanpa wilayah</th>
                      </>
                    )}
                    <th className="py-2 text-right font-semibold">Progres</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.baris.map((baris, nomor) => (
                    <tr
                      key={`${baris.kode ?? "tanpa"}-${nomor}`}
                      className="border-b border-line/70 last:border-0"
                    >
                      <td className="py-2 pl-3 pr-3">
                        <p className="font-medium text-ink">
                          {baris.nama || "(tanpa wilayah)"}
                        </p>
                        <p className="text-xs text-muted">{baris.kode || "-"}</p>
                      </td>
                      {detailRamping ? (
                        <>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka("belum" in baris ? baris.belum : null)}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka("ditindak" in baris ? baris.ditindak : null)}
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka("jumlah" in baris ? baris.jumlah : null)}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka("belum" in baris ? baris.belum : null)}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka("benar_awal" in baris ? baris.benar_awal : null)}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka(
                              "ditindak_posisi_benar" in baris
                                ? baris.ditindak_posisi_benar
                                : null,
                            )}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka(
                              "ditindak_posisi_salah" in baris
                                ? baris.ditindak_posisi_salah
                                : null,
                            )}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka("digeser" in baris ? baris.digeser : null)}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatAngka(
                              "tanpa_wilayah" in baris ? baris.tanpa_wilayah : null,
                            )}
                          </td>
                        </>
                      )}
                      <td className="py-2 text-right">
                        <Progres nilai={baris.persen_progres} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-3 text-sm text-muted">Tidak ada rincian untuk saringan ini.</p>
          )}
        </Panel>
      ) : null}
    </div>
  );
}

function RingkasanKartu({ label, nilai }: { label: string; nilai: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-kartu">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">
        {label}
      </p>
      <p className="mt-1 font-display text-2xl font-semibold tabular-nums text-ink">
        {nilai}
      </p>
    </div>
  );
}
