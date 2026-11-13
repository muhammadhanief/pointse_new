"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MultiPilih } from "@/components/dashboard/multi-pilih";
import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import { GrafikBatasKabKota } from "@/components/rekonsiliasi/grafik-batas-kabkota";
import { PengaturanPemeriksaanBatas } from "@/components/rekonsiliasi/pengaturan-pemeriksaan-batas";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
  unduhBerkas,
} from "@/lib/api/klien";
import type {
  RekonsiliasiBatasDetail,
  RekonsiliasiBatasPasangBaris,
  RekonsiliasiBatasRingkasan,
} from "@/lib/api/types";
import { PERAN_ADMIN_PROVINSI, kodeWilayah } from "@/lib/auth/peran";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";
import { daftarKabupaten, daftarKaresidenan } from "@/lib/wilayah/kabupaten";

const INTERVAL_MUAT_ULANG = 20000;

function formatLuas(luas: number): string {
  if (luas <= 0) {
    return "0";
  }
  if (luas < 0.01) {
    return "< 0,01";
  }
  return luas.toLocaleString("id-ID", {
    minimumFractionDigits: luas < 10 ? 2 : 1,
    maximumFractionDigits: 2,
  });
}

function formatAmbang(m2: number): string {
  if (!Number.isFinite(m2) || m2 <= 0) {
    return "0";
  }
  return m2.toLocaleString("id-ID", { maximumFractionDigits: 6 });
}

function formatWaktuRun(
  waktu: string | null | undefined,
  tanggal: string | null | undefined,
): string {
  if (waktu) {
    return formatWaktu(waktu);
  }
  return formatTanggal(tanggal);
}

function formatNamaKabKota(nama: string | null | undefined): string {
  if (!nama) {
    return "";
  }
  return nama.replace(/^Kabupaten\s+/i, "");
}

function BadgeStatusBatas({ status }: { status: string }) {
  switch (status) {
    case "clean":
      return (
        <span className="inline-flex items-center whitespace-nowrap rounded-md border border-success/25 bg-success-soft px-2 py-0.5 text-xs font-semibold text-success">
          Clean
        </span>
      );
    case "belum_clean":
      return (
        <span className="inline-flex items-center whitespace-nowrap rounded-md border border-danger/25 bg-danger-soft px-2 py-0.5 text-xs font-semibold text-danger">
          Belum Clean
        </span>
      );
    case "menunggu_tetangga":
      return (
        <span className="inline-flex items-center whitespace-nowrap rounded-md border border-warning/30 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-warning">
          Menunggu Tetangga
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center whitespace-nowrap rounded-md border border-line bg-paper px-2 py-0.5 text-xs font-medium text-muted">
          Belum Unggah
        </span>
      );
  }
}

type ArahUrut = "asc" | "desc";
type KolomUrutPasangan =
  | "wilayah_a"
  | "wilayah_b"
  | "status"
  | "overlap"
  | "gap";
type KolomUrutKabKota =
  | "kdkab"
  | "tetangga"
  | "total"
  | "clean"
  | "belum_clean"
  | "menunggu_tetangga"
  | "belum_unggah"
  | "progres";

const BOBOT_STATUS_BATAS: Record<string, number> = {
  belum_clean: 1,
  clean: 2,
  menunggu_tetangga: 3,
  belum_unggah: 4,
};

