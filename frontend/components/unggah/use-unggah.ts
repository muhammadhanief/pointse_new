"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  KesalahanApi,
  ambilJson,
  detailKesalahan,
  pesanKesalahan,
  urlApi,
} from "@/lib/api/klien";
import { ambilToken } from "@/lib/api/token";
import { istilahProses } from "@/lib/istilah";

export type StatusUnggah =
  | "idle"
  | "mengunggah"
  | "sukses"
  | "galat"
  | "batal";

export type ProgresUnggah = {
  loaded: number;
  total: number | null;
};

export type JenisUnggah = "master" | "peta" | "titik";

export type UnggahanSelesai = {
  unggahan_id: string;
  nama: string;
  ukuran: number;
  sha256: string;
  jenis: string;
};

export type PermintaanUnggah<T> = {
  jenis: JenisUnggah;
  berkas: File;
  proses: (unggahan: UnggahanSelesai, signal: AbortSignal) => Promise<T>;
};

type SesiUnggah = {
  unggahan_id: string;
  nama: string;
  ukuran: number;
  jenis: string;
  ukuran_potongan: number;
  jumlah_potongan: number;
  potongan_diterima: number[];
  selesai: boolean;
  sha256: string | null;
};

type SesiTersimpan = {
  id: string;
  nama: string;
  ukuran: number;
  jenis: JenisUnggah;
  lastModified: number;
};

const BATAS_WAKTU_POTONGAN = 30 * 60 * 1000;
const MAKS_PERCOBAAN = 5;
const AWALAN_SESI = "pointse.unggah.v1.";
const PARALEL = (() => {
  const nilai = Number(process.env.NEXT_PUBLIC_UNGGAH_PARALEL ?? "2");
  if (!Number.isFinite(nilai)) {
    return 2;
  }
  return Math.min(4, Math.max(1, Math.trunc(nilai)));
})();

class GalatPotongan extends Error {
  readonly status: number;
  readonly data: unknown;
  readonly teks: string;
  readonly retryAfter: number | null;

  constructor(
    status: number,
    data: unknown,
    teks: string,
    retryAfter: number | null = null,
  ) {
    super(`potongan gagal (HTTP ${status})`);
    this.name = "GalatPotongan";
    this.status = status;
    this.data = data;
    this.teks = teks;
    this.retryAfter = retryAfter;
  }
}

function dataJson(teks: string): unknown {
  try {
    return JSON.parse(teks) as unknown;
  } catch {
    return null;
  }
}

function hentikan() {
  return new DOMException("Dibatalkan", "AbortError");
}

function tunggu(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((selesai, gagal) => {
    if (signal.aborted) {
      gagal(hentikan());
      return;
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", batalkan);
      selesai();
    }, ms);
    function batalkan() {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", batalkan);
      gagal(hentikan());
    }
    signal.addEventListener("abort", batalkan, { once: true });
  });
}

function retryAfterDetik(xhr: XMLHttpRequest): number | null {
  const teks = xhr.getResponseHeader("retry-after");
  if (!teks) {
    return null;
  }
  const detik = Number(teks);
  if (Number.isFinite(detik) && detik >= 0) {
    return Math.min(60, Math.ceil(detik));
  }
  const waktu = Date.parse(teks);
  if (!Number.isNaN(waktu)) {
    return Math.min(60, Math.max(0, Math.ceil((waktu - Date.now()) / 1000)));
  }
  return null;
}

async function hashBagian(blob: Blob, signal: AbortSignal): Promise<string> {
  if (signal.aborted) {
    throw hentikan();
  }
  if (!globalThis.crypto?.subtle) {
    throw new Error(
      "Browser tidak mendukung SHA-256 (crypto.subtle). Buka aplikasi lewat HTTPS atau localhost.",
    );
  }
  const data = await blob.arrayBuffer();
  if (signal.aborted) {
    throw hentikan();
  }
  const hasil = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hasil))
    .map((satu) => satu.toString(16).padStart(2, "0"))
    .join("");
}

