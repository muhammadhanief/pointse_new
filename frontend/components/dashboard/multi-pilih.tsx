"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

import { TombolAksi } from "@/components/dashboard/ui";

export type OpsiPilih = {
  nilai: string;
  label: string;
};

/**
 * Dropdown dengan pencarian dan kotak centang (bisa pilih lebih dari satu).
 *
 * Pilihan baru dipakai setelah menekan "Terapkan", supaya memilih banyak
 * kabupaten/jenis tidak memicu satu permintaan API per klik.
 */
export function MultiPilih({
  label,
  opsi,
  terpilih,
  onTerapkan,
  labelSemua = "Semua",
  tempatCari = "Cari...",
  nonaktif = false,
}: {
  label: string;
  opsi: OpsiPilih[];
  terpilih: string[];
  onTerapkan: (nilai: string[]) => void;
  labelSemua?: string;
  tempatCari?: string;
  nonaktif?: boolean;
}) {
  const id = useId();
  const [buka, setBuka] = useState(false);
  const [draf, setDraf] = useState<string[]>(terpilih);
  const [cari, setCari] = useState("");
  const wadah = useRef<HTMLDivElement>(null);
  const kotakCari = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!buka) {
      return;
    }
    // Pilihan kosong dari induk berarti "semua"; tampilkan centang penuh
    // supaya pengguna bisa mencabut satu per satu.
    setDraf(
      terpilih.length === 0 ? opsi.map((satu) => satu.nilai) : terpilih,
    );
    setCari("");
    // ``opsi`` sengaja tidak jadi dependensi: nilainya dibuat ulang tiap render
    // induk sehingga akan mereset centang saat pengguna sedang memilih.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buka, terpilih]);

  useEffect(() => {
    if (!buka) {
      return;
    }
    const tutup = (kejadian: MouseEvent) => {
      if (!wadah.current?.contains(kejadian.target as Node)) {
        setBuka(false);
      }
    };
    const tombol = (kejadian: KeyboardEvent) => {
      if (kejadian.key === "Escape") {
        setBuka(false);
      }
    };
    document.addEventListener("mousedown", tutup);
    document.addEventListener("keydown", tombol);
    return () => {
      document.removeEventListener("mousedown", tutup);
      document.removeEventListener("keydown", tombol);
    };
  }, [buka]);

  useEffect(() => {
    if (buka) {
      kotakCari.current?.focus();
    }
  }, [buka]);

  const tersaring = useMemo(() => {
    const kata = cari.trim().toLowerCase();
    if (!kata) {
      return opsi;
    }
    return opsi.filter((satu) => satu.label.toLowerCase().includes(kata));
  }, [opsi, cari]);

  const semuaTerpilih =
    opsi.length > 0 && opsi.every((satu) => draf.includes(satu.nilai));

  const ringkasan = (() => {
    if (terpilih.length === 0) {
      return labelSemua;
    }
    if (terpilih.length === opsi.length) {
      return `${labelSemua} (${opsi.length})`;
    }
    if (terpilih.length === 1) {
      return opsi.find((satu) => satu.nilai === terpilih[0])?.label ?? "1 dipilih";
    }
    return `${terpilih.length} dipilih`;
  })();

  function ubahSatu(nilai: string, dicentang: boolean) {
    setDraf((lama) =>
      dicentang ? [...lama, nilai] : lama.filter((satu) => satu !== nilai),
    );
  }

  function ubahSemua(dicentang: boolean) {
    setDraf(dicentang ? opsi.map((satu) => satu.nilai) : []);
  }

  return (
    <div className="relative" ref={wadah}>
      <span className="block text-sm font-medium text-ink" id={`${id}-label`}>
        {label}
      </span>
      <button
        type="button"
        className="mt-label flex min-h-9 w-full items-center justify-between gap-2 rounded-lg border border-line-strong bg-surface px-input py-input text-left text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
        aria-haspopup="listbox"
        aria-expanded={buka}
        aria-labelledby={`${id}-label`}
        disabled={nonaktif}
        onClick={() => setBuka((lama) => !lama)}
      >
        <span className="truncate">{ringkasan}</span>
        <span aria-hidden="true" className="text-muted">
          ▾
        </span>
      </button>

      {buka ? (
        <div className="absolute z-20 mt-1 w-full min-w-56 rounded-lg border border-line-strong bg-surface shadow-lg">
          <div className="border-b border-line p-2">
            <input
              ref={kotakCari}
              type="search"
              value={cari}
              onChange={(kejadian) => setCari(kejadian.target.value)}
              placeholder={tempatCari}
              aria-label={`Cari ${label.toLowerCase()}`}
              className="block min-h-8 w-full rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-ink"
            />
          </div>

          <div className="max-h-64 overflow-y-auto p-1" role="group" aria-label={label}>
            <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink hover:bg-paper">
              <input
                type="checkbox"
                checked={semuaTerpilih}
                onChange={(kejadian) => ubahSemua(kejadian.target.checked)}
              />
              <span className="font-medium">{labelSemua}</span>
            </label>
            <div className="my-1 border-t border-line" />
            {tersaring.length === 0 ? (
              <p className="px-2 py-2 text-sm text-muted">Tidak ada yang cocok.</p>
            ) : (
              tersaring.map((satu) => (
                <label
                  key={satu.nilai}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-ink hover:bg-paper"
                >
                  <input
                    type="checkbox"
                    checked={draf.includes(satu.nilai)}
                    onChange={(kejadian) =>
                      ubahSatu(satu.nilai, kejadian.target.checked)
                    }
                  />
                  <span className="truncate">{satu.label}</span>
                </label>
              ))
            )}
          </div>

          <div className="flex justify-end gap-1.5 border-t border-line p-2">
            <TombolAksi
              varian="sekunder"
              className="min-h-8 px-2.5 text-xs"
              onClick={() => setBuka(false)}
            >
              Batal
            </TombolAksi>
            <TombolAksi
              className="min-h-8 px-2.5 text-xs"
              disabled={draf.length === 0}
              title={
                draf.length === 0
                  ? "Pilih minimal satu"
                  : "Pakai pilihan ini"
              }
              onClick={() => {
                onTerapkan(draf);
                setBuka(false);
              }}
            >
              Terapkan
            </TombolAksi>
          </div>
        </div>
      ) : null}
    </div>
  );
}
