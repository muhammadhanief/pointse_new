"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Panel, TombolAksi } from "@/components/dashboard/ui";
import { BidangBerkas } from "@/components/unggah/bidang-berkas";
import { CatatanUnggah } from "@/components/unggah/catatan";
import { PesanUnggah } from "@/components/unggah/pesan";
import { ProgresUnggahan } from "@/components/unggah/progres";
import { useUnggah } from "@/components/unggah/use-unggah";
import { ambilJson, buatFormUrlEncoded } from "@/lib/api/klien";
import { formatTanggal } from "@/lib/format";
import type { Run } from "@/lib/api/types";
import { labelNomorJob, labelTipe } from "@/lib/istilah";
import { labelKabupaten } from "@/lib/wilayah/kabupaten";

export function FormProsesB({
  onSelesai,
  sumberA,
  memuatSumberA,
  galatSumberA,
}: {
  onSelesai: () => void;
  sumberA: Run[];
  memuatSumberA: boolean;
  galatSumberA: string | null;
}) {
  const [titik, setTitik] = useState<File | null>(null);
  const [sumberId, setSumberId] = useState("");
  const [tanggal, setTanggal] = useState("");
  const [layer, setLayer] = useState("");
  const [kunciBerkas, setKunciBerkas] = useState(0);
  const { status, progres, pesan, data, unggah, batal, reset } =
    useUnggah<Run>();
  const sedang = status === "mengunggah";
  const tidakAdaSumber = !memuatSumberA && sumberA.length === 0;
  const sumber = sumberA.find((run) => String(run.id) === sumberId) ?? null;

  useEffect(() => {
    if (sumberA.length === 0) {
      setSumberId("");
      return;
    }
    if (!sumberA.some((run) => String(run.id) === sumberId)) {
      setSumberId(String(sumberA[0].id));
    }
  }, [sumberA, sumberId]);

  function pilihTitik(berkas: File | null) {
    setTitik(berkas);
    reset();
  }

  async function kirim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!titik || sedang || tidakAdaSumber || !sumberId) {
      return;
    }

    const hasil = await unggah({
      jenis: "titik",
      berkas: titik,
      proses: (unggahan, signal) =>
        ambilJson<Run>("/runs", {
          method: "POST",
          body: buatFormUrlEncoded({
            tipe: "B",
            unggahan_id: unggahan.unggahan_id,
            sumber_run_a_id: sumberId,
            tanggal_data: tanggal || undefined,
            layer_titik: layer.trim() || undefined,
          }),
          signal,
        }),
    });
    onSelesai();

    if (hasil) {
      setTitik(null);
      setTanggal("");
      setLayer("");
      setKunciBerkas((nilai) => nilai + 1);
    }
  }

  return (
    <Panel
      judul="2. Pengecekan Titik"
      deskripsi="Pilih hasil 1. Identifikasi Titik yang menjadi sumber peta, lalu unggah GPKG hasil edit dari QGIS."
    >
      <div className="mt-5 rounded-lg border border-line bg-paper p-4">
        <label
          htmlFor="sumber-proses-b"
          className="text-sm font-semibold text-ink"
        >
          Sumber peta
        </label>

        {memuatSumberA ? (
          <p className="mt-1 text-sm leading-6 text-muted">
            Memeriksa daftar hasil 1. Identifikasi Titik...
          </p>
        ) : sumberA.length > 0 ? (
          <>
            <select
              id="sumber-proses-b"
              value={sumberId}
              disabled={sedang || memuatSumberA}
              onChange={(event) => setSumberId(event.target.value)}
              className="mt-2 block min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="" disabled>
                Pilih 1. Identifikasi Titik
              </option>
              {sumberA.map((run) => (
                <option key={run.id} value={run.id}>
                  {labelTipe("A")} ·{" "}
                  {labelKabupaten(run.kdprov, run.kdkab)} ·{" "}
                  {labelNomorJob(run.nomor_urut)} ·{" "}
                  {formatTanggal(run.tanggal_data)}
                </option>
              ))}
            </select>
            {sumber ? (
              <p className="mt-2 text-xs leading-5 text-muted">
                Dipilih: {labelTipe("A")} ·{" "}
                {labelKabupaten(sumber.kdprov, sumber.kdkab)} ·{" "}
                {labelNomorJob(sumber.nomor_urut)}, tanggal data{" "}
                {formatTanggal(sumber.tanggal_data)}. Berkas pengecekan harus
                berasal dari kabupaten/kota yang sama.
              </p>
            ) : null}
            {galatSumberA ? (
              <p className="mt-2 text-xs leading-5 text-danger" role="alert">
                Daftar sumber mungkin sudah lama: {galatSumberA}
              </p>
            ) : null}
          </>
        ) : (
          <p className="mt-1 text-sm leading-6 text-danger">
            {galatSumberA ??
              "Belum ada hasil 1. Identifikasi Titik. Jalankan langkah 1 lebih dulu."}
          </p>
        )}

        <p className="mt-2 text-xs leading-5 text-muted">
          Peta disalin dari hasil 1. Identifikasi Titik yang dipilih. Tidak
          perlu mengunggah peta lagi.
        </p>
      </div>

      <form onSubmit={kirim} className="mt-5 space-y-5" aria-busy={sedang}>
        <BidangBerkas
          key={kunciBerkas}
          id="titik-proses-b"
          label="Berkas GPKG hasil edit"
          accept=".gpkg,application/geopackage+sqlite3"
          berkas={titik}
          onPilih={pilihTitik}
          keterangan="Gunakan GPKG keluaran 1. Identifikasi Titik yang sudah diedit di QGIS."
          disabled={sedang}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="tanggal-proses-b"
              className="text-sm font-medium text-ink"
            >
              Tanggal data (opsional)
            </label>
            <input
              id="tanggal-proses-b"
              type="date"
              value={tanggal}
              disabled={sedang}
              onChange={(event) => setTanggal(event.target.value)}
              className="mt-2 block min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1.5 text-xs leading-5 text-muted">
              Kosongkan untuk memakai tanggal unggah.
            </p>
          </div>

          <div>
            <label
              htmlFor="layer-proses-b"
              className="text-sm font-medium text-ink"
            >
              Layer titik (opsional)
            </label>
            <input
              id="layer-proses-b"
              type="text"
              value={layer}
              disabled={sedang}
              autoComplete="off"
              onChange={(event) => setLayer(event.target.value)}
              className="mt-2 block min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1.5 text-xs leading-5 text-muted">
              Isi bila GPKG punya beberapa layer.
            </p>
          </div>
        </div>

        <CatatanUnggah />

        <TombolAksi
          type="submit"
          disabled={!titik || sedang || tidakAdaSumber || !sumberId}
        >
          Unggah dan antrekan
        </TombolAksi>

        <ProgresUnggahan status={status} progres={progres} onBatal={batal} />

        <PesanUnggah status={status} pesan={pesan}>
          {data
            ? `2. Pengecekan Titik masuk antrean (${labelNomorJob(
                data.nomor_urut,
              )}).${
                sumber
                  ? ` Sumber peta: 1. Identifikasi Titik (${labelNomorJob(
                      sumber.nomor_urut,
                    )}).`
                  : ""
              } Pantau statusnya di riwayat job.`
            : "2. Pengecekan Titik berhasil diantrekan."}
        </PesanUnggah>
      </form>
    </Panel>
  );
}
