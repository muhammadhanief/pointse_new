"use client";

import Link from "next/link";
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

export function FormProsesA({ onSelesai }: { onSelesai?: () => void }) {
  const [peta, setPeta] = useState<File | null>(null);
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
          }),
          signal,
        }),
    });
    onSelesai?.();

    if (hasil) {
      setPeta(null);
      setKunciBerkas((nilai) => nilai + 1);
    }
  }

  return (
    <Panel>
      <form onSubmit={kirim} className="space-y-field" aria-busy={sedang}>
        <BidangBerkas
          key={kunciBerkas}
          id="peta-proses-a"
          label="Peta SLS/SubSLS Final Kabupaten/Kota"
          accept=".geojson,.json,.gpkg,application/geo+json,application/geopackage+sqlite3"
          berkas={peta}
          onPilih={pilihPeta}
          keterangan="GeoJSON atau GPKG. Berkas harus Full 1 Kabupaten/Kota."
          disabled={sedang}
        />

        <CatatanUnggah />

        <TombolAksi type="submit" disabled={!peta || sedang}>
          Unggah dan antrekan
        </TombolAksi>

        <ProgresUnggahan status={status} progres={progres} onBatal={batal} />

        <PesanUnggah status={status} pesan={pesan}>
          {data ? (
            <>
              {`Unggahan peta masuk antrean (${labelNomorJob(
                data.nomor_urut,
              )}).`}{" "}
              Pantau statusnya di{" "}
              <Link
                href="/riwayat"
                className="font-semibold underline underline-offset-4"
              >
                Riwayat upload
              </Link>
              .
            </>
          ) : (
            "Unggahan peta berhasil diantrekan."
          )}
        </PesanUnggah>
      </form>
    </Panel>
  );
}
