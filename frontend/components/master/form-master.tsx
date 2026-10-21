"use client";

import { useState, type FormEvent } from "react";

import { TombolAksi } from "@/components/dashboard/ui";
import { BidangBerkas } from "@/components/unggah/bidang-berkas";
import { CatatanUnggah } from "@/components/unggah/catatan";
import { PesanUnggah } from "@/components/unggah/pesan";
import { ProgresUnggahan } from "@/components/unggah/progres";
import { useUnggah } from "@/components/unggah/use-unggah";
import { ambilJson, buatFormUrlEncoded } from "@/lib/api/klien";
import type { MasterGeotag } from "@/lib/api/types";
import { formatAngka } from "@/lib/format";
import {
  daftarKabupaten,
  labelKabupaten,
} from "@/lib/wilayah/kabupaten";

export function FormMaster({
  kdprov,
  kdkabAwal,
  onSelesai,
}: {
  kdprov: string;
  kdkabAwal?: string;
  onSelesai: () => void;
}) {
  const [kdkab, setKdkab] = useState(kdkabAwal ?? "");
  const [tanggal, setTanggal] = useState("");
  const [layer, setLayer] = useState("");
  const [berkas, setBerkas] = useState<File | null>(null);
  const [kunciBerkas, setKunciBerkas] = useState(0);
  const [galatIsian, setGalatIsian] = useState<string | null>(null);
  const { status, progres, pesan, data, unggah, batal, reset } =
    useUnggah<MasterGeotag>();
  const sedang = status === "mengunggah";
  const pilihanKabupaten = daftarKabupaten(kdprov);

  function pilihBerkas(berkasBaru: File | null) {
    setBerkas(berkasBaru);
    setGalatIsian(null);
    reset();
  }

  async function kirim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const kode = kdkab.trim();
    if (!/^\d{4}$/.test(kode) || !kode.startsWith(kdprov)) {
      setGalatIsian(
        `Kode kabupaten/kota harus 4 digit dan berawalan ${kdprov}, misalnya ${kdprov}07.`,
      );
      return;
    }
    if (!berkas || sedang) {
      return;
    }

    setGalatIsian(null);
    const hasil = await unggah({
      jenis: "master",
      berkas,
      proses: (unggahan, signal) =>
        ambilJson<MasterGeotag>("/geotag-master", {
          method: "POST",
          body: buatFormUrlEncoded({
            kdprov,
            kdkab: kode,
            unggahan_id: unggahan.unggahan_id,
            tanggal_data: tanggal || undefined,
            layer: layer.trim() || undefined,
          }),
          signal,
        }),
    });

    if (hasil) {
      setTanggal("");
      setLayer("");
      setBerkas(null);
      setKunciBerkas((nilai) => nilai + 1);
      onSelesai();
    }
  }

  return (
    <form onSubmit={kirim} className="space-y-field" aria-busy={sedang}>
        <div className="grid gap-field sm:grid-cols-2">
          <div>
            <p className="text-sm font-medium text-ink">Kode provinsi</p>
            <p className="mt-1 flex min-h-9 items-center rounded-lg border border-line bg-paper px-3 text-sm font-semibold tabular-nums text-ink">
              {kdprov}
            </p>
            <p className="mt-bantuan text-xs leading-5 text-muted">
              Mengikuti wilayah akun admin.
            </p>
          </div>

          <div>
            <label
              htmlFor="kdkab-master"
              className="text-sm font-medium text-ink"
            >
              Kabupaten/kota
            </label>
            {pilihanKabupaten.length > 0 ? (
              <>
                <select
                  id="kdkab-master"
                  value={kdkab}
                  disabled={sedang}
                  onChange={(event) => {
                    setKdkab(event.target.value);
                    setGalatIsian(null);
                  }}
                  className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <option value="">Pilih kabupaten/kota</option>
                  {pilihanKabupaten.map((satu) => (
                    <option key={satu.kode} value={satu.kode}>
                      {satu.kode} · {satu.nama}
                    </option>
                  ))}
                </select>
                <p className="mt-bantuan text-xs leading-5 text-muted">
                  Pilih kode BPS Provinsi {kdprov}.
                </p>
              </>
            ) : (
              <>
                <input
                  id="kdkab-master"
                  type="text"
                  inputMode="numeric"
                  maxLength={4}
                  value={kdkab}
                  disabled={sedang}
                  autoComplete="off"
                  placeholder={`${kdprov}07`}
                  onChange={(event) => {
                    setKdkab(
                      event.target.value.replace(/\D/g, "").slice(0, 4),
                    );
                    setGalatIsian(null);
                  }}
                  className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm tabular-nums text-ink disabled:cursor-not-allowed disabled:opacity-60"
                />
                <p className="mt-bantuan text-xs leading-5 text-muted">
                  Daftar kode provinsi ini belum tersedia. Masukkan empat digit
                  berawalan {kdprov}.
                </p>
              </>
            )}
          </div>
        </div>

        <BidangBerkas
          key={kunciBerkas}
          id="berkas-master"
          label="Berkas geotag asli"
          accept=".gpkg,.geojson,.json,application/geo+json,application/geopackage+sqlite3"
          berkas={berkas}
          onPilih={pilihBerkas}
          keterangan="GPKG atau GeoJSON asli dari GS, bukan hasil Proses 1/2. Semua level_6_full_code harus milik kabupaten/kota yang sama."
          disabled={sedang}
        />

        <div className="grid gap-field sm:grid-cols-2">
          <div>
            <label
              htmlFor="tanggal-master"
              className="text-sm font-medium text-ink"
            >
              Tanggal data (opsional)
            </label>
            <input
              id="tanggal-master"
              type="date"
              value={tanggal}
              disabled={sedang}
              onChange={(event) => setTanggal(event.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-bantuan text-xs leading-5 text-muted">
              Kosongkan untuk memakai tanggal hari ini.
            </p>
          </div>

          <div>
            <label
              htmlFor="layer-master"
              className="text-sm font-medium text-ink"
            >
              Layer (opsional)
            </label>
            <input
              id="layer-master"
              type="text"
              value={layer}
              disabled={sedang}
              autoComplete="off"
              onChange={(event) => setLayer(event.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            />
            <p className="mt-bantuan text-xs leading-5 text-muted">
              Isi bila berkas punya beberapa layer.
            </p>
          </div>
        </div>

        {galatIsian ? (
          <p
            role="alert"
            className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger"
          >
            {galatIsian}
          </p>
        ) : null}

        <p className="rounded-lg bg-paper px-3 py-2 text-xs leading-5 text-muted">
          Berkas harus asli dari GS. Semua{" "}
          <span className="font-mono">level_6_full_code</span> harus milik satu
          kabupaten/kota. Versi lama tetap tersimpan.
        </p>

        <CatatanUnggah />

        <div className="sticky bottom-0 z-10 -mx-4 -mb-4 border-t border-line bg-surface px-4 py-3">
          <TombolAksi
            type="submit"
            disabled={!berkas || sedang}
            className="w-full"
          >
            Unggah master geotag
          </TombolAksi>
        </div>

        <ProgresUnggahan status={status} progres={progres} onBatal={batal} />

        <PesanUnggah status={status} pesan={pesan}>
          {data
            ? `Master ${labelKabupaten(data.kdprov, data.kdkab)} tersimpan (versi ke-${
                data.nomor_versi ?? "?"
              }, ${formatAngka(data.jumlah_baris)} baris, layer ${
                data.layer ?? "-"
              }).`
            : "Master geotag berhasil disimpan."}
        </PesanUnggah>
    </form>
  );
}
