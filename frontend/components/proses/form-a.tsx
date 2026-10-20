"use client";

import { useState, type FormEvent } from "react";

import { Panel, TombolAksi } from "@/components/dashboard/ui";
import { BidangBerkas } from "@/components/unggah/bidang-berkas";
import { CatatanUnggah } from "@/components/unggah/catatan";
import { PesanUnggah } from "@/components/unggah/pesan";
import { ProgresUnggahan } from "@/components/unggah/progres";
import { useUnggah } from "@/components/unggah/use-unggah";
import { ambilJson, buatFormUrlEncoded } from "@/lib/api/klien";
import type { Run } from "@/lib/api/types";
import { labelNomorJob } from "@/lib/istilah";

export function FormProsesA({ onSelesai }: { onSelesai: () => void }) {
  const [peta, setPeta] = useState<File | null>(null);
  const [tanggal, setTanggal] = useState("");
  const [layer, setLayer] = useState("");
  const [kunciBerkas, setKunciBerkas] = useState(0);
  const { status, progres, pesan, data, unggah, batal, reset } =
    useUnggah<Run>();
  const sedang = status === "mengunggah";

  function pilihPeta(berkas: File | null) {
    setPeta(berkas);
    reset();
  }

  async function kirim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!peta || sedang) {
      return;
    }

    const hasil = await unggah({
      jenis: "peta",
      berkas: peta,
      proses: (unggahan, signal) =>
        ambilJson<Run>("/runs", {
          method: "POST",
          body: buatFormUrlEncoded({
            tipe: "A",
            unggahan_id: unggahan.unggahan_id,
            tanggal_data: tanggal || undefined,
            layer_peta: layer.trim() || undefined,
          }),
          signal,
        }),
    });
    onSelesai();

    if (hasil) {
      setPeta(null);
      setTanggal("");
      setLayer("");
      setKunciBerkas((nilai) => nilai + 1);
    }
  }

  return (
    <Panel
      judul="1. Identifikasi Titik"
      deskripsi="Unggah peta batas Wilkerstat. Backend memakai geotag master terbaru untuk kabupaten/kota yang terdeteksi dari peta."
    >
      <form onSubmit={kirim} className="mt-5 space-y-5" aria-busy={sedang}>
        <BidangBerkas
          key={kunciBerkas}
          id="peta-proses-a"
          label="Berkas peta Wilkerstat"
          accept=".geojson,.json,.gpkg,application/geo+json,application/geopackage+sqlite3"
          berkas={peta}
          onPilih={pilihPeta}
          keterangan="GeoJSON atau GPKG. Satu berkas hanya boleh memuat satu kabupaten/kota."
          disabled={sedang}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="tanggal-proses-a"
              className="text-sm font-medium text-ink"
            >
              Tanggal data (opsional)
            </label>
            <input
              id="tanggal-proses-a"
              type="date"
              value={tanggal}
              disabled={sedang}
              onChange={(event) => setTanggal(event.target.value)}
              className="mt-2 block min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1.5 text-xs leading-5 text-muted">
              Kosongkan untuk memakai tanggal data master geotag.
            </p>
          </div>

          <div>
            <label
              htmlFor="layer-proses-a"
              className="text-sm font-medium text-ink"
            >
              Layer peta (opsional)
            </label>
            <input
              id="layer-proses-a"
              type="text"
              value={layer}
              disabled={sedang}
              autoComplete="off"
              onChange={(event) => setLayer(event.target.value)}
              className="mt-2 block min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-1.5 text-xs leading-5 text-muted">
              Isi bila berkas punya beberapa layer.
            </p>
          </div>
        </div>

        <p className="rounded-lg bg-paper px-4 py-3 text-xs leading-5 text-muted">
          Bila master geotag belum ada, unggahan ditolak dengan pesan 409.
          Admin provinsi menyiapkannya lewat menu Master geotag.
        </p>

        <CatatanUnggah />

        <TombolAksi type="submit" disabled={!peta || sedang}>
          Unggah dan antrekan
        </TombolAksi>

        <ProgresUnggahan status={status} progres={progres} onBatal={batal} />

        <PesanUnggah status={status} pesan={pesan}>
          {data
            ? `1. Identifikasi Titik masuk antrean (${labelNomorJob(
                data.nomor_urut,
              )}). Pantau statusnya di riwayat job.`
            : "1. Identifikasi Titik berhasil diantrekan."}
        </PesanUnggah>
      </form>
    </Panel>
  );
}
