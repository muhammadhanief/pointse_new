"use client";

import { useState } from "react";

import { TombolAksi } from "@/components/dashboard/ui";
import { pesanKesalahan, unduhBerkas } from "@/lib/api/klien";
import type { Run } from "@/lib/api/types";
import { kodeWilayah } from "@/lib/auth/peran";

export function UnduhanJob({ run }: { run: Run }) {
  const [sibuk, setSibuk] = useState<string | null>(null);
  const [galat, setGalat] = useState<string | null>(null);

  if (run.status !== "sukses") {
    return (
      <p className="mt-3 rounded-lg bg-paper px-3 py-2 text-sm leading-normal text-muted">
        Ekspor hanya tersedia untuk job yang sukses.
      </p>
    );
  }

  const kode = kodeWilayah(run.kdprov, run.kdkab);
  const nomor = run.nomor_urut ?? "?";
  const namaHasilA = `${kode}_hasil_identifikasi_titik_ke${nomor}.gpkg`;
  const namaHasilB = `${kode}_hasil_pengecekan_titik_ke${nomor}.gpkg`;
  const namaTitikCsv = `${kode}_titik_perlu_tindakan_ke${nomor}.csv`;
  const namaTitikGpkg = `${kode}_titik_perlu_tindakan_ke${nomor}.gpkg`;

  async function unduh(id: string, jalur: string, nama: string) {
    setGalat(null);
    setSibuk(id);
    try {
      await unduhBerkas(jalur, nama);
    } catch (galatUnduh) {
      setGalat(pesanKesalahan(galatUnduh));
    } finally {
      setSibuk(null);
    }
  }

  return (
    <div className="rounded-lg border border-line bg-paper p-kartu">
      <h3 className="text-sm font-semibold text-ink">Unduh hasil</h3>
      <div className="mt-2 flex flex-wrap gap-field">
        {run.tipe === "A" ? (
          <TombolAksi
            onClick={() =>
              void unduh(
                "hasil",
                `/runs/${run.id}/ekspor/hasil-a.gpkg`,
                namaHasilA,
              )
            }
            disabled={sibuk !== null}
          >
            {sibuk === "hasil" ? "Menyiapkan..." : "Hasil Peta (GPKG)"}
          </TombolAksi>
        ) : (
          <TombolAksi
            onClick={() =>
              void unduh(
                "hasil",
                `/runs/${run.id}/ekspor/hasil-b.gpkg`,
                namaHasilB,
              )
            }
            disabled={sibuk !== null}
          >
            {sibuk === "hasil" ? "Menyiapkan..." : "Hasil Pengecekan (GPKG)"}
          </TombolAksi>
        )}

        {run.detail_tersedia ? (
          <>
            <TombolAksi
              varian="sekunder"
              onClick={() =>
                void unduh(
                  "csv",
                  `/runs/${run.id}/ekspor/titik.csv`,
                  namaTitikCsv,
                )
              }
              disabled={sibuk !== null}
            >
              {sibuk === "csv" ? "Menyiapkan..." : "Titik perlu tindakan (CSV)"}
            </TombolAksi>
            <TombolAksi
              varian="sekunder"
              onClick={() =>
                void unduh(
                  "gpkg",
                  `/runs/${run.id}/ekspor/titik.gpkg`,
                  namaTitikGpkg,
                )
              }
              disabled={sibuk !== null}
            >
              {sibuk === "gpkg"
                ? "Menyiapkan..."
                : "Titik perlu tindakan (GPKG)"}
            </TombolAksi>
          </>
        ) : (
          <p className="text-sm leading-normal text-muted">
            Detail titik job ini sudah dipangkas. Rekap tetap bisa diunduh
            lewat menu Ekspor rekap.
          </p>
        )}
      </div>

      {galat ? (
        <p
          role="alert"
          className="mt-2 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger"
        >
          {galat}
        </p>
      ) : null}

      <p className="mt-2 text-xs leading-5 text-muted">
        Jika server membalas 409, berkas mentah atau detail titik job ini sudah
        tidak tersedia.
      </p>
    </div>
  );
}
