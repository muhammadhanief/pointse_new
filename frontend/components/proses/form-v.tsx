"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Panel, TautanAksi, TombolAksi } from "@/components/dashboard/ui";
import { Modal } from "@/components/dashboard/modal";
import { BidangBerkas } from "@/components/unggah/bidang-berkas";
import { CatatanUnggah } from "@/components/unggah/catatan";
import { PesanUnggah } from "@/components/unggah/pesan";
import { ProgresUnggahan } from "@/components/unggah/progres";
import { useUnggah } from "@/components/unggah/use-unggah";
import { ambilJson, buatFormUrlEncoded } from "@/lib/api/klien";
import type { Run } from "@/lib/api/types";
import { labelNomorJob } from "@/lib/istilah";
import { KOLOM_PETA_VALIDASI } from "@/lib/validasi/kolom";

export function FormProsesV({ onSelesai }: { onSelesai?: () => void }) {
  const [peta, setPeta] = useState<File | null>(null);
  const [kunciBerkas, setKunciBerkas] = useState(0);
  const [notifikasi, setNotifikasi] = useState(false);
  const [bukaKolom, setBukaKolom] = useState(false);
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
            tipe: "V",
            unggahan_id: unggahan.unggahan_id,
          }),
          signal,
        }),
    });
    onSelesai?.();

    if (hasil) {
      setPeta(null);
      setKunciBerkas((nilai) => nilai + 1);
      setNotifikasi(true);
    }
  }

  return (
    <Panel>
      <form onSubmit={kirim} className="space-y-field" aria-busy={sedang}>
        <BidangBerkas
          key={kunciBerkas}
          id="peta-proses-v"
          label="Peta SLS/SubSLS 2026 Semester 1 Kabupaten/Kota"
          accept=".geojson,.json,.gpkg,application/geo+json,application/geopackage+sqlite3"
          berkas={peta}
          onPilih={pilihPeta}
          keterangan="GeoJSON atau GPKG. Berkas harus Full 1 Kabupaten/Kota, 17 kolom sesuai dokumen Validasi Atribut."
          disabled={sedang}
        />

        <CatatanUnggah />

        <div>
          <button
            type="button"
            onClick={() => setBukaKolom(true)}
            aria-haspopup="dialog"
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-sm font-semibold text-brand-strong transition-colors hover:border-brand hover:bg-brand-soft/40"
          >
            <span aria-hidden="true" className="text-base leading-none">ⓘ</span>
            Lihat 17 kolom wajib + tipe datanya
          </button>
        </div>

        <TombolAksi type="submit" disabled={!peta || sedang}>
          Unggah dan validasi
        </TombolAksi>

        <ProgresUnggahan status={status} progres={progres} onBatal={batal} />

        <PesanUnggah status={status} pesan={pesan}>
          {data ? (
            <>
              {`Validasi masuk antrean (${labelNomorJob(data.nomor_urut)}).`}{" "}
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
            "Validasi berhasil diantrekan."
          )}
        </PesanUnggah>
      </form>

      <Modal
        terbuka={bukaKolom}
        judul="17 kolom wajib peta SLS 2026 Semester 1"
        onTutup={() => setBukaKolom(false)}
      >
        <p className="text-sm leading-normal text-muted">
          Nama kolom harus persis seperti di bawah (huruf kecil semua).
          Panjang = jumlah karakter maksimum; baris yang melebihi batas
          ditolak saat validasi.
        </p>
        <table className="mt-3 w-full border-collapse text-sm">
          <caption className="sr-only">
            Daftar kolom wajib beserta tipe data dan panjang maksimum
          </caption>
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted">
              <th scope="col" className="border-b border-line px-2 py-1.5">Kolom</th>
              <th scope="col" className="border-b border-line px-2 py-1.5">Tipe data</th>
              <th scope="col" className="border-b border-line px-2 py-1.5 text-right">Panjang maks</th>
            </tr>
          </thead>
          <tbody>
            {KOLOM_PETA_VALIDASI.map((satu) => (
              <tr key={satu.nama} className="border-b border-line/70 last:border-0">
                <td className="px-2 py-1.5 font-mono text-xs text-ink">{satu.nama}</td>
                <td className="px-2 py-1.5 text-muted">{satu.tipe}</td>
                <td className="px-2 py-1.5 text-right tabular-nums text-ink">{satu.panjang}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Modal>

      <Modal
        terbuka={notifikasi}
        judul="Peta SLS 2026 Semester 1 Berhasil Diunggah"
        onTutup={() => setNotifikasi(false)}
      >
        <div className="space-y-field">
          <p className="text-sm leading-normal text-ink">
            Berkas masuk antrean validasi. Hasil lolos/gagal tercatat di
            riwayat; unduh daftar temuan (Excel) untuk diperbaiki di QGIS. Proses
            ini tidak mengubah progres SE2026.
          </p>
          <div className="flex flex-wrap justify-end gap-field border-t border-line pt-kartu">
            <TombolAksi varian="sekunder" onClick={() => setNotifikasi(false)}>
              Saya Mengerti
            </TombolAksi>
            <TautanAksi href="/riwayat">Buka Riwayat Upload</TautanAksi>
          </div>
        </div>
      </Modal>
    </Panel>
  );
}
