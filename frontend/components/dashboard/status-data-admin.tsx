"use client";

import { useCallback, useEffect, useState } from "react";

import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
} from "@/lib/api/klien";
import type { DaftarMaster, MasterGeotag, Ringkasan } from "@/lib/api/types";
import { formatTanggal } from "@/lib/format";
import { KABUPATEN_33, kodeKabupaten } from "@/lib/wilayah/kabupaten";

import { BarisStatus, TautanAksi } from "./ui";

type Tabulasi = {
  master: number;
  peta: number;
  edit: number;
};

const TOTAL_KAB = KABUPATEN_33.length;

function kode(kdprov: string, kdkab: string): string {
  return kodeKabupaten(kdprov, kdkab);
}

export function StatusDataPetugas({ kdkab }: { kdkab: string | null }) {
  const [master, setMaster] = useState<MasterGeotag | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);

  const muat = useCallback(
    async (isyarat: AbortSignal) => {
      if (!kdkab) {
        setMemuat(false);
        return;
      }
      setGalat(null);
      try {
        const hasil = await ambilJson<DaftarMaster>(
          `/geotag-master?kdkab=${encodeURIComponent(kdkab)}&limit=1`,
          { signal: isyarat },
        );
        setMaster(hasil.baris[0] ?? null);
      } catch (kesalahan) {
        if (!adalahBatal(kesalahan)) {
          setGalat(pesanKesalahan(kesalahan));
        }
      } finally {
        if (!isyarat.aborted) {
          setMemuat(false);
        }
      }
    },
    [kdkab],
  );

  useEffect(() => {
    const kendali = new AbortController();
    void muat(kendali.signal);
    return () => kendali.abort();
  }, [muat]);

  if (galat) {
    return (
      <p className="mt-1 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger">
        {galat}
      </p>
    );
  }

  return (
    <BarisStatus
      label="Master geotag"
      status={memuat ? undefined : master ? "ada" : "belum"}
      nilai={memuat ? "Memuat..." : undefined}
      keterangan={
        memuat
          ? "Memeriksa master untuk wilayah kerja Anda."
          : master
            ? `Versi ke-${master.nomor_versi ?? "-"} · ${formatTanggal(master.tanggal_data)}.`
            : "Belum diunggah admin provinsi untuk wilayah kerja Anda."
      }
    />
  );
}

export function StatusDataAdmin() {
  const [data, setData] = useState<Tabulasi | null>(null);
  const [galat, setGalat] = useState<string | null>(null);

  const muat = useCallback(async (isyarat: AbortSignal) => {
    setGalat(null);
    try {
      const [master, ringkasan] = await Promise.all([
        ambilJson<DaftarMaster>("/geotag-master?limit=500", {
          signal: isyarat,
        }),
        ambilJson<Ringkasan>("/ringkasan?dasar=tugas", {
          signal: isyarat,
        }),
      ]);

      const kabMaster = new Set(
        master.baris.map((satu) => kode(satu.kdprov, satu.kdkab)),
      );
      const kabPeta = new Set<string>();
      const kabEdit = new Set<string>();

      for (const baris of ringkasan.baris) {
        const kodeKab = kode(baris.kdprov, baris.kdkab);
        if (baris.terakhir.some((satu) => satu.tipe === "A")) {
          kabPeta.add(kodeKab);
        }
        if (baris.terakhir.some((satu) => satu.tipe === "B")) {
          kabEdit.add(kodeKab);
        }
      }

      setData({
        master: kabMaster.size,
        peta: kabPeta.size,
        edit: kabEdit.size,
      });
    } catch (kesalahan) {
      if (adalahBatal(kesalahan)) {
        return;
      }
      setGalat(pesanKesalahan(kesalahan));
    }
  }, []);

  useEffect(() => {
    const kendali = new AbortController();
    void muat(kendali.signal);
    return () => kendali.abort();
  }, [muat]);

  if (galat) {
    return (
      <p className="mt-1 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger">
        {galat}
      </p>
    );
  }

  if (!data) {
    return <p className="mt-1 text-sm text-muted">Memuat tabulasi...</p>;
  }

  return (
    <dl className="mt-3">
      <BarisStatus
        label="Master geotag"
        nilai={`${data.master} / ${TOTAL_KAB} kabupaten/kota`}
        keterangan="Sudah mengunggah master geotag."
        aksi={
          <TautanAksi href="/master-geotag" ringkas>
            Lihat
          </TautanAksi>
        }
      />
      <BarisStatus
        label="Peta digital terakhir"
        nilai={`${data.peta} / ${TOTAL_KAB} kabupaten/kota`}
        keterangan="Sudah punya Proses 1 sukses."
        aksi={
          <TautanAksi href="/proses/identifikasi" ringkas>
            Lihat
          </TautanAksi>
        }
      />
      <BarisStatus
        label="Edit geotag terakhir"
        nilai={`${data.edit} / ${TOTAL_KAB} kabupaten/kota`}
        keterangan="Sudah punya Proses 2 sukses."
        aksi={
          <TautanAksi href="/proses/pengecekan" ringkas>
            Lihat
          </TautanAksi>
        }
      />
    </dl>
  );
}