function pesanGalat(galat: unknown): string {
  if (galat instanceof KesalahanApi) {
    if (galat.status === 401) {
      return "Sesi sudah habis. Muat ulang halaman, lalu masuk lagi.";
    }
    if (galat.status === 404) {
      return "Sesi unggahan tidak ditemukan atau sudah kedaluwarsa. Ulangi unggah.";
    }
    if (galat.status === 413) {
      return (
        istilahProses(galat.detail) ||
        "Berkas ditolak server (HTTP 413). Periksa batas ukuran unggahan."
      );
    }
    return istilahProses(pesanKesalahan(galat));
  }

  if (galat instanceof GalatPotongan) {
    const detail = detailKesalahan(galat.data);
    if (galat.status === 401) {
      return "Sesi sudah habis. Muat ulang halaman, lalu masuk lagi.";
    }
    if (galat.status === 403) {
      return (
        (detail && istilahProses(detail)) ||
        "Potongan ditolak WAF/server (HTTP 403). Pastikan body biner dikirim dengan Content-Type application/octet-stream."
      );
    }
    if (galat.status === 404) {
      return "Sesi unggahan tidak ditemukan atau sudah kedaluwarsa. Ulangi unggah.";
    }
    if (galat.status === 413) {
      return (
        (detail && istilahProses(detail)) ||
        "Potongan ditolak server (HTTP 413). Batas body server 128 MiB; ukuran potongan terlalu besar atau proxy menolak body."
      );
    }
    if (galat.status === 415) {
      return detail ?? "Format potongan tidak didukung server (HTTP 415).";
    }
    if (galat.status === 408 || galat.status === 504) {
      return `Server atau proxy melewati batas waktu (HTTP ${galat.status}). Koneksi bisa dilanjutkan.`;
    }
    if (galat.status === 429) {
      return "Server sibuk (HTTP 429). Coba lagi beberapa saat.";
    }
    if (galat.status === 0) {
      return "Koneksi terputus saat mengirim potongan. Sesi disimpan; pilih berkas yang sama untuk melanjutkan.";
    }
    if (galat.status >= 500) {
      return "Server gagal memproses potongan. Coba lagi beberapa saat.";
    }
    return (
      (detail && istilahProses(detail)) ||
      `Potongan ditolak (HTTP ${galat.status}).`
    );
  }

  if (galat instanceof TypeError) {
    return "Koneksi terputus. Sesi unggahan disimpan; pilih berkas yang sama untuk melanjutkan.";
  }

  if (galat instanceof Error && galat.message) {
    return galat.message;
  }
  return "Koneksi terputus saat mengunggah. Periksa jaringan lalu coba lagi.";
}

function bisaDiulang(galat: unknown): boolean {
  return (
    galat instanceof GalatPotongan &&
    (galat.status === 0 ||
      galat.status === 408 ||
      galat.status === 429 ||
      galat.status >= 500)
  );
}

function kunciSesi(jenis: JenisUnggah, berkas: File): string {
  return `${AWALAN_SESI}${jenis}:${berkas.size}:${berkas.lastModified}:${berkas.name}`;
}

function bacaSesiTersimpan(kunci: string): SesiTersimpan | null {
  try {
    const mentah = window.localStorage.getItem(kunci);
    if (!mentah) {
      return null;
    }
    const data = JSON.parse(mentah) as Partial<SesiTersimpan>;
    if (
      typeof data.id !== "string" ||
      typeof data.nama !== "string" ||
      typeof data.ukuran !== "number" ||
      typeof data.jenis !== "string" ||
      typeof data.lastModified !== "number"
    ) {
      return null;
    }
    return data as SesiTersimpan;
  } catch {
    return null;
  }
}

function simpanSesi(kunci: string, sesi: SesiTersimpan) {
  try {
    window.localStorage.setItem(kunci, JSON.stringify(sesi));
  } catch {
    // localStorage bisa diblokir; unggahan tetap berjalan tanpa resume.
  }
}

function hapusSesi(kunci: string) {
  try {
    window.localStorage.removeItem(kunci);
  } catch {
    // abaikan
  }
}

