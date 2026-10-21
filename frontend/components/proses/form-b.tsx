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

export function FormProsesB({ onSelesai }: { onSelesai?: () => void }) {
  const [titik, setTitik] = useState<File | null>(null);
  const [kunciBerkas, setKunciBerkas] = useState(0);
  const { status, progres, pesan, data, unggah, batal, reset } =
    useUnggah<Run>();
  const sedang = status === "mengunggah";

  function pilihTitik(berkas: File | null) {
    setTitik(berkas);
    reset();
  }

  async function kirim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!titik || sedang) {
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
          }),
          signal,
        }),
    });
    onSelesai?.();

    if (hasil) {
      setTitik(null);
      setKunciBerkas((nilai) => nilai + 1);
    }
  }

  return (
    <Panel>
      <form onSubmit={kirim} className="space-y-field" aria-busy={sedang}>
        <BidangBerkas
          key={kunciBerkas}
          id="titik-proses-b"
          label="Berkas GPKG/GeoJSON hasil edit"
          accept=".gpkg,.geojson,.json,application/geopackage+sqlite3,application/geo+json,application/json"
          berkas={titik}
          onPilih={pilihTitik}
          keterangan="Gunakan GPKG atau GeoJSON keluaran Peta SLS/SubSLS Final yang sudah diedit di QGIS. Pastikan CRS tetap sama."
          disabled={sedang}
        />

        <CatatanUnggah />

        <TombolAksi type="submit" disabled={!titik || sedang}>
          Unggah dan antrekan
        </TombolAksi>

        <ProgresUnggahan status={status} progres={progres} onBatal={batal} />

        <PesanUnggah status={status} pesan={pesan}>
          {data ? (
            <>
              {`Unggahan titik hasil perbaikan masuk antrean (${labelNomorJob(
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
            "Unggahan titik hasil perbaikan berhasil diantrekan."
          )}
        </PesanUnggah>
      </form>
    </Panel>
  );
}
