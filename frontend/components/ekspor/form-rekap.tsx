"use client";

import { useState, type FormEvent } from "react";

import { Panel, TombolAksi } from "@/components/dashboard/ui";
import { KesalahanApi, unduhBerkas } from "@/lib/api/klien";

export function FormRekap({
  onMulai,
  onSiap,
  onGagal,
}: {
  onMulai?: () => void;
  onSiap?: (nama: string) => void;
  onGagal?: () => void;
}) {
  const [tingkat, setTingkat] = useState("kabupaten");
  const [tipe, setTipe] = useState("");
  const [dasar, setDasar] = useState("tugas");
  const [awal, setAwal] = useState("");
  const [akhir, setAkhir] = useState("");
  const [galat, setGalat] = useState<string | null>(null);
  const [mengunduh, setMengunduh] = useState(false);

  async function kirim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (awal && akhir && awal > akhir) {
      setGalat("Tanggal awal harus sama atau lebih awal dari tanggal akhir.");
      return;
    }
    setGalat(null);

    const params = new URLSearchParams();
    params.set("tingkat", tingkat);
    params.set("dasar", dasar);
    if (tipe) {
      params.set("tipe", tipe);
    }
    if (awal) {
      params.set("tanggal_awal", awal);
    }
    if (akhir) {
      params.set("tanggal_akhir", akhir);
    }

    onMulai?.();
    setMengunduh(true);
    try {
      const nama = await unduhBerkas(
        `/ekspor/rekap.csv?${params.toString()}`,
        `rekap_${tingkat}_${dasar}.csv`,
      );
      onSiap?.(nama);
    } catch (galatUnduh) {
      setGalat(
        galatUnduh instanceof KesalahanApi
          ? `Unduhan gagal: ${galatUnduh.detail}`
          : "Unduhan gagal. Periksa koneksi lalu coba lagi.",
      );
      onGagal?.();
    } finally {
      setMengunduh(false);
    }
  }

  return (
    <Panel
      judul="Unduh rekap CSV"
      deskripsi="Satu baris per run per wilayah dalam rentang tanggal data. Kategori tanpa wilayah ditulis dengan kode kosong."
    >
      <form onSubmit={kirim} className="mt-3 space-y-field">
        <div className="grid gap-field sm:grid-cols-3">
          <div>
            <label
              htmlFor="tingkat-rekap"
              className="text-sm font-medium text-ink"
            >
              Tingkat
            </label>
            <select
              id="tingkat-rekap"
              value={tingkat}
              onChange={(event) => setTingkat(event.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              <option value="kabupaten">Kabupaten/kota</option>
              <option value="desa">Desa</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="tipe-rekap"
              className="text-sm font-medium text-ink"
            >
              Proses
            </label>
            <select
              id="tipe-rekap"
              value={tipe}
              onChange={(event) => setTipe(event.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              <option value="">Semua proses</option>
              <option value="A">1. Identifikasi Titik</option>
              <option value="B">2. Pengecekan Titik</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="dasar-rekap"
              className="text-sm font-medium text-ink"
            >
              Dasar wilayah
            </label>
            <select
              id="dasar-rekap"
              value={dasar}
              onChange={(event) => setDasar(event.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              <option value="tugas">Tugas</option>
              <option value="posisi">Posisi</option>
            </select>
          </div>
        </div>

        <div className="grid gap-field sm:grid-cols-2">
          <div>
            <label
              htmlFor="awal-rekap"
              className="text-sm font-medium text-ink"
            >
              Tanggal awal (opsional)
            </label>
            <input
              id="awal-rekap"
              type="date"
              value={awal}
              onChange={(event) => setAwal(event.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            />
          </div>

          <div>
            <label
              htmlFor="akhir-rekap"
              className="text-sm font-medium text-ink"
            >
              Tanggal akhir (opsional)
            </label>
            <input
              id="akhir-rekap"
              type="date"
              value={akhir}
              onChange={(event) => setAkhir(event.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            />
          </div>
        </div>

        {galat ? (
          <p
            role="alert"
            className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger"
          >
            {galat}
          </p>
        ) : null}

        <TombolAksi type="submit" disabled={mengunduh}>
          {mengunduh ? "Menyiapkan unduhan..." : "Unduh rekap CSV"}
        </TombolAksi>
      </form>
    </Panel>
  );
}