function kirimSatuPotongan(
  idUnggah: string,
  nomor: number,
  bagian: Blob,
  sha256: string,
  signal: AbortSignal,
  onProgress: (terkirim: number) => void,
  simpanXhr: (xhr: XMLHttpRequest) => void,
  lepasXhr: (xhr: XMLHttpRequest) => void,
): Promise<void> {
  return new Promise<void>((selesai, gagal) => {
    if (signal.aborted) {
      gagal(hentikan());
      return;
    }

    const xhr = new XMLHttpRequest();
    simpanXhr(xhr);
    let beres = false;

    function bersihkan() {
      if (beres) {
        return;
      }
      beres = true;
      signal.removeEventListener("abort", batalkan);
      lepasXhr(xhr);
    }

    function batalkan() {
      xhr.abort();
    }

    signal.addEventListener("abort", batalkan, { once: true });
    xhr.open(
      "POST",
      urlApi(`/unggahan/${encodeURIComponent(idUnggah)}/potongan/${nomor}`),
    );
    xhr.timeout = BATAS_WAKTU_POTONGAN;
    // API lintas origin memakai Bearer; jangan kirim cookie ke backend.
    xhr.withCredentials = false;
    xhr.setRequestHeader("accept", "application/json");
    xhr.setRequestHeader("content-type", "application/octet-stream");
    xhr.setRequestHeader("x-sha256", sha256);
    const token = ambilToken();
    if (token) {
      xhr.setRequestHeader("authorization", `Bearer ${token}`);
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.min(event.loaded, bagian.size));
      }
    };

    xhr.onload = () => {
      bersihkan();
      const data = dataJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        selesai();
        return;
      }
      gagal(
        new GalatPotongan(
          xhr.status,
          data,
          xhr.responseText,
          retryAfterDetik(xhr),
        ),
      );
    };

    xhr.onerror = () => {
      bersihkan();
      gagal(new GalatPotongan(0, null, ""));
    };

    xhr.ontimeout = () => {
      bersihkan();
      gagal(new GalatPotongan(408, null, ""));
    };

    xhr.onabort = () => {
      bersihkan();
      gagal(hentikan());
    };

    try {
      xhr.send(bagian);
    } catch {
      bersihkan();
      gagal(new GalatPotongan(0, null, ""));
    }
  });
}

async function kirimDenganUlang(
  idUnggah: string,
  nomor: number,
  bagian: Blob,
  sha256: string,
  signal: AbortSignal,
  onProgress: (terkirim: number) => void,
  simpanXhr: (xhr: XMLHttpRequest) => void,
  lepasXhr: (xhr: XMLHttpRequest) => void,
): Promise<void> {
  let percobaan = 0;
  while (true) {
    try {
      await kirimSatuPotongan(
        idUnggah,
        nomor,
        bagian,
        sha256,
        signal,
        onProgress,
        simpanXhr,
        lepasXhr,
      );
      return;
    } catch (galat) {
      if (signal.aborted) {
        throw hentikan();
      }
      if (!bisaDiulang(galat) || percobaan >= MAKS_PERCOBAAN - 1) {
        throw galat;
      }
      const jeda =
        galat instanceof GalatPotongan && galat.retryAfter !== null
          ? galat.retryAfter * 1000
          : Math.min(30_000, 1000 * 2 ** percobaan);
      percobaan += 1;
      await tunggu(jeda, signal);
    }
  }
}

async function mulaiSesi(
  jenis: JenisUnggah,
  berkas: File,
  signal: AbortSignal,
): Promise<SesiUnggah> {
  const sesi = await ambilJson<SesiUnggah>("/unggahan/mulai", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      nama: berkas.name,
      ukuran: berkas.size,
      jenis,
    }),
    signal,
  });
  return {
    ...sesi,
    potongan_diterima: sesi.potongan_diterima ?? [],
    selesai: sesi.selesai ?? false,
    sha256: sesi.sha256 ?? null,
  };
}

async function statusSesi(
  idUnggah: string,
  signal: AbortSignal,
): Promise<SesiUnggah> {
  return ambilJson<SesiUnggah>(`/unggahan/${encodeURIComponent(idUnggah)}`, {
    signal,
  });
}