function HeaderUrut({
  label,
  aktif,
  arah,
  rataKanan = false,
  onClick,
}: {
  label: string;
  aktif: boolean;
  arah: ArahUrut;
  rataKanan?: boolean;
  onClick: () => void;
}) {
  return (
    <th
      aria-sort={aktif ? (arah === "asc" ? "ascending" : "descending") : "none"}
      className={`px-3 py-2.5 select-none ${rataKanan ? "text-right" : "text-left"}`}
    >
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1 font-semibold uppercase tracking-wider transition-colors hover:text-ink ${
          aktif ? "text-ink" : "text-muted"
        } ${rataKanan ? "ml-auto justify-end" : ""}`}
      >
        <span>{label}</span>
        <span aria-hidden="true" className="font-mono text-[10px]">
          {aktif ? (arah === "asc" ? "↑" : "↓") : "↕"}
        </span>
      </button>
    </th>
  );
}

export function RekonsiliasiBatasClient({
  kdprov,
  kdkab,
  peran,
}: {
  kdprov: string;
  kdkab: string | null;
  peran: string;
}) {
  const adalahAdminProv = peran === PERAN_ADMIN_PROVINSI || !kdkab;
  const bisaAturPemeriksaan = peran === PERAN_ADMIN_PROVINSI;
  const kodeKabPengguna = kdkab ? kodeWilayah(kdprov, kdkab) : null;

  const [ringkasan, setRingkasan] = useState<RekonsiliasiBatasRingkasan | null>(
    null,
  );
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [diperbarui, setDiperbarui] = useState<string | null>(null);

  const [tabAktif, setTabAktif] = useState<"pasangan" | "kabkota" | "grafik">(
    "pasangan",
  );
  const [urutPasangan, setUrutPasangan] = useState<{
    kolom: KolomUrutPasangan;
    arah: ArahUrut;
  } | null>(null);
  const [urutKabKota, setUrutKabKota] = useState<{
    kolom: KolomUrutKabKota;
    arah: ArahUrut;
  }>({ kolom: "kdkab", arah: "asc" });
  const [filterKaresidenan, setFilterKaresidenan] = useState<string[]>([]);
  const [filterKabs, setFilterKabs] = useState<string[]>(
    kodeKabPengguna ? [kodeKabPengguna] : [],
  );
  const [filterStatuses, setFilterStatuses] = useState<string[]>([]);
  const [sedangUnduh, setSedangUnduh] = useState<string | null>(null);

  const semuaKab = useMemo(() => daftarKabupaten(kdprov), [kdprov]);
  const semuaKaresidenan = useMemo(() => daftarKaresidenan(kdprov), [kdprov]);

  const daftarKabAktif = useMemo(() => {
    if (filterKaresidenan.length > 0) {
      const setId = new Set(filterKaresidenan);
      const kodeSet = new Set<string>();
      for (const kar of semuaKaresidenan) {
        if (setId.has(kar.id)) {
          for (const kode of kar.kdkabList) {
            kodeSet.add(kode);
          }
        }
      }
      return Array.from(kodeSet);
    }
    return filterKabs;
  }, [filterKaresidenan, filterKabs, semuaKaresidenan]);

  // Modal pengaturan ambang: dimount hanya saat terbuka supaya state selalu
  // segar dan inputnya tidak tertimpa polling dari instance lama.
  const [modalAmbang, setModalAmbang] = useState(false);

  // State modal rincian pasangan
  const [pasangAktif, setPasangAktif] = useState<{
    kdkab_a: string;
    kdkab_b: string;
  } | null>(null);
  const [detailPasang, setDetailPasang] =
    useState<RekonsiliasiBatasDetail | null>(null);
  const [memuatDetail, setMemuatDetail] = useState(false);
  const [galatDetail, setGalatDetail] = useState<string | null>(null);
  const [filterJenisDetail, setFilterJenisDetail] = useState<string>("semua");
  const [koordinatDisalin, setKoordinatDisalin] = useState<number | null>(null);

  const controllerRef = useRef<AbortController | null>(null);

  const muatRingkasan = useCallback(
    (daftarKabSaring: string[]) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      const params = new URLSearchParams();
      if (adalahAdminProv && daftarKabSaring.length > 0) {
        for (const kode of daftarKabSaring) {
          params.append("kdkab", kode);
        }
      }
      const qs = params.toString();
      const url = `/rekonsiliasi-batas/ringkasan${qs ? `?${qs}` : ""}`;

      ambilJson<RekonsiliasiBatasRingkasan>(url, {
        signal: controller.signal,
      })
        .then((hasil) => {
          if (controller.signal.aborted) {
            return;
          }
          setRingkasan(hasil);
          setGalat(null);
          setDiperbarui(formatWaktu(new Date().toISOString()));
        })
        .catch((err: unknown) => {
          if (!adalahBatal(err)) {
            setGalat(pesanKesalahan(err));
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setMemuat(false);
          }
        });
    },
    [adalahAdminProv],
  );

  useEffect(() => {
    muatRingkasan(daftarKabAktif);
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        muatRingkasan(daftarKabAktif);
      }
    }, INTERVAL_MUAT_ULANG);
    return () => {
      window.clearInterval(interval);
      controllerRef.current?.abort();
    };
  }, [muatRingkasan, daftarKabAktif]);

  const bukaRincian = useCallback(async (kdkabA: string, kdkabB: string) => {
    setPasangAktif({ kdkab_a: kdkabA, kdkab_b: kdkabB });
    setFilterJenisDetail("semua");
    setMemuatDetail(true);
    setGalatDetail(null);
    try {
      const hasil = await ambilJson<RekonsiliasiBatasDetail>(
        `/rekonsiliasi-batas/pasang/${kdkabA}/${kdkabB}`,
      );
      setDetailPasang(hasil);
    } catch (err) {
      setGalatDetail(pesanKesalahan(err));
    } finally {
      setMemuatDetail(false);
    }
  }, []);

  async function handleUnduhGeojson(kdkabA: string, kdkabB: string) {
    const kunci = `geojson_${kdkabA}_${kdkabB}`;
    setSedangUnduh(kunci);
    try {
      await unduhBerkas(
        `/rekonsiliasi-batas/pasang/${kdkabA}/${kdkabB}/geojson`,
        `QC_Batas_${kdkabA}_${kdkabB}.geojson`,
      );
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setSedangUnduh(null);
    }
  }

  async function handleUnduhPetaFull(
    kdkabA: string,
    kdkabB: string,
    kdkabTarget: string,
  ) {
    const kunci = `peta_${kdkabA}_${kdkabB}_${kdkabTarget}`;
    setSedangUnduh(kunci);
    try {
      await unduhBerkas(
        `/rekonsiliasi-batas/pasang/${kdkabA}/${kdkabB}/peta/${kdkabTarget}`,
        `Peta_SLS_${kdkabTarget}.gpkg`,
      );
    } catch (err) {
      setGalat(pesanKesalahan(err));
    } finally {
      setSedangUnduh(null);
    }
  }

  function salinKoordinat(id: number, lat: number, lon: number) {
    const teks = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
    void navigator.clipboard?.writeText(teks);
    setKoordinatDisalin(id);
    window.setTimeout(() => {
      setKoordinatDisalin((sebelumnya) =>
        sebelumnya === id ? null : sebelumnya,
      );
    }, 1800);
  }

  function toggleUrutPasangan(kolom: KolomUrutPasangan) {
    setUrutPasangan((lama) => {
      if (lama?.kolom === kolom) {
        return { kolom, arah: lama.arah === "asc" ? "desc" : "asc" };
      }
      const arahDefault: ArahUrut =
        kolom === "overlap" || kolom === "gap" ? "desc" : "asc";
      return { kolom, arah: arahDefault };
    });
  }

  function toggleUrutKabKota(kolom: KolomUrutKabKota) {
    setUrutKabKota((lama) => {
      if (lama.kolom === kolom) {
        return { kolom, arah: lama.arah === "asc" ? "desc" : "asc" };
      }
      const arahDefault: ArahUrut =
        kolom === "kdkab" || kolom === "tetangga" ? "asc" : "desc";
      return { kolom, arah: arahDefault };
    });
  }

  const daftarBarisTersaring = useMemo(() => {
    const semua = ringkasan?.baris ?? [];
    const disaring =
      filterStatuses.length === 0
        ? semua
        : (() => {
            const setStatus = new Set(filterStatuses);
            return semua.filter((b) => setStatus.has(b.status));
          })();

    if (!urutPasangan) {
      return disaring;
    }

    const { kolom, arah } = urutPasangan;
    const faktor = arah === "asc" ? 1 : -1;
    return [...disaring].sort((a, b) => {
      let selisih = 0;
      if (kolom === "wilayah_a") {
        selisih = a.kdkab_a.localeCompare(b.kdkab_a);
      } else if (kolom === "wilayah_b") {
        selisih = a.kdkab_b.localeCompare(b.kdkab_b);
      } else if (kolom === "status") {
        selisih =
          (BOBOT_STATUS_BATAS[a.status] ?? 99) -
          (BOBOT_STATUS_BATAS[b.status] ?? 99);
      } else if (kolom === "overlap") {
        selisih = a.total_luas_overlap_m2 - b.total_luas_overlap_m2;
      } else if (kolom === "gap") {
        selisih = a.total_luas_gap_m2 - b.total_luas_gap_m2;
      }
      if (selisih !== 0) {
        return selisih * faktor;
      }
      return (
        a.kdkab_a.localeCompare(b.kdkab_a) ||
        a.kdkab_b.localeCompare(b.kdkab_b)
      );
    });
  }, [ringkasan, filterStatuses, urutPasangan]);

  const temuanDetailTersaring = useMemo(() => {
    const semua = detailPasang?.temuan ?? [];
    return semua.filter((t) => {
      if (filterJenisDetail !== "semua" && t.jenis !== filterJenisDetail) {
        return false;
      }
      return true;
    });
  }, [detailPasang, filterJenisDetail]);

  const rekapKabKotaTersaring = useMemo(() => {
    const semuaBaris = ringkasan?.baris ?? [];
    if (semuaBaris.length === 0) {
      return [];
    }

    const petaNama = new Map<string, string>();
    for (const k of semuaKab) {
      petaNama.set(k.kode, k.nama);
    }

    type ItemTetangga = {
      kdkab: string;
      nmkab: string;
      status: string;
      kdkab_a: string;
      kdkab_b: string;
      sudahDihitung: boolean;
    };

    type RekapSatuKab = {
      kdkab: string;
      nmkab: string;
      run_id: number | null;
      waktu: string | null | undefined;
      tanggal: string | null | undefined;
      pengunggah: string | null | undefined;
      ada_peta: boolean;
      pasanganPertama: { kdkab_a: string; kdkab_b: string } | null;
      tetangga: ItemTetangga[];
      clean: number;
      belum_clean: number;
      menunggu_tetangga: number;
      belum_unggah: number;
    };

    const petaRekap = new Map<string, RekapSatuKab>();

    function pastikanKab(
      kode: string,
      namaFallback: string,
      runId: number | null,
      waktu: string | null | undefined,
      tanggal: string | null | undefined,
      pengunggah: string | null | undefined,
      adaPeta: boolean,
      pasangan: { kdkab_a: string; kdkab_b: string },
    ): RekapSatuKab {
      let entri = petaRekap.get(kode);
      if (!entri) {
        entri = {
          kdkab: kode,
          nmkab: petaNama.get(kode) ?? namaFallback,
          run_id: runId,
          waktu,
          tanggal,
          pengunggah,
          ada_peta: adaPeta,
          pasanganPertama: pasangan,
          tetangga: [],
          clean: 0,
          belum_clean: 0,
          menunggu_tetangga: 0,
          belum_unggah: 0,
        };
        petaRekap.set(kode, entri);
      } else if (entri.run_id == null && runId != null) {
        entri.run_id = runId;
        entri.waktu = waktu;
        entri.tanggal = tanggal;
        entri.pengunggah = pengunggah;
        entri.ada_peta = adaPeta;
      }
      return entri;
    }

    for (const b of semuaBaris) {
      const sudahDihitung = b.status === "clean" || b.status === "belum_clean";
      const pas = { kdkab_a: b.kdkab_a, kdkab_b: b.kdkab_b };

      const entriA = pastikanKab(
        b.kdkab_a,
        b.nmkab_a,
        b.run_a_id,
        b.waktu_a,
        b.tanggal_a,
        b.pengunggah_a,
        Boolean(b.ada_peta_a ?? b.run_a_id),
        pas,
      );
      entriA.tetangga.push({
        kdkab: b.kdkab_b,
        nmkab: b.nmkab_b,
        status: b.status,
        kdkab_a: b.kdkab_a,
        kdkab_b: b.kdkab_b,
        sudahDihitung,
      });
      if (b.status === "clean") entriA.clean += 1;
      else if (b.status === "belum_clean") entriA.belum_clean += 1;
      else if (b.status === "menunggu_tetangga") entriA.menunggu_tetangga += 1;
      else entriA.belum_unggah += 1;

      const entriB = pastikanKab(
        b.kdkab_b,
        b.nmkab_b,
        b.run_b_id,
        b.waktu_b,
        b.tanggal_b,
        b.pengunggah_b,
        Boolean(b.ada_peta_b ?? b.run_b_id),
        pas,
      );
      entriB.tetangga.push({
        kdkab: b.kdkab_a,
        nmkab: b.nmkab_a,
        status: b.status,
        kdkab_a: b.kdkab_a,
        kdkab_b: b.kdkab_b,
        sudahDihitung,
      });
      if (b.status === "clean") entriB.clean += 1;
      else if (b.status === "belum_clean") entriB.belum_clean += 1;
      else if (b.status === "menunggu_tetangga") entriB.menunggu_tetangga += 1;
      else entriB.belum_unggah += 1;
    }

    const setKabSaring =
      daftarKabAktif.length > 0 ? new Set(daftarKabAktif) : null;
    const setStatusSaring =
      filterStatuses.length > 0 ? new Set(filterStatuses) : null;

    const hasil = Array.from(petaRekap.values()).filter((item) => {
      if (setKabSaring && !setKabSaring.has(item.kdkab)) {
        return false;
      }
      if (
        setStatusSaring &&
        !item.tetangga.some((t) => setStatusSaring.has(t.status))
      ) {
        return false;
      }
      return true;
    });

    for (const item of hasil) {
      item.tetangga.sort((a, b) => a.kdkab.localeCompare(b.kdkab));
    }

    const { kolom, arah } = urutKabKota;
    const faktor = arah === "asc" ? 1 : -1;
    hasil.sort((a, b) => {
      let selisih = 0;
      if (kolom === "kdkab") {
        selisih = a.kdkab.localeCompare(b.kdkab);
      } else if (kolom === "tetangga" || kolom === "total") {
        selisih = a.tetangga.length - b.tetangga.length;
      } else if (kolom === "clean") {
        selisih = a.clean - b.clean;
      } else if (kolom === "belum_clean") {
        selisih = a.belum_clean - b.belum_clean;
      } else if (kolom === "menunggu_tetangga") {
        selisih = a.menunggu_tetangga - b.menunggu_tetangga;
      } else if (kolom === "belum_unggah") {
        selisih = a.belum_unggah - b.belum_unggah;
      } else if (kolom === "progres") {
        const pA = a.tetangga.length > 0 ? a.clean / a.tetangga.length : 0;
        const pB = b.tetangga.length > 0 ? b.clean / b.tetangga.length : 0;
        selisih = pA - pB;
      }
      if (selisih !== 0) {
        return selisih * faktor;
      }
      return a.kdkab.localeCompare(b.kdkab);
    });

    return hasil;
  }, [ringkasan, semuaKab, daftarKabAktif, filterStatuses, urutKabKota]);

  // Data grafik memakai ulang rekap tab "Rekap per Kabupaten/Kota" supaya ikut
  // saringan yang sama. Urutannya diatur di dalam komponen grafik.
  const dataGrafikKabKota = useMemo(
    () =>
      rekapKabKotaTersaring.map((item) => {
        const nama = formatNamaKabKota(item.nmkab) || item.kdkab;
        return {
          kode: item.kdkab,
          nama,
          label: `${item.kdkab} ${nama}`,
          clean: item.clean,
          belum_clean: item.belum_clean,
          menunggu_tetangga: item.menunggu_tetangga,
          belum_unggah: item.belum_unggah,
          total: item.tetangga.length,
        };
      }),
    [rekapKabKotaTersaring],
  );

  const totalPasang = ringkasan?.total_pasang ?? 0;
  const jmlClean = ringkasan?.clean ?? 0;
  const jmlBelumClean = ringkasan?.belum_clean ?? 0;
  const jmlMenunggu = ringkasan?.menunggu_tetangga ?? 0;
  const jmlBelumUnggah = ringkasan?.belum_unggah ?? 0;
  const luasMin = ringkasan?.luas_min_m2 ?? 0;
  const persenClean =
    totalPasang > 0 ? Math.round((jmlClean / totalPasang) * 100) : 0;

  const opsiStatus = useMemo(
    () => [
      {
        nilai: "belum_clean",
        label: `Belum Clean (${formatAngka(jmlBelumClean)})`,
      },
      {
        nilai: "clean",
        label: `Clean (${formatAngka(jmlClean)})`,
      },
      {
        nilai: "menunggu_tetangga",
        label: `Menunggu Tetangga (${formatAngka(jmlMenunggu)})`,
      },
      {
        nilai: "belum_unggah",
        label: `Belum Unggah (${formatAngka(jmlBelumUnggah)})`,
      },
    ],
    [jmlBelumClean, jmlClean, jmlMenunggu, jmlBelumUnggah],
  );

  const opsiKaresidenan = useMemo(
    () =>
      semuaKaresidenan.map((k) => ({
        nilai: k.id,
        label: `${k.nama} (${k.kdkabList.length} kab/kota)`,
      })),
    [semuaKaresidenan],
  );

  const opsiKabupaten = useMemo(
    () =>
      semuaKab.map((k) => ({
        nilai: k.kode,
        label: `[${k.kode}] ${formatNamaKabKota(k.nama)}`,
      })),
    [semuaKab],
  );

  return (
    <div className="space-y-field">
      {/* Pita Ringkasan & Progres Pasangan Perbatasan */}
      <Panel>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1">
            <div className="flex flex-wrap items-baseline gap-2.5">
              <span className="font-mono text-2xl font-bold tabular-nums text-ink">
                {formatAngka(jmlClean)} / {formatAngka(totalPasang)}
              </span>
              <span className="text-sm font-semibold text-ink">
                pasang perbatasan berstatus Clean ({persenClean}%)
              </span>
            </div>
            <p className="text-xs text-muted">
              {luasMin <= 0 ? (
                <>
                  Tanpa toleransi: setiap gap dan overlap yang terdeteksi ikut
                  dihitung, sama dengan Topology Checker QGIS.
                </>
              ) : (
                <>
                  Batas toleransi{" "}
                  <span className="font-mono font-semibold tabular-nums text-ink">
                    {formatAmbang(luasMin)} m²
                  </span>
                  : gap atau overlap dengan luas kurang dari nilai ini diampuni
                  (tidak dihitung).
                </>
              )}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs">
            <TombolAksi
              varian="sekunder"
              onClick={() => {
                setMemuat(true);
                setGalat(null);
                void muatRingkasan(daftarKabAktif);
              }}
              disabled={memuat}
            >
              {memuat ? "Memuat..." : "Refresh"}
            </TombolAksi>

            {bisaAturPemeriksaan && (
              <TombolAksi
                varian="sekunder"
                onClick={() => setModalAmbang(true)}
              >
                Ubah ambang
              </TombolAksi>
            )}
          </div>
        </div>

        {/* Bar Progres Komposisi Status */}
        {totalPasang > 0 && (
          <div className="mt-4">
            <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-paper">
              {jmlClean > 0 && (
                <div
                  className="bg-success transition-all"
                  style={{ width: `${(jmlClean / totalPasang) * 100}%` }}
                  title={`Clean: ${jmlClean} pasang`}
                />
              )}
              {jmlBelumClean > 0 && (
                <div
                  className="bg-danger transition-all"
                  style={{ width: `${(jmlBelumClean / totalPasang) * 100}%` }}
                  title={`Belum Clean: ${jmlBelumClean} pasang`}
                />
              )}
              {jmlMenunggu > 0 && (
                <div
                  className="bg-warning transition-all"
                  style={{ width: `${(jmlMenunggu / totalPasang) * 100}%` }}
                  title={`Menunggu Tetangga: ${jmlMenunggu} pasang`}
                />
              )}
            </div>
          </div>
        )}

        {/* Filter Wilayah & Status (Dropdown Multi-Pilih) */}
        <div
          className={`mt-4 grid grid-cols-1 gap-3 border-t border-line pt-4 ${
            adalahAdminProv ? "sm:grid-cols-3" : "sm:grid-cols-1"
          }`}
        >
          {adalahAdminProv && (
            <MultiPilih
              label="Karesidenan"
              labelSemua={
                filterKabs.length > 0
                  ? "Nonaktif (Filter Kab/Kota aktif)"
                  : "Seluruh Karesidenan (6)"
              }
              tempatCari="Cari karesidenan..."
              opsi={opsiKaresidenan}
              terpilih={filterKaresidenan}
              nonaktif={filterKabs.length > 0}
              onTerapkan={(pilihan) => {
                const bersih =
                  pilihan.length === semuaKaresidenan.length ? [] : pilihan;
                setMemuat(true);
                setFilterKaresidenan(bersih);
                if (bersih.length > 0) {
                  setFilterKabs([]);
                }
              }}
            />
          )}

          {adalahAdminProv && (
            <MultiPilih
              label="Kabupaten/Kota"
              labelSemua={
                filterKaresidenan.length > 0
                  ? "Nonaktif (Filter Karesidenan aktif)"
                  : "Seluruh Kab/Kota (74 pasang)"
              }
              tempatCari="Cari kode atau nama kab/kota..."
              opsi={opsiKabupaten}
              terpilih={filterKabs}
              nonaktif={filterKaresidenan.length > 0}
              onTerapkan={(pilihan) => {
                const bersih =
                  pilihan.length === semuaKab.length ? [] : pilihan;
                setMemuat(true);
                setFilterKabs(bersih);
                if (bersih.length > 0) {
                  setFilterKaresidenan([]);
                }
              }}
            />
          )}

          <MultiPilih
            label="Status Pasangan Batas"
            labelSemua={`Semua Pasangan (${formatAngka(totalPasang)})`}
            tempatCari="Cari status batas..."
            opsi={opsiStatus}
            terpilih={filterStatuses}
            onTerapkan={(pilihan) => {
              const bersih =
                pilihan.length === opsiStatus.length ? [] : pilihan;
              setFilterStatuses(bersih);
            }}
          />
        </div>
      </Panel>

      {galat && (
        <div
          role="alert"
          className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-xs text-danger"
        >
          {galat}
        </div>
      )}

      {/* Tab Pilihan Tampilan: Daftar Pasangan, Rekap, dan Grafik per Kabupaten/Kota */}
      <div
        role="tablist"
        aria-label="Tampilan rekonsiliasi batas"
        className="flex flex-wrap gap-2 border-b border-line pb-2"
      >
        <button
          type="button"
          role="tab"
          aria-selected={tabAktif === "pasangan"}
          onClick={() => setTabAktif("pasangan")}
          className={`inline-flex min-h-9 items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
            tabAktif === "pasangan"
              ? "bg-brand text-white"
              : "border border-line bg-surface text-ink hover:bg-paper"
          }`}
        >
          <span>Daftar Pasangan Batas</span>
          <span
            className={`rounded px-1.5 py-0.5 font-mono text-[11px] tabular-nums ${
              tabAktif === "pasangan"
                ? "bg-white/20 text-white"
                : "bg-paper text-muted"
            }`}
          >
            {daftarBarisTersaring.length}
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tabAktif === "kabkota"}
          onClick={() => setTabAktif("kabkota")}
          className={`inline-flex min-h-9 items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
            tabAktif === "kabkota"
              ? "bg-brand text-white"
              : "border border-line bg-surface text-ink hover:bg-paper"
          }`}
        >
          <span>Rekap per Kabupaten/Kota</span>
          <span
            className={`rounded px-1.5 py-0.5 font-mono text-[11px] tabular-nums ${
              tabAktif === "kabkota"
                ? "bg-white/20 text-white"
                : "bg-paper text-muted"
            }`}
          >
            {rekapKabKotaTersaring.length}
          </span>
        </button>
        {dataGrafikKabKota.length >= 2 ? (
          <button
            type="button"
            role="tab"
            aria-selected={tabAktif === "grafik"}
            onClick={() => setTabAktif("grafik")}
            className={`inline-flex min-h-9 items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
              tabAktif === "grafik"
                ? "bg-brand text-white"
                : "border border-line bg-surface text-ink hover:bg-paper"
            }`}
          >
            <span>Grafik per Kabupaten/Kota</span>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[11px] tabular-nums ${
                tabAktif === "grafik"
                  ? "bg-white/20 text-white"
                  : "bg-paper text-muted"
              }`}
            >
              {dataGrafikKabKota.length}
            </span>
          </button>
        ) : null}
      </div>

      {/* Tab 1: Daftar Pasangan Perbatasan */}
      {tabAktif === "pasangan" ? (
      <Panel
        judul="Daftar Pasangan Perbatasan Kabupaten/Kota"
        deskripsi={
          diperbarui
            ? `Menampilkan ${daftarBarisTersaring.length} pasangan • Diperbarui ${diperbarui}`
            : `Menampilkan ${daftarBarisTersaring.length} pasangan`
        }
      >
        {memuat && !ringkasan ? (
          <p className="py-8 text-center text-xs text-muted">
            Memuat data rekonsiliasi batas...
          </p>
        ) : daftarBarisTersaring.length === 0 ? (
          <EmptyState judul="Tidak ada pasangan perbatasan yang cocok">
            Ubah saringan status atau pilihan kabupaten/kota untuk melihat
            pasangan perbatasan lainnya.
          </EmptyState>
        ) : (
          <div className="mt-3 max-h-[68vh] overflow-auto rounded-lg border border-line">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="sticky top-0 z-10 bg-paper shadow-[0_1px_0_0_var(--line)]">
                <tr className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                  <HeaderUrut
                    label="Wilayah A"
                    aktif={urutPasangan?.kolom === "wilayah_a"}
                    arah={urutPasangan?.arah ?? "asc"}
                    onClick={() => toggleUrutPasangan("wilayah_a")}
                  />
                  <HeaderUrut
                    label="Wilayah B (Tetangga)"
                    aktif={urutPasangan?.kolom === "wilayah_b"}
                    arah={urutPasangan?.arah ?? "asc"}
                    onClick={() => toggleUrutPasangan("wilayah_b")}
                  />
                  <HeaderUrut
                    label="Status Batas"
                    aktif={urutPasangan?.kolom === "status"}
                    arah={urutPasangan?.arah ?? "asc"}
                    onClick={() => toggleUrutPasangan("status")}
                  />
                  <HeaderUrut
                    label="Overlap"
                    rataKanan
                    aktif={urutPasangan?.kolom === "overlap"}
                    arah={urutPasangan?.arah ?? "desc"}
                    onClick={() => toggleUrutPasangan("overlap")}
                  />
                  <HeaderUrut
                    label="Gap"
                    rataKanan
                    aktif={urutPasangan?.kolom === "gap"}
                    arah={urutPasangan?.arah ?? "desc"}
                    onClick={() => toggleUrutPasangan("gap")}
                  />
                  <th className="px-3 py-2.5 text-right">
                    Aksi &amp; Berkas Pemeriksaan
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {daftarBarisTersaring.map(
                  (baris: RekonsiliasiBatasPasangBaris) => {
                    const kunci = `${baris.kdkab_a}_${baris.kdkab_b}`;
                    const kunciGeojson = `geojson_${kunci}`;
                    const kunciPetaA = `peta_${kunci}_${baris.kdkab_a}`;
                    const kunciPetaB = `peta_${kunci}_${baris.kdkab_b}`;
                    const sudahDihitung =
                      baris.status === "clean" ||
                      baris.status === "belum_clean";
                    const bisaUnduhPetaA = Boolean(
                      baris.ada_peta_a ?? baris.run_a_id,
                    );
                    const bisaUnduhPetaB = Boolean(
                      baris.ada_peta_b ?? baris.run_b_id,
                    );

                    return (
                      <tr
                        key={kunci}
                        className="transition-colors hover:bg-paper/70"
                      >
                        <td className="px-3 py-3 align-top">
                          <div className="flex items-center gap-1.5">
                            <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums text-ink">
                              {baris.kdkab_a}
                            </span>
                            <span className="font-medium text-ink">
                              {formatNamaKabKota(baris.nmkab_a)}
                            </span>
                          </div>
                          <div className="mt-1 space-y-0.5 text-[11px] text-muted">
                            {baris.run_a_id ? (
                              <>
                                <div>
                                  Run #{baris.run_a_id} •{" "}
                                  {formatWaktuRun(
                                    baris.waktu_a,
                                    baris.tanggal_a,
                                  )}
                                </div>
                                {baris.pengunggah_a && (
                                  <div className="text-[11px] text-muted">
                                    {baris.pengunggah_a}
                                  </div>
                                )}
                              </>
                            ) : (
                              <span className="text-warning">
                                Belum unggah peta V
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="px-3 py-3 align-top">
                          <div className="flex items-center gap-1.5">
                            <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums text-ink">
                              {baris.kdkab_b}
                            </span>
                            <span className="font-medium text-ink">
                              {formatNamaKabKota(baris.nmkab_b)}
                            </span>
                          </div>
                          <div className="mt-1 space-y-0.5 text-[11px] text-muted">
                            {baris.run_b_id ? (
                              <>
                                <div>
                                  Run #{baris.run_b_id} •{" "}
                                  {formatWaktuRun(
                                    baris.waktu_b,
                                    baris.tanggal_b,
                                  )}
                                </div>
                                {baris.pengunggah_b && (
                                  <div className="text-[11px] text-muted">
                                    {baris.pengunggah_b}
                                  </div>
                                )}
                              </>
                            ) : (
                              <span className="text-warning">
                                Belum unggah peta V
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="px-3 py-3 align-top">
                          <BadgeStatusBatas status={baris.status} />
                          {baris.pesan && !sudahDihitung && (
                            <p className="mt-1 max-w-xs text-[11px] text-muted">
                              {baris.pesan}
                            </p>
                          )}
                        </td>

                        <td className="px-3 py-3 align-top text-right font-mono tabular-nums">
                          {sudahDihitung ? (
                            <span
                              className={
                                baris.jumlah_overlap > 0 ||
                                baris.total_luas_overlap_m2 > 0
                                  ? "font-bold text-danger"
                                  : "text-muted"
                              }
                            >
                              {formatLuas(baris.total_luas_overlap_m2)} m²
                            </span>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>

                        <td className="px-3 py-3 align-top text-right font-mono tabular-nums">
                          {sudahDihitung ? (
                            <span
                              className={
                                baris.jumlah_gap > 0 ||
                                baris.total_luas_gap_m2 > 0
                                  ? "font-bold text-warning"
                                  : "text-muted"
                              }
                            >
                              {formatLuas(baris.total_luas_gap_m2)} m²
                            </span>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>

                        <td className="px-3 py-3 align-top text-right">
                          <div className="inline-flex flex-wrap justify-end gap-1.5">
                            {sudahDihitung && (
                              <button
                                type="button"
                                onClick={() =>
                                  void bukaRincian(
                                    baris.kdkab_a,
                                    baris.kdkab_b,
                                  )
                                }
                                className="inline-flex min-h-9 items-center rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink transition-colors hover:bg-paper"
                              >
                                Rincian SLS
                              </button>
                            )}
                            {baris.ada_geojson && baris.total_temuan > 0 && (
                              <button
                                type="button"
                                disabled={sedangUnduh === kunciGeojson}
                                onClick={() =>
                                  void handleUnduhGeojson(
                                    baris.kdkab_a,
                                    baris.kdkab_b,
                                  )
                                }
                                className="inline-flex min-h-9 items-center rounded-lg bg-brand px-2.5 py-1 text-xs font-semibold text-white transition-colors hover:bg-brand-strong disabled:opacity-50"
                              >
                                {sedangUnduh === kunciGeojson
                                  ? "Mengunduh..."
                                  : "Unduh GeoJSON QC"}
                              </button>
                            )}
                            {bisaUnduhPetaA && (
                              <button
                                type="button"
                                disabled={sedangUnduh === kunciPetaA}
                                onClick={() =>
                                  void handleUnduhPetaFull(
                                    baris.kdkab_a,
                                    baris.kdkab_b,
                                    baris.kdkab_a,
                                  )
                                }
                                title={`Unduh berkas peta full Validasi SLS [${baris.kdkab_a}] ${baris.nmkab_a}`}
                                className="inline-flex min-h-9 items-center rounded-lg border border-line bg-surface px-2.5 py-1 font-mono text-xs font-medium tabular-nums text-ink transition-colors hover:bg-paper disabled:opacity-50"
                              >
                                {sedangUnduh === kunciPetaA
                                  ? "Mengunduh..."
                                  : `Peta Full ${baris.kdkab_a}`}
                              </button>
                            )}
                            {bisaUnduhPetaB && (
                              <button
                                type="button"
                                disabled={sedangUnduh === kunciPetaB}
                                onClick={() =>
                                  void handleUnduhPetaFull(
                                    baris.kdkab_a,
                                    baris.kdkab_b,
                                    baris.kdkab_b,
                                  )
                                }
                                title={`Unduh berkas peta full Validasi SLS [${baris.kdkab_b}] ${baris.nmkab_b}`}
                                className="inline-flex min-h-9 items-center rounded-lg border border-line bg-surface px-2.5 py-1 font-mono text-xs font-medium tabular-nums text-ink transition-colors hover:bg-paper disabled:opacity-50"
                              >
                                {sedangUnduh === kunciPetaB
                                  ? "Mengunduh..."
                                  : `Peta Full ${baris.kdkab_b}`}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  },
                )}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      ) : tabAktif === "kabkota" ? (
      /* Tab 2: Rekap per Kabupaten/Kota */
      <Panel
        judul="Rekap Perbatasan per Kabupaten/Kota"
        deskripsi={
          diperbarui
            ? `Menampilkan ${rekapKabKotaTersaring.length} kabupaten/kota • Diperbarui ${diperbarui}`
            : `Menampilkan ${rekapKabKotaTersaring.length} kabupaten/kota`
        }
      >
        {memuat && !ringkasan ? (
          <p className="py-8 text-center text-xs text-muted">
            Memuat data rekonsiliasi batas...
          </p>
        ) : rekapKabKotaTersaring.length === 0 ? (
          <EmptyState judul="Tidak ada kabupaten/kota yang cocok">
            Ubah saringan status atau pilihan wilayah untuk melihat rekap
            kabupaten/kota lainnya.
          </EmptyState>
        ) : (
          <div className="mt-3 max-h-[68vh] overflow-auto rounded-lg border border-line">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="sticky top-0 z-10 bg-paper shadow-[0_1px_0_0_var(--line)]">
                <tr className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                  <HeaderUrut
                    label="Kabupaten/Kota"
                    aktif={urutKabKota.kolom === "kdkab"}
                    arah={urutKabKota.arah}
                    onClick={() => toggleUrutKabKota("kdkab")}
                  />
                  <HeaderUrut
                    label="Kab/Kota Tetangga"
                    aktif={urutKabKota.kolom === "tetangga"}
                    arah={urutKabKota.arah}
                    onClick={() => toggleUrutKabKota("tetangga")}
                  />
                  <HeaderUrut
                    label="Total"
                    rataKanan
                    aktif={urutKabKota.kolom === "total"}
                    arah={urutKabKota.arah}
                    onClick={() => toggleUrutKabKota("total")}
                  />
                  <HeaderUrut
                    label="Clean"
                    rataKanan
                    aktif={urutKabKota.kolom === "clean"}
                    arah={urutKabKota.arah}
                    onClick={() => toggleUrutKabKota("clean")}
                  />
                  <HeaderUrut
                    label="Belum Clean"
                    rataKanan
                    aktif={urutKabKota.kolom === "belum_clean"}
                    arah={urutKabKota.arah}
                    onClick={() => toggleUrutKabKota("belum_clean")}
                  />
                  <HeaderUrut
                    label="Menunggu"
                    rataKanan
                    aktif={urutKabKota.kolom === "menunggu_tetangga"}
                    arah={urutKabKota.arah}
                    onClick={() => toggleUrutKabKota("menunggu_tetangga")}
                  />
                  <HeaderUrut
                    label="Belum Unggah"
                    rataKanan
                    aktif={urutKabKota.kolom === "belum_unggah"}
                    arah={urutKabKota.arah}
                    onClick={() => toggleUrutKabKota("belum_unggah")}
                  />
                  <HeaderUrut
                    label="Progres"
                    rataKanan
                    aktif={urutKabKota.kolom === "progres"}
                    arah={urutKabKota.arah}
                    onClick={() => toggleUrutKabKota("progres")}
                  />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rekapKabKotaTersaring.map((item) => {
                  const totalTetangga = item.tetangga.length;
                  const persenKab =
                    totalTetangga > 0
                      ? Math.round((item.clean / totalTetangga) * 100)
                      : 0;
                  return (
                    <tr
                      key={item.kdkab}
                      className="transition-colors hover:bg-paper/70"
                    >
                      <td className="px-3 py-3 align-top">
                        <div className="flex items-center gap-1.5">
                          <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums text-ink">
                            {item.kdkab}
                          </span>
                          <span className="font-medium text-ink">
                            {formatNamaKabKota(item.nmkab)}
                          </span>
                        </div>
                        <div className="mt-1 space-y-0.5 text-[11px] text-muted">
                          {item.run_id ? (
                            <>
                              <div>
                                Run #{item.run_id} •{" "}
                                {formatWaktuRun(item.waktu, item.tanggal)}
                              </div>
                              {item.pengunggah && (
                                <div className="text-[11px] text-muted">
                                  {item.pengunggah}
                                </div>
                              )}
                            </>
                          ) : (
                            <span className="text-warning">
                              Belum unggah peta V
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="px-3 py-3 align-top">
                        <div className="flex flex-wrap gap-1.5">
                          {item.tetangga.map((t) => {
                            const kelasWarna =
                              t.status === "clean"
                                ? "border-success/25 bg-success-soft text-success"
                                : t.status === "belum_clean"
                                  ? "border-danger/25 bg-danger-soft text-danger"
                                  : t.status === "menunggu_tetangga"
                                    ? "border-warning/30 bg-amber-50 text-warning"
                                    : "border-line bg-paper text-muted";
                            const isi = (
                              <>
                                <span className="font-mono font-semibold tabular-nums">
                                  {t.kdkab}
                                </span>
                                <span>{formatNamaKabKota(t.nmkab)}</span>
                              </>
                            );
                            return t.sudahDihitung ? (
                              <button
                                key={t.kdkab}
                                type="button"
                                onClick={() =>
                                  void bukaRincian(t.kdkab_a, t.kdkab_b)
                                }
                                title={`Klik untuk melihat rincian batas ${item.kdkab} ↔ ${t.kdkab}`}
                                className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium transition-opacity hover:opacity-80 ${kelasWarna}`}
                              >
                                {isi}
                              </button>
                            ) : (
                              <span
                                key={t.kdkab}
                                className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${kelasWarna}`}
                              >
                                {isi}
                              </span>
                            );
                          })}
                        </div>
                      </td>

                      <td className="px-3 py-3 align-top text-right font-mono font-semibold tabular-nums text-ink">
                        {totalTetangga}
                      </td>

                      <td className="px-3 py-3 align-top text-right font-mono tabular-nums">
                        <span
                          className={
                            item.clean > 0
                              ? "font-bold text-success"
                              : "text-muted"
                          }
                        >
                          {item.clean}
                        </span>
                      </td>

                      <td className="px-3 py-3 align-top text-right font-mono tabular-nums">
                        <span
                          className={
                            item.belum_clean > 0
                              ? "font-bold text-danger"
                              : "text-muted"
                          }
                        >
                          {item.belum_clean}
                        </span>
                      </td>

                      <td className="px-3 py-3 align-top text-right font-mono tabular-nums">
                        <span
                          className={
                            item.menunggu_tetangga > 0
                              ? "font-semibold text-warning"
                              : "text-muted"
                          }
                        >
                          {item.menunggu_tetangga}
                        </span>
                      </td>

                      <td className="px-3 py-3 align-top text-right font-mono tabular-nums text-muted">
                        {item.belum_unggah}
                      </td>

                      <td className="px-3 py-3 align-top text-right font-mono font-semibold tabular-nums text-ink">
                        {persenKab}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      ) : (
      /* Tab 3: Grafik per Kabupaten/Kota */
      <Panel judul="Pemeriksaan Batas per Kabupaten/Kota" judulRata="tengah">
        <GrafikBatasKabKota data={dataGrafikKabKota} />
      </Panel>
      )}

      {/* Modal Rincian Temuan Pasangan Perbatasan */}
      {pasangAktif && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="judul-modal-rekonsiliasi"
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-3 sm:p-6"
        >
          <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-xl">
            {/* Header Modal */}
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-4">
              <div>
                <h2
                  id="judul-modal-rekonsiliasi"
                  className="text-sm font-bold text-ink sm:text-base"
                >
                  Rincian Batas:{" "}
                  {detailPasang
                    ? `[${detailPasang.kdkab_a}] ${formatNamaKabKota(detailPasang.nmkab_a)} ↔ [${detailPasang.kdkab_b}] ${formatNamaKabKota(detailPasang.nmkab_b)}`
                    : `${pasangAktif.kdkab_a} ↔ ${pasangAktif.kdkab_b}`}
                </h2>
                <p className="mt-0.5 text-xs text-muted">
                  Daftar poligon SLS yang bersinggungan pada area Overlap maupun
                  Gap di sepanjang garis perbatasan kedua kabupaten/kota.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {detailPasang &&
                  Boolean(detailPasang.ada_peta_a ?? detailPasang.run_a_id) && (
                    <button
                      type="button"
                      onClick={() =>
                        void handleUnduhPetaFull(
                          pasangAktif.kdkab_a,
                          pasangAktif.kdkab_b,
                          pasangAktif.kdkab_a,
                        )
                      }
                      className="inline-flex min-h-9 items-center rounded-lg border border-line bg-surface px-3 py-1.5 font-mono text-xs font-medium tabular-nums text-ink hover:bg-paper"
                    >
                      Peta Full {pasangAktif.kdkab_a}
                    </button>
                  )}
                {detailPasang &&
                  Boolean(detailPasang.ada_peta_b ?? detailPasang.run_b_id) && (
                    <button
                      type="button"
                      onClick={() =>
                        void handleUnduhPetaFull(
                          pasangAktif.kdkab_a,
                          pasangAktif.kdkab_b,
                          pasangAktif.kdkab_b,
                        )
                      }
                      className="inline-flex min-h-9 items-center rounded-lg border border-line bg-surface px-3 py-1.5 font-mono text-xs font-medium tabular-nums text-ink hover:bg-paper"
                    >
                      Peta Full {pasangAktif.kdkab_b}
                    </button>
                  )}
                {detailPasang?.ada_geojson && detailPasang.total_temuan > 0 && (
                  <button
                    type="button"
                    onClick={() =>
                      void handleUnduhGeojson(
                        pasangAktif.kdkab_a,
                        pasangAktif.kdkab_b,
                      )
                    }
                    className="inline-flex min-h-9 items-center rounded-lg bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-strong"
                  >
                    Unduh GeoJSON QC
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setPasangAktif(null);
                    setDetailPasang(null);
                  }}
                  className="inline-flex min-h-9 items-center rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink hover:bg-paper"
                >
                  Tutup
                </button>
              </div>
            </div>

            {/* Filter Rincian */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-paper px-5 py-2.5 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-muted">Jenis:</span>
                {[
                  { id: "semua", label: "Semua" },
                  { id: "overlap", label: "Overlap" },
                  { id: "gap", label: "Gap" },
                ].map((j) => (
                  <button
                    key={j.id}
                    type="button"
                    onClick={() => setFilterJenisDetail(j.id)}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                      filterJenisDetail === j.id
                        ? "bg-brand text-white"
                        : "bg-surface text-ink hover:bg-paper"
                    }`}
                  >
                    {j.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Isi Tabel Rincian */}
            <div className="flex-1 overflow-y-auto p-5">
              {memuatDetail ? (
                <p className="py-10 text-center text-xs text-muted">
                  Memuat rincian titik perbatasan...
                </p>
              ) : galatDetail ? (
                <div className="rounded-lg border border-danger/30 bg-danger-soft p-4 text-xs text-danger">
                  {galatDetail}
                </div>
              ) : temuanDetailTersaring.length === 0 ? (
                <EmptyState judul="Tidak ada temuan pada saringan ini">
                  Pasangan perbatasan ini bersih atau tidak memiliki temuan
                  dengan kriteria filter yang dipilih.
                </EmptyState>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left text-xs">
                    <thead className="sticky top-0 z-10 bg-paper shadow-[0_1px_0_0_var(--line)]">
                      <tr className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                        <th className="px-3 py-2">No</th>
                        <th className="px-3 py-2">Jenis</th>
                        <th className="px-3 py-2">
                          SLS [{detailPasang?.kdkab_a}]{" "}
                          {formatNamaKabKota(detailPasang?.nmkab_a)}
                        </th>
                        <th className="px-3 py-2">
                          SLS [{detailPasang?.kdkab_b}]{" "}
                          {formatNamaKabKota(detailPasang?.nmkab_b)}
                        </th>
                        <th className="px-3 py-2 text-right">Luas (m²)</th>
                        <th className="px-3 py-2 text-right">
                          Koordinat (Lat, Lon)
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {temuanDetailTersaring.map((item, idx) => (
                        <tr
                          key={item.id}
                          className="hover:bg-paper/70"
                        >
                          <td className="px-3 py-2.5 font-mono text-muted tabular-nums">
                            {idx + 1}
                          </td>
                          <td className="px-3 py-2.5">
                            <span
                              className={`inline-flex rounded border px-2 py-0.5 text-[11px] font-bold uppercase ${
                                item.jenis === "overlap"
                                  ? "border-danger/25 bg-danger-soft text-danger"
                                  : "border-warning/30 bg-amber-50 text-warning"
                              }`}
                            >
                              {item.jenis}
                            </span>
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="font-mono font-semibold tabular-nums text-ink">
                              {item.idsubsls_a ?? item.idsls_a ?? "-"}
                            </div>
                            <div className="text-[11px] text-muted">
                              {item.nmsls_a ?? "-"}
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="font-mono font-semibold tabular-nums text-ink">
                              {item.idsubsls_b ?? item.idsls_b ?? "-"}
                            </div>
                            <div className="text-[11px] text-muted">
                              {item.nmsls_b ?? "-"}
                            </div>
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono font-semibold tabular-nums text-ink">
                            {formatLuas(item.luas_m2)}
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            <button
                              type="button"
                              onClick={() =>
                                salinKoordinat(item.id, item.lat, item.lon)
                              }
                              title="Klik untuk menyalin koordinat ke clipboard"
                              className="inline-flex items-center gap-1.5 rounded border border-line bg-surface px-2 py-1 font-mono text-[11px] tabular-nums text-ink hover:bg-paper"
                            >
                              <span>
                                {item.lat.toFixed(6)}, {item.lon.toFixed(6)}
                              </span>
                              <span className="text-[10px] font-sans font-semibold text-brand">
                                {koordinatDisalin === item.id
                                  ? "Tersalin!"
                                  : "Salin"}
                              </span>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal pengaturan ambang pemeriksaan batas (khusus Admin Provinsi) */}
      {modalAmbang && (
        <PengaturanPemeriksaanBatas
          onTutup={() => setModalAmbang(false)}
          onSelesai={() => {
            setMemuat(true);
            void muatRingkasan(daftarKabAktif);
          }}
        />
      )}
    </div>
  );
}