async function selesaiSesi(
  idUnggah: string,
  signal: AbortSignal,
): Promise<UnggahanSelesai> {
  return ambilJson<UnggahanSelesai>(
    `/unggahan/${encodeURIComponent(idUnggah)}/selesai`,
    { method: "POST", signal },
  );
}

export function useUnggah<T>() {
  const [status, setStatus] = useState<StatusUnggah>("idle");
  const [progres, setProgres] = useState<ProgresUnggah>({
    loaded: 0,
    total: null,
  });
  const [pesan, setPesan] = useState<string | null>(null);
  const [data, setData] = useState<T | null>(null);

  const xhrRef = useRef<Set<XMLHttpRequest>>(new Set());
  const unggahRef = useRef<AbortController | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const batalRef = useRef(false);
  const hidupRef = useRef(true);
  const idUnggah = useRef(0);

  useEffect(() => {
    hidupRef.current = true;
    const xhrAktif = xhrRef.current;
    return () => {
      hidupRef.current = false;
      unggahRef.current?.abort();
      for (const xhr of Array.from(xhrAktif)) {
        xhr.abort();
      }
      xhrAktif.clear();
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (status !== "mengunggah") {
      return;
    }

    function cegahTutup(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = "";
    }

    window.addEventListener("beforeunload", cegahTutup);
    return () => window.removeEventListener("beforeunload", cegahTutup);
  }, [status]);

  const batal = useCallback(() => {
    batalRef.current = true;
    unggahRef.current?.abort();
    for (const xhr of Array.from(xhrRef.current)) {
      xhr.abort();
    }
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setProgres({ loaded: 0, total: null });
    setPesan(null);
    setData(null);
  }, []);

  const unggah = useCallback(
    async (permintaan: PermintaanUnggah<T>): Promise<T | null> => {
      const id = ++idUnggah.current;
      unggahRef.current?.abort();
      for (const xhr of Array.from(xhrRef.current)) {
        xhr.abort();
      }
      xhrRef.current.clear();
      abortRef.current?.abort();
      batalRef.current = false;

      const pengendali = new AbortController();
      unggahRef.current = pengendali;
      const signal = pengendali.signal;
      const berkas = permintaan.berkas;
      const kunci = kunciSesi(permintaan.jenis, berkas);
      let sesi: SesiUnggah | null = null;

      function aman(ubah: () => void) {
        if (hidupRef.current && id === idUnggah.current) {
          ubah();
        }
      }

      function perbaruiProgres(peta: Map<number, number>) {
        let terkirim = 0;
        for (const nilai of peta.values()) {
          terkirim += nilai;
        }
        aman(() =>
          setProgres({
            loaded: Math.min(terkirim, berkas.size),
            total: berkas.size,
          }),
        );
      }

      if (hidupRef.current) {
        setStatus("mengunggah");
        setProgres({ loaded: 0, total: berkas.size });
        setPesan(null);
        setData(null);
      }

      try {
        const tersimpan = bacaSesiTersimpan(kunci);
        if (tersimpan) {
          if (
            tersimpan.nama !== berkas.name ||
            tersimpan.ukuran !== berkas.size ||
            tersimpan.jenis !== permintaan.jenis ||
            tersimpan.lastModified !== berkas.lastModified
          ) {
            hapusSesi(kunci);
          } else {
            try {
              sesi = await statusSesi(tersimpan.id, signal);
              if (
                sesi.nama !== berkas.name ||
                sesi.ukuran !== berkas.size ||
                sesi.jenis !== permintaan.jenis
              ) {
                sesi = null;
                hapusSesi(kunci);
              }
            } catch (galat) {
              if (galat instanceof KesalahanApi && galat.status === 404) {
                hapusSesi(kunci);
              } else if (galat instanceof KesalahanApi && galat.status === 403) {
                hapusSesi(kunci);
              } else {
                throw galat;
              }
            }
          }
        }

        if (!sesi) {
          sesi = await mulaiSesi(permintaan.jenis, berkas, signal);
          simpanSesi(kunci, {
            id: sesi.unggahan_id,
            nama: berkas.name,
            ukuran: berkas.size,
            jenis: permintaan.jenis,
            lastModified: berkas.lastModified,
          });
        }

        let hasil: UnggahanSelesai;
        if (sesi.selesai) {
          hasil = {
            unggahan_id: sesi.unggahan_id,
            nama: sesi.nama,
            ukuran: sesi.ukuran,
            sha256: sesi.sha256 ?? "",
            jenis: sesi.jenis,
          };
          aman(() =>
            setProgres({ loaded: berkas.size, total: berkas.size }),
          );
        } else {
          const ukuranPotongan = sesi.ukuran_potongan;
          const totalPotongan = sesi.jumlah_potongan;
          if (ukuranPotongan < 1 || totalPotongan < 1) {
            throw new Error("Server memberi ukuran potongan yang tidak valid.");
          }

          const diterima = new Set(
            sesi.potongan_diterima.filter(
              (nomor) => nomor >= 1 && nomor <= totalPotongan,
            ),
          );
          const potonganAwal = new Map<number, number>();
          for (const nomor of diterima) {
            const mulai = (nomor - 1) * ukuranPotongan;
            potonganAwal.set(
              nomor,
              Math.min(ukuranPotongan, berkas.size - mulai),
            );
          }
          perbaruiProgres(potonganAwal);

          const antre: number[] = [];
          for (let nomor = 1; nomor <= totalPotongan; nomor += 1) {
            if (!diterima.has(nomor)) {
              antre.push(nomor);
            }
          }

          let indeks = 0;
          let galatUtama: unknown = null;
          const idSesi = sesi.unggahan_id;

          const pekerja = async () => {
            while (!galatUtama && !signal.aborted) {
              const nomor = antre[indeks];
              indeks += 1;
              if (nomor === undefined) {
                return;
              }
              const mulai = (nomor - 1) * ukuranPotongan;
              const bagian = berkas.slice(
                mulai,
                Math.min(mulai + ukuranPotongan, berkas.size),
              );
              try {
                const sha256 = await hashBagian(bagian, signal);
                await kirimDenganUlang(
                  idSesi,
                  nomor,
                  bagian,
                  sha256,
                  signal,
                  (terkirim) => {
                    potonganAwal.set(nomor, terkirim);
                    perbaruiProgres(potonganAwal);
                  },
                  (xhr) => xhrRef.current.add(xhr),
                  (xhr) => xhrRef.current.delete(xhr),
                );
                potonganAwal.set(nomor, bagian.size);
                perbaruiProgres(potonganAwal);
              } catch (galat) {
                if (!galatUtama) {
                  galatUtama = galat;
                }
                for (const xhr of Array.from(xhrRef.current)) {
                  xhr.abort();
                }
                return;
              }
            }
          };

          const jumlahPekerja = Math.min(PARALEL, Math.max(1, antre.length));
          await Promise.all(
            Array.from({ length: jumlahPekerja }, () => pekerja()),
          );
          if (galatUtama) {
            throw galatUtama;
          }
          if (signal.aborted) {
            throw hentikan();
          }

          hasil = await selesaiSesi(sesi.unggahan_id, signal);
          aman(() =>
            setProgres({ loaded: berkas.size, total: berkas.size }),
          );
        }

        if (batalRef.current) {
          throw hentikan();
        }

        const pengendaliProses = new AbortController();
        abortRef.current = pengendaliProses;
        const proses = await permintaan.proses(hasil, pengendaliProses.signal);
        abortRef.current = null;
        hapusSesi(kunci);

        aman(() => {
          setStatus("sukses");
          setData(proses);
        });
        return proses;
      } catch (galat) {
        if (galat instanceof DOMException && galat.name === "AbortError") {
          aman(() => {
            setStatus("batal");
            setPesan(
              "Unggahan dibatalkan. Sesi disimpan; pilih berkas yang sama untuk melanjutkan.",
            );
          });
          return null;
        }

        aman(() => {
          setStatus("galat");
          setPesan(pesanGalat(galat));
        });
        return null;
      } finally {
        if (id === idUnggah.current) {
          unggahRef.current = null;
          abortRef.current = null;
          xhrRef.current.clear();
        }
      }
    },
    [],
  );

  return {
    status,
    progres,
    pesan,
    data,
    unggah,
    batal,
    reset,
  };
}
