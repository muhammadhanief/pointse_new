"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { MultiPilih } from "@/components/dashboard/multi-pilih";
import { Modal } from "@/components/dashboard/modal";
import { EmptyState, Panel, TombolAksi } from "@/components/dashboard/ui";
import { PenjelasanJenis } from "@/components/anomali/penjelasan-jenis";
import { LABEL_JENIS } from "@/lib/anomali/istilah";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
  unduhBerkas,
} from "@/lib/api/klien";
import type {
  Anomali,
  AnomaliBaris,
  AnomaliRun,
  DaftarAnomaliRun,
  HasilKonfirmasi,
  PermintaanKonfirmasi,
  StatusKonfirmasi,
} from "@/lib/api/types";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";
import { PERAN_ADMIN_PROVINSI } from "@/lib/auth/peran";
import { daftarKabupaten } from "@/lib/wilayah/kabupaten";

const BATAS = 50;
/** Ukuran halaman yang bisa dipilih; "semua" menampilkan seluruh baris. */
const PILIHAN_BATAS = [10, 20, 50] as const;
/** Batas maksimum baris per permintaan ``/anomali`` (API: le=500). */
const BATAS_PERMINTAAN = 500;
/** Header tabel menempel di atas supaya tetap terlihat saat isi digulir. */
const KELAS_HEAD =
  "sticky top-0 z-10 bg-paper px-3 py-2 font-semibold after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-line";
/** Header kolom kiri: menempel ke atas sekaligus ke kiri (sudut). */
const KELAS_HEAD_KIRI =
  "sticky top-0 z-20 bg-paper px-3 py-2 font-semibold after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-line";
/** Sel kiri yang ikut menempel saat tabel digulir ke samping. */
const KELAS_SEL_KIRI = "sticky left-0 z-10 w-10 bg-surface px-2 py-2";
const KELAS_STATUS_KIRI =
  "sticky left-10 z-10 min-w-[10.5rem] border-r border-line bg-surface px-3 py-2";

/** Isi dropdown status saat API lama belum mengirim ``status_pilihan``. */
const STATUS_BAWAAN: StatusKonfirmasi[] = [
  { kode: "belum", label: "Belum dikonfirmasi", jumlah: 0 },
  { kode: "akan_diperbaiki", label: "Akan Diperbaiki", jumlah: 0 },
  { kode: "sesuai_kenyataan", label: "Sesuai Kondisi Kenyataan", jumlah: 0 },
];

type UkuranHalaman = number | "semua";
type KodeStatus = "akan_diperbaiki" | "sesuai_kenyataan";

function teks(nilai: string | null | undefined): string {
  return nilai && nilai.trim() !== "" ? nilai : "–";
}

function kelasBadge(status: string | null | undefined): string {
  if (status === "sesuai_kenyataan") {
    return "border-success/30 bg-success-soft text-success";
  }
  if (status === "akan_diperbaiki") {
    return "border-accent/30 bg-accent-soft text-accent";
  }
  return "border-line bg-paper text-muted";
}

/** Tombol salin kecil untuk id/kode yang panjang. */
function TombolSalin({ nilai, label }: { nilai: string | null; label: string }) {
  const [tersalin, setTersalin] = useState(false);
  if (!nilai) {
    return null;
  }
  return (
    <button
      type="button"
      title={`Salin ${label}`}
      aria-label={`Salin ${label}`}
      onClick={async (kejadian) => {
        kejadian.stopPropagation();
        try {
          await navigator.clipboard.writeText(nilai);
          setTersalin(true);
          window.setTimeout(() => setTersalin(false), 1200);
        } catch {
          setTersalin(false);
        }
      }}
      className="ml-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] text-muted transition-colors hover:bg-paper hover:text-ink"
    >
      {tersalin ? "✓" : "⧉"}
    </button>
  );
}

export function AnomaliClient({
  kdprov,
  kdkabAwal,
  peran,
}: {
  kdprov: string;
  kdkabAwal: string | null;
  peran: string;
}) {
  const opsi = daftarKabupaten(kdprov);
  const adminProvinsi = peran === PERAN_ADMIN_PROVINSI;
  // Admin provinsi: semua kabupaten/kota tercentang. Petugas kabupaten: hanya
  // kabupaten/kotanya sendiri. Jenis pencermatan kosong = semua jenis.
  const [kdkabs, setKdkabs] = useState<string[]>(() =>
    kdkabAwal ? [kdkabAwal] : opsi.map((satu) => satu.kode),
  );
  const [jenises, setJenises] = useState<string[]>([]);
  const [cari, setCari] = useState("");
  const [kataKunci, setKataKunci] = useState("");
  // Default "belum": yang paling perlu dikerjakan lebih dulu.
  const [statusFilter, setStatusFilter] = useState("belum");
  const [halaman, setHalaman] = useState(0);
  const [batas, setBatas] = useState<UkuranHalaman>(BATAS);
  const [data, setData] = useState<Anomali | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const [berhasil, setBerhasil] = useState<string | null>(null);
  const [mengunduh, setMengunduh] = useState(false);
  const [bukaPenjelasan, setBukaPenjelasan] = useState(false);
  // Riwayat run B sukses milik kabupaten yang sedang dipilih (dropdown riwayat).
  const [riwayat, setRiwayat] = useState<AnomaliRun[]>([]);
  // ``null`` = run terakhir (default). Hanya berlaku saat tepat satu kabupaten.
  const [runTerpilih, setRunTerpilih] = useState<number | null>(null);
  // Pilihan untuk aksi massal: id baris tertentu, atau seluruh hasil filter.
  const [pilihan, setPilihan] = useState<Set<number>>(() => new Set());
  const [pilihSemua, setPilihSemua] = useState(false);
  const kepalaPilih = useRef<HTMLInputElement>(null);
  // Drawer konfirmasi satu titik.
  const [drawer, setDrawer] = useState<AnomaliBaris | null>(null);
  const [formStatus, setFormStatus] = useState<KodeStatus>("akan_diperbaiki");
  const [formCatatan, setFormCatatan] = useState("");
  // Modal keterangan sekali untuk aksi massal "Sesuai Kondisi Kenyataan".
  const [bukaMassal, setBukaMassal] = useState(false);
  const [massalCatatan, setMassalCatatan] = useState("");
  // Permintaan klarifikasi admin provinsi untuk titik di drawer.
  const [bukaKlarifikasi, setBukaKlarifikasi] = useState(false);
  const [klarifikasiCatatan, setKlarifikasiCatatan] = useState("");
  const [mengirim, setMengirim] = useState(false);
  const kdkabSatu = kdkabs.length === 1 ? kdkabs[0] : null;

  // Parameter /anomali untuk satu permintaan. Limit/offset eksplisit supaya
  // mode "Semua" bisa menyusuri halaman sampai seluruh baris terkumpul.
  const parameter = useCallback(
    (ukuran: number, halamanMuat: number) => {
      const isi = new URLSearchParams({
        kdprov,
        limit: String(ukuran),
        offset: String(halamanMuat * ukuran),
      });
      for (const kode of kdkabs) {
        isi.append("kdkab", kode);
      }
      for (const kode of jenises) {
        isi.append("jenis", kode);
      }
      if (statusFilter) {
        isi.set("status", statusFilter);
      }
      if (kataKunci) {
        isi.set("q", kataKunci);
      }
      if (kdkabSatu && runTerpilih != null) {
        isi.set("run_b_id", String(runTerpilih));
      }
      return isi;
    },
    [kdprov, kdkabs, jenises, statusFilter, kataKunci, kdkabSatu, runTerpilih],
  );

  const muat = useCallback(
    async (signal?: AbortSignal) => {
      if (kdkabs.length === 0) {
        setData(null);
        setMemuat(false);
        return;
      }
      setMemuat(true);
      setGalat(null);
      try {
        if (batas === "semua") {
          // API membatasi 500 baris per permintaan, jadi halaman disusuri sampai
          // seluruh baris terkumpul sebelum ditampilkan.
          const kumpulan: AnomaliBaris[] = [];
          let dasar: Anomali | null = null;
          for (let langkah = 0; ; langkah += 1) {
            const hasil = await ambilJson<Anomali>(
              `/anomali?${parameter(BATAS_PERMINTAAN, langkah)}`,
              { signal },
            );
            dasar = dasar ?? hasil;
            kumpulan.push(...hasil.baris);
            if (hasil.baris.length === 0 || kumpulan.length >= hasil.total) {
              break;
            }
          }
          if (dasar) {
            setData({ ...dasar, baris: kumpulan });
          }
        } else {
          const hasil = await ambilJson<Anomali>(
            `/anomali?${parameter(batas, halaman)}`,
            { signal },
          );
          setData(hasil);
        }
      } catch (kesalahan) {
        if (!adalahBatal(kesalahan)) {
          setGalat(pesanKesalahan(kesalahan));
        }
      } finally {
        if (!signal?.aborted) {
          setMemuat(false);
        }
      }
    },
    [kdkabs.length, batas, halaman, parameter],
  );

  useEffect(() => {
    const kendali = new AbortController();
    void muat(kendali.signal);
    return () => kendali.abort();
  }, [muat]);

  // Muat riwayat run kabupaten yang dipilih. Ganti kabupaten/kota -> balik ke
  // run terakhir (pilihan lama milik kabupaten lain tidak berlaku).
  useEffect(() => {
    setRunTerpilih(null);
    if (!kdkabSatu) {
      setRiwayat([]);
      return;
    }
    const kendali = new AbortController();
    void (async () => {
      try {
        const isi = new URLSearchParams({ kdprov, kdkab: kdkabSatu });
        const hasil = await ambilJson<DaftarAnomaliRun>(
          `/anomali/riwayat?${isi}`,
          { signal: kendali.signal },
        );
        setRiwayat(hasil.baris);
      } catch (kesalahan) {
        if (!adalahBatal(kesalahan)) {
          setRiwayat([]);
        }
      }
    })();
    return () => kendali.abort();
  }, [kdprov, kdkabSatu]);

  // Kunci gulir latar saat drawer/modal terbuka.
  const adaPanel = drawer !== null || bukaMassal || bukaKlarifikasi;
  useEffect(() => {
    if (!adaPanel) {
      return;
    }
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
    };
  }, [adaPanel]);

  useEffect(() => {
    if (!adaPanel) {
      return;
    }
    const padaTombol = (kejadian: KeyboardEvent) => {
      if (kejadian.key === "Escape") {
        if (bukaKlarifikasi) {
          setBukaKlarifikasi(false);
          return;
        }
        if (bukaMassal) {
          setBukaMassal(false);
          return;
        }
        setDrawer(null);
      }
    };
    window.addEventListener("keydown", padaTombol);
    return () => window.removeEventListener("keydown", padaTombol);
  }, [adaPanel, bukaKlarifikasi, bukaMassal]);

  // ``runs`` baru ada di backend versi ini; sisa pakai ``run`` supaya halaman
  // tetap hidup saat frontend lebih dulu diperbarui.
  const runs = data?.runs ?? (data?.run ? [data.run] : []);
  const jenisTerpilih =
    jenises.length === 1
      ? data?.jenis.find((satu) => satu.kode === jenises[0])
      : undefined;
  const totalSemua =
    data?.jenis.reduce((jumlah, satu) => jumlah + satu.jumlah, 0) ?? 0;
  const total = data?.total ?? 0;
  const ukuranHalaman = batas === "semua" ? total : batas;
  const mulai = total === 0 ? 0 : halaman * ukuranHalaman + 1;
  const akhir = Math.min(total, (halaman + 1) * ukuranHalaman);
  const target = runs.reduce((jumlah, satu) => jumlah + satu.target, 0);
  const selesai = runs.reduce((jumlah, satu) => jumlah + satu.selesai, 0);
  const perluHitungUlang = runs.some((satu) => satu.anomali_versi === 0);
  const banyakKabupaten = kdkabs.length > 1;
  // API lama belum mengirim ``id`` baris, sehingga aksi konfirmasi tidak bisa
  // dipakai. Beri tahu penyebabnya, jangan hanya menonaktifkan tombol diam-diam.
  const apiLama =
    (data?.baris.length ?? 0) > 0 && data!.baris.every((baris) => baris.id == null);

  const ringkasan = data?.ringkasan ?? {
    total: 0,
    terkonfirmasi: 0,
    belum: 0,
    per_status: [],
  };
  const persenKonfirmasi =
    ringkasan.total > 0
      ? Math.round((ringkasan.terkonfirmasi / ringkasan.total) * 100)
      : 0;
  const statusPilihan =
    data?.status_pilihan && data.status_pilihan.length > 0
      ? data.status_pilihan
      : STATUS_BAWAAN;

  const barisHalaman = data?.baris ?? [];
  const semuaHalamanDipilih =
    pilihSemua ||
    (barisHalaman.length > 0 &&
      barisHalaman.every(
        (baris) => baris.id != null && pilihan.has(baris.id),
      ));
  const sebagianHalaman =
    pilihSemua ||
    barisHalaman.some((baris) => baris.id != null && pilihan.has(baris.id));
  const jumlahDipilih = pilihSemua ? total : pilihan.size;
  const adaPilihan = pilihSemua || pilihan.size > 0;

  useEffect(() => {
    if (kepalaPilih.current) {
      kepalaPilih.current.indeterminate =
        sebagianHalaman && !semuaHalamanDipilih;
    }
  }, [sebagianHalaman, semuaHalamanDipilih]);

  const labelKabupaten = useMemo(() => {
    const peta = new Map(opsi.map((satu) => [satu.kode, satu.nama]));
    return (kode: string | null) =>
      kode ? (peta.get(kode) ?? kode) : "–";
  }, [opsi]);

  const labelJenis = useMemo(() => {
    const peta = new Map((data?.jenis ?? []).map((satu) => [satu.kode, satu.label]));
    return (kode: string) => LABEL_JENIS[kode] ?? peta.get(kode) ?? kode;
  }, [data]);

  function bersihkanPilihan() {
    setPilihan(new Set());
    setPilihSemua(false);
  }

  function ubahBatas(nilai: UkuranHalaman) {
    setBatas(nilai);
    setHalaman(0);
  }

  function ubahKabupaten(nilai: string[]) {
    setKdkabs(nilai);
    setHalaman(0);
    bersihkanPilihan();
  }

  function ubahJenis(nilai: string[]) {
    setJenises(nilai);
    setHalaman(0);
    bersihkanPilihan();
  }

  function ubahStatus(nilai: string) {
    setStatusFilter(nilai);
    setHalaman(0);
    bersihkanPilihan();
  }

  function ubahRiwayat(nilai: number | null) {
    setRunTerpilih(nilai);
    setHalaman(0);
    bersihkanPilihan();
  }

  function toggleBaris(baris: AnomaliBaris) {
    const id = baris.id;
    if (id == null) {
      return;
    }
    setPilihSemua(false);
    setPilihan((lama) => {
      const baru = new Set(lama);
      if (baru.has(id)) {
        baru.delete(id);
      } else {
        baru.add(id);
      }
      return baru;
    });
  }

  function toggleHalaman() {
    if (semuaHalamanDipilih) {
      bersihkanPilihan();
      return;
    }
    setPilihSemua(false);
    const id = barisHalaman
      .map((baris) => baris.id)
      .filter((satu): satu is number => satu != null);
    setPilihan(new Set(id));
  }

  /** Muatan aksi massal: baris tertentu, atau seluruh hasil filter (server). */
  function muatanPilihan(): PermintaanKonfirmasi | null {
    if (pilihSemua) {
      return {
        kdprov,
        kdkab: kdkabs,
        jenis: jenises,
        q: kataKunci || undefined,
        run_b_id: kdkabSatu && runTerpilih != null ? runTerpilih : undefined,
        status_filter: statusFilter || undefined,
        semua: true,
      };
    }
    if (pilihan.size === 0) {
      return null;
    }
    return { anomali_ids: [...pilihan] };
  }

  async function kirimKonfirmasi(
    isi: PermintaanKonfirmasi,
  ): Promise<number | null> {
    setMengirim(true);
    setGalat(null);
    setBerhasil(null);
    try {
      const hasil = await ambilJson<HasilKonfirmasi>("/anomali/konfirmasi", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(isi),
      });
      setBerhasil(`${formatAngka(hasil.jumlah)} titik dikonfirmasi.`);
      setDrawer(null);
      setBukaMassal(false);
      bersihkanPilihan();
      await muat();
      return hasil.jumlah;
    } catch (kesalahan) {
      setGalat(pesanKesalahan(kesalahan));
      return null;
    } finally {
      setMengirim(false);
    }
  }

  async function kirimBatal(isi: PermintaanKonfirmasi) {
    setMengirim(true);
    setGalat(null);
    setBerhasil(null);
    try {
      const hasil = await ambilJson<HasilKonfirmasi>(
        "/anomali/konfirmasi/batal",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(isi),
        },
      );
      setBerhasil(
        `${formatAngka(hasil.jumlah)} konfirmasi dibatalkan (kembali belum dikonfirmasi).`,
      );
      setDrawer(null);
      bersihkanPilihan();
      await muat();
    } catch (kesalahan) {
      setGalat(pesanKesalahan(kesalahan));
    } finally {
      setMengirim(false);
    }
  }

  function bukaDrawer(baris: AnomaliBaris, statusAwal?: KodeStatus) {
    setDrawer(baris);
    const statusLama = baris.konfirmasi?.status;
    const awal: KodeStatus =
      statusLama === "sesuai_kenyataan" || statusLama === "akan_diperbaiki"
        ? statusLama
        : "akan_diperbaiki";
    setFormStatus(statusAwal ?? awal);
    setFormCatatan(baris.konfirmasi?.catatan ?? "");
  }

  async function simpanDrawer() {
    const id = drawer?.id;
    if (id == null) {
      return;
    }
    if (formStatus === "sesuai_kenyataan" && formCatatan.trim() === "") {
      return;
    }
    await kirimKonfirmasi({
      status: formStatus,
      catatan: formCatatan.trim() || null,
      anomali_ids: [id],
    });
  }

  async function konfirmasiCepat(baris: AnomaliBaris, status: KodeStatus) {
    const id = baris.id;
    if (id == null) {
      return;
    }
    await kirimKonfirmasi({ status, anomali_ids: [id] });
  }

  async function massalAkan() {
    const dasar = muatanPilihan();
    if (!dasar) {
      return;
    }
    await kirimKonfirmasi({ ...dasar, status: "akan_diperbaiki" });
  }

  async function simpanMassal() {
    const dasar = muatanPilihan();
    if (!dasar || massalCatatan.trim() === "") {
      return;
    }
    const hasil = await kirimKonfirmasi({
      ...dasar,
      status: "sesuai_kenyataan",
      catatan: massalCatatan.trim(),
    });
    if (hasil != null) {
      setMassalCatatan("");
    }
  }

  async function batalMassal() {
    const dasar = muatanPilihan();
    if (!dasar) {
      return;
    }
    await kirimBatal(dasar);
  }

  async function kirimKlarifikasi() {
    const id = drawer?.id;
    if (id == null || klarifikasiCatatan.trim() === "") {
      return;
    }
    setMengirim(true);
    setGalat(null);
    setBerhasil(null);
    try {
      const hasil = await ambilJson<HasilKonfirmasi>(
        "/anomali/konfirmasi/klarifikasi",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            anomali_ids: [id],
            catatan: klarifikasiCatatan.trim(),
          }),
        },
      );
      setBerhasil(
        `Permintaan klarifikasi dikirim untuk ${formatAngka(hasil.jumlah)} titik.`,
      );
      setBukaKlarifikasi(false);
      setDrawer(null);
      setKlarifikasiCatatan("");
      await muat();
    } catch (kesalahan) {
      setGalat(pesanKesalahan(kesalahan));
    } finally {
      setMengirim(false);
    }
  }

  async function unduhExcel() {
    if (runs.length === 0) {
      return;
    }
    setMengunduh(true);
    setGalat(null);
    try {
      const isi = new URLSearchParams({ kdprov });
      for (const kode of kdkabs) {
        isi.append("kdkab", kode);
      }
      for (const kode of jenises) {
        isi.append("jenis", kode);
      }
      if (statusFilter) {
        isi.set("status", statusFilter);
      }
      if (kataKunci) {
        isi.set("q", kataKunci);
      }
      if (kdkabSatu && runTerpilih != null) {
        isi.set("run_b_id", String(runTerpilih));
      }
      const label = jenises.length === 1 ? jenises[0] : "semua";
      await unduhBerkas(
        `/anomali.xlsx?${isi}`,
        `pencermatan_${label}_${kdkabs.join("-")}.xlsx`,
      );
    } catch (kesalahan) {
      setGalat(pesanKesalahan(kesalahan));
    } finally {
      setMengunduh(false);
    }
  }

  const simpanMati =
    mengirim ||
    (formStatus === "sesuai_kenyataan" && formCatatan.trim() === "");

  return (
    <div className="space-y-field">
      <Panel
        judul="Pencermatan Titik"
        deskripsi="Titik yang menurut sistem masih bermasalah pada Proses B. Pilih run terakhir atau dari riwayat; rekap memakai klaim kabupaten, halaman ini memperlihatkan selisihnya."
      >
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted">
            Filter berlaku untuk tabel dan unduhan Excel.
          </p>
          <button
            type="button"
            onClick={() => setBukaPenjelasan(true)}
            aria-haspopup="dialog"
            className="group inline-flex animate-pulse items-center gap-2 rounded-full bg-red-600 px-4 py-2 text-xs font-bold text-white shadow-[0_0_18px_4px_rgba(220,38,38,0.55)] ring-2 ring-red-300 transition hover:animate-none hover:bg-red-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 motion-reduce:animate-none"
          >
            <span
              aria-hidden="true"
              className="grid h-5 w-5 place-items-center rounded-full bg-white/25 text-[11px] font-bold ring-1 ring-white/50"
            >
              !
            </span>
            Penjelasan poin pencermatan
          </button>
        </div>

        <div className="mt-3 grid gap-field sm:grid-cols-2 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1.2fr)_minmax(0,1.3fr)_auto]">
          {kdkabAwal ? (
            <div>
              <span className="block text-sm font-medium text-ink">
                Kabupaten/kota
              </span>
              <span className="mt-label block min-h-9 text-sm font-medium text-muted">
                {opsi.find((satu) => satu.kode === kdkabAwal)?.nama ??
                  kdkabAwal}
              </span>
            </div>
          ) : (
            <MultiPilih
              label="Kabupaten/kota"
              labelSemua="Semua kabupaten/kota"
              tempatCari="Cari kode atau nama kabupaten..."
              opsi={opsi.map((satu) => ({
                nilai: satu.kode,
                label: `${satu.kode} · ${satu.nama}`,
              }))}
              terpilih={kdkabs}
              onTerapkan={ubahKabupaten}
            />
          )}

          <MultiPilih
            label="Jenis pencermatan"
            labelSemua={`Semua (${formatAngka(totalSemua)})`}
            tempatCari="Cari jenis pencermatan..."
            opsi={(data?.jenis ?? []).map((satu) => ({
              nilai: satu.kode,
              label: `${LABEL_JENIS[satu.kode] ?? satu.label} (${formatAngka(satu.jumlah)})`,
            }))}
            terpilih={jenises}
            onTerapkan={ubahJenis}
          />

          <div>
            <label
              htmlFor="status-konfirmasi"
              className="block text-sm font-medium text-ink"
            >
              Status
            </label>
            <select
              id="status-konfirmasi"
              value={statusFilter}
              onChange={(kejadian) => ubahStatus(kejadian.target.value)}
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            >
              {statusPilihan.map((satu) => (
                <option key={satu.kode} value={satu.kode}>
                  {satu.label}
                </option>
              ))}
              <option value="">Semua status</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="riwayat-run"
              className="block text-sm font-medium text-ink"
            >
              Riwayat run
            </label>
            <select
              id="riwayat-run"
              value={
                kdkabSatu ? String(runTerpilih ?? riwayat[0]?.run_id ?? "") : ""
              }
              onChange={(kejadian) =>
                ubahRiwayat(
                  kejadian.target.value ? Number(kejadian.target.value) : null,
                )
              }
              disabled={!kdkabSatu || riwayat.length === 0}
              title={
                !kdkabSatu
                  ? "Pilih tepat satu kabupaten/kota untuk membuka riwayat run"
                  : undefined
              }
              className="mt-label block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink disabled:cursor-not-allowed disabled:opacity-60"
            >
              {kdkabSatu && riwayat.length > 0 ? (
                riwayat.map((satu) => (
                  <option key={satu.run_id} value={satu.run_id}>
                    {`#${satu.run_id} · ${formatTanggal(satu.tanggal_data)} · ${
                      satu.jumlah_anomali == null
                        ? "–"
                        : formatAngka(satu.jumlah_anomali)
                    } anomali${satu.pengunggah ? ` · ${satu.pengunggah}` : ""}`}
                  </option>
                ))
              ) : (
                <option value="">
                  {kdkabSatu
                    ? "Run terakhir (otomatis)"
                    : "Run terakhir (semua kabupaten)"}
                </option>
              )}
            </select>
          </div>

          <form
            className="text-sm font-medium text-ink"
            onSubmit={(kejadian) => {
              kejadian.preventDefault();
              setHalaman(0);
              setKataKunci(cari.trim());
              bersihkanPilihan();
            }}
          >
            <span className="block">Cari</span>
            <div className="mt-label flex gap-1.5">
              <input
                type="search"
                value={cari}
                onChange={(kejadian) => setCari(kejadian.target.value)}
                placeholder="assignment_id / bangunan / kode"
                className="block min-h-9 w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
              />
              <TombolAksi
                type="submit"
                varian="sekunder"
                className="min-h-9 px-2.5 text-xs"
              >
                Cari
              </TombolAksi>
            </div>
          </form>

          <div>
            <span
              aria-hidden="true"
              className="invisible block text-sm font-medium text-ink"
            >
              Unduh
            </span>
            <TombolAksi
              varian="sekunder"
              className="mt-label min-h-9 px-2.5 text-xs"
              onClick={() => void unduhExcel()}
              disabled={runs.length === 0 || mengunduh || total === 0}
              title={
                runs.length === 0
                  ? "Belum ada Proses B yang sukses"
                  : "Unduh pencermatan sesuai filter sebagai Excel"
              }
            >
              {mengunduh ? "Menyiapkan..." : "Unduh Excel"}
            </TombolAksi>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 text-xs text-muted">
          {runs.length === 1 ? (
            <>
              <span>
                Proses B{" "}
                <strong className="text-ink">#{runs[0].run_id}</strong> ·{" "}
                {formatTanggal(runs[0].tanggal_data)}
                {runs[0].pengunggah ? ` · ${runs[0].pengunggah}` : ""}
              </span>
              <span>
                Selesai{" "}
                <strong className="text-ink">
                  {formatAngka(runs[0].selesai)}
                </strong>{" "}
                dari {formatAngka(runs[0].target)}
              </span>
            </>
          ) : null}
          {runs.length > 1 ? (
            <>
              <span>
                <strong className="text-ink">{formatAngka(runs.length)}</strong>{" "}
                kabupaten/kota dengan Proses B sukses
              </span>
              <span>
                Selesai{" "}
                <strong className="text-ink">{formatAngka(selesai)}</strong> dari{" "}
                {formatAngka(target)}
              </span>
            </>
          ) : null}
          <span className="font-medium text-danger">
            <strong className="font-bold">{formatAngka(total)}</strong> titik
            bermasalah
            {jenisTerpilih ? ` · ${labelJenis(jenisTerpilih.kode)}` : ""}
          </span>
        </div>

        {/* Progres konfirmasi: tetap utuh walau tabel difilter ke satu status. */}
        <div className="mt-2 rounded-lg border border-line bg-paper/60 px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="font-medium text-ink">
              Dikonfirmasi{" "}
              <strong>{formatAngka(ringkasan.terkonfirmasi)}</strong> dari{" "}
              {formatAngka(ringkasan.total)}
            </span>
            <span className="tabular-nums text-muted">{persenKonfirmasi}%</span>
          </div>
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={persenKonfirmasi}
            aria-label="Progres konfirmasi pencermatan"
            className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface ring-1 ring-inset ring-line"
          >
            <div
              className="h-full rounded-full bg-success transition-[width]"
              style={{ width: `${persenKonfirmasi}%` }}
            />
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
            {(ringkasan.per_status.length > 0
              ? ringkasan.per_status
              : STATUS_BAWAAN
            ).map((satu) => (
              <span key={satu.kode} className="inline-flex items-center gap-1">
                <span
                  aria-hidden="true"
                  className={`h-2 w-2 rounded-full ${
                    satu.kode === "sesuai_kenyataan"
                      ? "bg-success"
                      : satu.kode === "akan_diperbaiki"
                        ? "bg-accent"
                        : "bg-muted/50"
                  }`}
                />
                {satu.label}{" "}
                <span className="tabular-nums text-ink">
                  {formatAngka(satu.jumlah)}
                </span>
              </span>
            ))}
          </div>
        </div>

        {perluHitungUlang ? (
          <div
            role="status"
            className="mt-3 rounded-lg border border-accent/30 bg-accent-soft/50 px-3 py-2 text-sm text-ink"
          >
            Ada job B yang diproses sebelum fitur pencermatan ada. Antrekan ulang
            berkas B terakhir kabupaten tersebut untuk menghitung pencermatan
            (tidak perlu unggah ulang).
          </div>
        ) : null}

        {apiLama ? (
          <div
            role="alert"
            className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-sm text-ink"
          >
            <strong className="font-semibold">
              API backend masih versi lama.
            </strong>{" "}
            Respons <code className="font-mono text-xs">/anomali</code> belum
            memuat id baris, jadi tombol konfirmasi dinonaktifkan. Deploy
            backend terbaru beserta migrasi <code className="font-mono text-xs">0017</code>,
            lalu muat ulang halaman ini.
          </div>
        ) : null}

        {galat ? (
          <div
            role="alert"
            className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/50 px-3 py-2 text-sm text-ink"
          >
            {galat}
          </div>
        ) : null}

        {berhasil ? (
          <div
            role="status"
            className="mt-3 rounded-lg border border-success/30 bg-success-soft px-3 py-2 text-sm text-success"
          >
            {berhasil}
          </div>
        ) : null}

        {memuat && data == null ? (
          <div className="mt-3 space-y-2" aria-label="Memuat pencermatan">
            {[0, 1, 2, 3].map((baris) => (
              <div
                key={baris}
                className="h-11 animate-pulse rounded-lg bg-paper"
              />
            ))}
          </div>
        ) : null}

        {!memuat && data != null && runs.length === 0 ? (
          <EmptyState judul="Belum ada Proses B yang sukses">
            Pencermatan dihitung saat job Proses B selesai. Unggah titik hasil
            perbaikan untuk kabupaten/kota ini lebih dulu.
          </EmptyState>
        ) : null}

        {runs.length > 0 && data && data.baris.length === 0 ? (
          <EmptyState
            judul={
              statusFilter === "belum" && ringkasan.total > 0
                ? "Semua titik sudah dikonfirmasi"
                : "Tidak ada titik yang perlu dicermati"
            }
          >
            {statusFilter === "belum" && ringkasan.total > 0
              ? "Tidak ada temuan yang belum dijelaskan pada filter ini. Ganti filter Status untuk melihat yang sudah dikonfirmasi."
              : jenises.length > 0
                ? "Jenis yang dipilih kosong untuk run terakhir."
                : "Semua titik target cocok dan tidak ada kerusakan baru menurut sistem."}
          </EmptyState>
        ) : null}

        {adaPilihan ? (
          <div className="sticky top-2 z-30 mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-accent/40 bg-accent-soft px-3 py-2 text-sm text-ink shadow-sm">
            <span>
              <strong>{formatAngka(jumlahDipilih)}</strong> titik dipilih
            </span>
            {!pilihSemua ? (
              <button
                type="button"
                onClick={() => {
                  setPilihSemua(true);
                  setPilihan(new Set());
                }}
                className="rounded-md border border-accent/40 bg-surface px-2 py-1 text-xs font-semibold text-accent transition-colors hover:border-accent"
              >
                Pilih semua {formatAngka(total)} hasil filter
              </button>
            ) : (
              <span className="text-xs text-muted">
                (seluruh hasil filter, bukan hanya halaman ini)
              </span>
            )}
            <div className="ml-auto flex flex-wrap items-center gap-1.5">
              <TombolAksi
                varian="sekunder"
                className="min-h-8 px-2.5 text-xs"
                onClick={() => void massalAkan()}
                disabled={mengirim}
              >
                Akan Diperbaiki
              </TombolAksi>
              <TombolAksi
                varian="sekunder"
                className="min-h-8 px-2.5 text-xs"
                onClick={() => setBukaMassal(true)}
                disabled={mengirim}
              >
                Sesuai Kenyataan
              </TombolAksi>
              <TombolAksi
                varian="sekunder"
                className="min-h-8 px-2.5 text-xs"
                onClick={() => void batalMassal()}
                disabled={mengirim}
              >
                Batalkan konfirmasi
              </TombolAksi>
              <button
                type="button"
                onClick={bersihkanPilihan}
                className="rounded-md px-2 py-1 text-xs font-semibold text-muted hover:text-ink"
              >
                Bersihkan
              </button>
            </div>
          </div>
        ) : null}

        {data && data.baris.length > 0 ? (
          <>
            <div className="mt-3 max-h-[70vh] overflow-auto rounded-lg border border-line">
              <table className="w-full min-w-[76rem] border-collapse text-[13px]">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted">
                    <th className={`${KELAS_HEAD_KIRI} w-10 px-2`}>
                      <input
                        ref={kepalaPilih}
                        type="checkbox"
                        checked={semuaHalamanDipilih}
                        onChange={toggleHalaman}
                        aria-label="Pilih semua baris di halaman ini"
                        className="h-4 w-4 accent-[var(--brand)]"
                      />
                    </th>
                    <th className={`${KELAS_HEAD_KIRI} left-10`}>Status</th>
                    {banyakKabupaten ? (
                      <th className={KELAS_HEAD}>Kabupaten/kota</th>
                    ) : null}
                    <th className={KELAS_HEAD}>Jenis</th>
                    <th className={KELAS_HEAD}>Assignment ID</th>
                    <th className={KELAS_HEAD}>ID baru</th>
                    <th className={KELAS_HEAD}>Bangunan</th>
                    <th className={KELAS_HEAD}>level_6_fullcode Master GS</th>
                    <th className={KELAS_HEAD}>
                      level_6_fullcode Geotag Kabkot
                    </th>
                    <th className={KELAS_HEAD}>Wilayah</th>
                    <th className={KELAS_HEAD}>Flag unggah / model</th>
                    <th className={KELAS_HEAD}>Keterangan</th>
                  </tr>
                </thead>
                <tbody>
                  {data.baris.map((baris, indeks) => {
                    const dipilih = baris.id != null && pilihan.has(baris.id);
                    return (
                      <tr
                        key={`${baris.id ?? "x"}-${baris.kdkab}-${baris.assignment_id}-${baris.assignment_id_baru}-${indeks}`}
                        className="border-b border-line/70 last:border-0"
                      >
                        <td className={KELAS_SEL_KIRI}>
                          <input
                            type="checkbox"
                            checked={dipilih || pilihSemua}
                            onChange={() => toggleBaris(baris)}
                            disabled={baris.id == null}
                            aria-label="Pilih titik ini"
                            className="h-4 w-4 accent-[var(--brand)]"
                          />
                        </td>
                        <td className={KELAS_STATUS_KIRI}>
                          <span
                            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${kelasBadge(
                              baris.konfirmasi?.status,
                            )}`}
                          >
                            {baris.konfirmasi?.label ?? "Belum dikonfirmasi"}
                          </span>
                          {baris.konfirmasi?.perlu_klarifikasi ? (
                            <p
                              className="mt-1 truncate text-[10px] font-semibold text-danger"
                              title={baris.konfirmasi.klarifikasi_catatan ?? undefined}
                            >
                              Diminta klarifikasi
                            </p>
                          ) : null}
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            <button
                              type="button"
                              onClick={() =>
                                void konfirmasiCepat(baris, "akan_diperbaiki")
                              }
                              disabled={mengirim || baris.id == null}
                              className="hidden min-h-6 rounded-md border border-line-strong bg-surface px-1.5 text-[10px] font-semibold text-ink transition-colors hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60 lg:inline-flex"
                              title="Tandai Akan Diperbaiki"
                            >
                              Akan
                            </button>
                            <button
                              type="button"
                              onClick={() => bukaDrawer(baris, "sesuai_kenyataan")}
                              disabled={baris.id == null}
                              className="hidden min-h-6 rounded-md border border-line-strong bg-surface px-1.5 text-[10px] font-semibold text-ink transition-colors hover:border-success hover:text-success disabled:cursor-not-allowed disabled:opacity-60 lg:inline-flex"
                              title="Tandai Sesuai Kondisi Kenyataan (wajib keterangan)"
                            >
                              Sesuai
                            </button>
                            <button
                              type="button"
                              onClick={() => bukaDrawer(baris)}
                              disabled={baris.id == null}
                              className="min-h-6 rounded-md border border-line-strong bg-surface px-1.5 text-[10px] font-semibold text-ink transition-colors hover:border-brand hover:text-brand-strong disabled:cursor-not-allowed disabled:opacity-60 lg:hidden"
                            >
                              Konfirmasi
                            </button>
                            {baris.konfirmasi ? (
                              <button
                                type="button"
                                onClick={() => bukaDrawer(baris)}
                                disabled={baris.id == null}
                                className="hidden min-h-6 rounded-md border border-line-strong bg-surface px-1.5 text-[10px] font-semibold text-ink transition-colors hover:border-brand hover:text-brand-strong disabled:cursor-not-allowed disabled:opacity-60 lg:inline-flex"
                                title="Ubah atau batalkan konfirmasi"
                              >
                                Ubah
                              </button>
                            ) : null}
                          </div>
                          {baris.konfirmasi?.catatan ? (
                            <p
                              className="mt-1 max-w-[14rem] truncate text-[10px] text-muted"
                              title={baris.konfirmasi.catatan}
                            >
                              {baris.konfirmasi.catatan}
                            </p>
                          ) : null}
                        </td>
                        {banyakKabupaten ? (
                          <td className="whitespace-nowrap px-3 py-2 text-muted">
                            {labelKabupaten(baris.kdkab)}
                          </td>
                        ) : null}
                        <td className="whitespace-nowrap px-3 py-2 text-muted">
                          {labelJenis(baris.jenis)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-ink">
                          <span className="inline-flex items-center">
                            {teks(baris.assignment_id)}
                            <TombolSalin
                              nilai={baris.assignment_id}
                              label="Assignment ID"
                            />
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                          <span className="inline-flex items-center">
                            {teks(baris.assignment_id_baru)}
                            <TombolSalin
                              nilai={baris.assignment_id_baru}
                              label="ID baru"
                            />
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                          <span className="inline-flex items-center">
                            {teks(baris.unique_bang)}
                            <TombolSalin
                              nilai={baris.unique_bang}
                              label="ID bangunan"
                            />
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                          <span className="inline-flex items-center">
                            {teks(baris.level_6_full_code)}
                            <TombolSalin
                              nilai={baris.level_6_full_code}
                              label="kode SLS Master GS"
                            />
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                          <span className="inline-flex items-center">
                            {teks(baris.level_6_full_code_b)}
                            <TombolSalin
                              nilai={baris.level_6_full_code_b}
                              label="kode SLS Geotag Kabkot"
                            />
                          </span>
                        </td>
                        <td className="px-3 py-2 text-muted">
                          {teks(baris.wilayah)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted">
                          {baris.flag_unggah ?? "–"} / {baris.flag_model ?? "–"}
                        </td>
                        <td className="px-3 py-2 text-muted">
                          {teks(baris.keterangan)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <span>
                  {formatAngka(mulai)}–{formatAngka(akhir)} dari{" "}
                  {formatAngka(total)}
                </span>
                <label className="flex items-center gap-1.5">
                  <span>Baris per halaman</span>
                  <select
                    value={batas === "semua" ? "semua" : String(batas)}
                    onChange={(kejadian) =>
                      ubahBatas(
                        kejadian.target.value === "semua"
                          ? "semua"
                          : Number(kejadian.target.value),
                      )
                    }
                    disabled={memuat}
                    className="min-h-8 rounded-lg border border-line-strong bg-surface px-2 py-1 text-xs text-ink disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {PILIHAN_BATAS.map((nilai) => (
                      <option key={nilai} value={nilai}>
                        {nilai}
                      </option>
                    ))}
                    <option value="semua">Semua</option>
                  </select>
                </label>
              </div>
              {batas === "semua" ? null : (
                <div className="flex gap-1.5">
                  <TombolAksi
                    varian="sekunder"
                    className="min-h-8 px-2.5 text-xs"
                    onClick={() => setHalaman((lama) => Math.max(0, lama - 1))}
                    disabled={halaman === 0 || memuat}
                  >
                    Sebelumnya
                  </TombolAksi>
                  <TombolAksi
                    varian="sekunder"
                    className="min-h-8 px-2.5 text-xs"
                    onClick={() => setHalaman((lama) => lama + 1)}
                    disabled={akhir >= total || memuat}
                  >
                    Berikutnya
                  </TombolAksi>
                </div>
              )}
            </div>
          </>
        ) : null}
      </Panel>

      <PenjelasanJenis
        terbuka={bukaPenjelasan}
        onTutup={() => setBukaPenjelasan(false)}
      />

      {/* Drawer konfirmasi satu titik (dari kanan). */}
      {drawer ? (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button
            type="button"
            aria-label="Tutup panel konfirmasi"
            onClick={() => setDrawer(null)}
            className="absolute inset-0 bg-ink/40"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="judul-konfirmasi"
            className="relative flex h-full w-full flex-col border-l border-line bg-surface shadow-2xl sm:w-[min(28rem,100vw)]"
          >
            <div className="flex items-start justify-between gap-3 border-b border-line p-kartu">
              <h2
                id="judul-konfirmasi"
                className="text-base font-semibold tracking-tight text-ink"
              >
                Konfirmasi titik
              </h2>
              <button
                type="button"
                onClick={() => setDrawer(null)}
                aria-label="Tutup"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-paper hover:text-ink"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-kartu">
              <div className="rounded-lg border border-line bg-paper/60 px-3 py-2 text-sm">
                <p className="font-semibold text-ink">
                  {labelJenis(drawer.jenis)}
                </p>
                <dl className="mt-1.5 space-y-1 text-xs text-muted">
                  <div className="flex justify-between gap-3">
                    <dt>Kabupaten/kota</dt>
                    <dd className="text-right text-ink">
                      {labelKabupaten(drawer.kdkab)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>Assignment ID</dt>
                    <dd className="inline-flex items-center text-right font-mono text-ink">
                      {teks(drawer.assignment_id)}
                      <TombolSalin
                        nilai={drawer.assignment_id}
                        label="Assignment ID"
                      />
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>Wilayah</dt>
                    <dd className="text-right text-ink">{teks(drawer.wilayah)}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>Keterangan sistem</dt>
                    <dd className="text-right text-ink">
                      {teks(drawer.keterangan)}
                    </dd>
                  </div>
                </dl>
                {drawer.konfirmasi ? (
                  <p className="mt-2 border-t border-line pt-2 text-[11px] text-muted">
                    Dikonfirmasi oleh{" "}
                    <strong className="text-ink">
                      {drawer.konfirmasi.oleh ?? "–"}
                    </strong>
                    {drawer.konfirmasi.pada
                      ? ` pada ${formatWaktu(drawer.konfirmasi.pada)}`
                      : ""}
                    .
                  </p>
                ) : null}
              </div>

              {drawer.konfirmasi?.perlu_klarifikasi ? (
                <div className="rounded-lg border border-danger/30 bg-danger-soft/60 px-3 py-2 text-xs text-ink">
                  <p className="font-semibold text-danger">
                    Diminta klarifikasi admin provinsi
                  </p>
                  <p className="mt-1 whitespace-pre-line">
                    {teks(drawer.konfirmasi.klarifikasi_catatan)}
                  </p>
                  <p className="mt-1 text-[11px] text-muted">
                    {drawer.konfirmasi.klarifikasi_oleh ?? "–"}
                    {drawer.konfirmasi.klarifikasi_pada
                      ? ` · ${formatWaktu(drawer.konfirmasi.klarifikasi_pada)}`
                      : ""}
                  </p>
                </div>
              ) : null}

              <fieldset>
                <legend className="text-sm font-medium text-ink">Status</legend>
                <div className="mt-1.5 grid gap-1.5">
                  {(
                    [
                      {
                        kode: "akan_diperbaiki" as const,
                        label: "Akan Diperbaiki",
                        ket: "Temuan diakui dan akan diperbaiki. Keterangan opsional.",
                      },
                      {
                        kode: "sesuai_kenyataan" as const,
                        label: "Sesuai Kondisi Kenyataan",
                        ket: "Temuan sesuai lapangan. Keterangan wajib diisi.",
                      },
                    ]
                  ).map((pilihanStatus) => (
                    <label
                      key={pilihanStatus.kode}
                      className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                        formStatus === pilihanStatus.kode
                          ? "border-brand bg-accent-soft/60"
                          : "border-line bg-surface hover:border-line-strong"
                      }`}
                    >
                      <input
                        type="radio"
                        name="status-konfirmasi-titik"
                        value={pilihanStatus.kode}
                        checked={formStatus === pilihanStatus.kode}
                        onChange={() => setFormStatus(pilihanStatus.kode)}
                        className="mt-0.5 h-4 w-4 accent-[var(--brand)]"
                      />
                      <span>
                        <span className="block font-semibold text-ink">
                          {pilihanStatus.label}
                        </span>
                        <span className="block text-xs text-muted">
                          {pilihanStatus.ket}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div>
                <label
                  htmlFor="catatan-konfirmasi"
                  className="block text-sm font-medium text-ink"
                >
                  Keterangan
                  {formStatus === "sesuai_kenyataan" ? (
                    <span className="ml-1 text-xs font-normal text-danger">
                      wajib
                    </span>
                  ) : (
                    <span className="ml-1 text-xs font-normal text-muted">
                      opsional
                    </span>
                  )}
                </label>
                <textarea
                  id="catatan-konfirmasi"
                  value={formCatatan}
                  onChange={(kejadian) => setFormCatatan(kejadian.target.value)}
                  rows={4}
                  maxLength={2000}
                  placeholder={
                    formStatus === "sesuai_kenyataan"
                      ? "Jelaskan mengapa temuan ini sesuai kondisi lapangan…"
                      : "Rencana/target perbaikan (opsional)…"
                  }
                  className="mt-label block w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
                />
                <p className="mt-1 text-right text-[11px] text-muted">
                  {formCatatan.length}/2000
                </p>
              </div>

              <p className="rounded-lg border border-accent/30 bg-accent-soft/50 px-3 py-2 text-[11px] leading-5 text-ink">
                Konfirmasi berlaku juga untuk run berikutnya selama jenis dan
                titiknya sama, jadi tidak perlu diulang tiap unggahan.
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line p-kartu">
              {drawer.konfirmasi ? (
                <button
                  type="button"
                  onClick={() =>
                    void kirimBatal({ anomali_ids: drawer.id ? [drawer.id] : [] })
                  }
                  disabled={mengirim || drawer.id == null}
                  className="mr-auto rounded-lg px-2 py-1 text-xs font-semibold text-danger hover:underline disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Batalkan konfirmasi
                </button>
              ) : null}
              {adminProvinsi && drawer.konfirmasi ? (
                <button
                  type="button"
                  onClick={() => {
                    setKlarifikasiCatatan("");
                    setBukaKlarifikasi(true);
                  }}
                  disabled={mengirim}
                  className="rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:underline disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Minta klarifikasi
                </button>
              ) : null}
              <TombolAksi
                varian="sekunder"
                onClick={() => setDrawer(null)}
                disabled={mengirim}
              >
                Batal
              </TombolAksi>
              <TombolAksi onClick={() => void simpanDrawer()} disabled={simpanMati}>
                {mengirim ? "Menyimpan…" : "Simpan"}
              </TombolAksi>
            </div>
          </div>
        </div>
      ) : null}

      {/* Aksi massal "Sesuai Kondisi Kenyataan": alasan diminta sekali. */}
      <Modal
        terbuka={bukaMassal}
        judul={`Sesuai Kondisi Kenyataan · ${formatAngka(jumlahDipilih)} titik`}
        onTutup={() => setBukaMassal(false)}
      >
        <p className="text-sm leading-6 text-muted">
          Keterangan di bawah dipakai untuk semua titik terpilih.
          Keterangan wajib diisi.
        </p>
        <div className="mt-3 space-y-3">
          <div>
            <label
              htmlFor="catatan-massal"
              className="block text-sm font-medium text-ink"
            >
              Keterangan <span className="text-xs font-normal text-danger">wajib</span>
            </label>
            <textarea
              id="catatan-massal"
              value={massalCatatan}
              onChange={(kejadian) => setMassalCatatan(kejadian.target.value)}
              rows={4}
              maxLength={2000}
              placeholder="Jelaskan kondisi lapangan untuk titik-titik ini…"
              className="mt-label block w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
            />
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <TombolAksi
            varian="sekunder"
            onClick={() => setBukaMassal(false)}
            disabled={mengirim}
          >
            Batal
          </TombolAksi>
          <TombolAksi
            onClick={() => void simpanMassal()}
            disabled={mengirim || massalCatatan.trim() === ""}
          >
            {mengirim ? "Menyimpan…" : "Simpan untuk semua"}
          </TombolAksi>
        </div>
      </Modal>

      {/* Admin provinsi: minta klarifikasi atas konfirmasi kabupaten/kota. */}
      <Modal
        terbuka={bukaKlarifikasi}
        judul="Minta klarifikasi"
        onTutup={() => setBukaKlarifikasi(false)}
      >
        <p className="text-sm leading-6 text-muted">
          Catatan ini terlihat oleh kabupaten/kota. Status konfirmasi tidak
          berubah sampai mereka mengonfirmasi ulang.
        </p>
        <div className="mt-3">
          <label
            htmlFor="catatan-klarifikasi"
            className="block text-sm font-medium text-ink"
          >
            Catatan klarifikasi{" "}
            <span className="text-xs font-normal text-danger">wajib</span>
          </label>
          <textarea
            id="catatan-klarifikasi"
            value={klarifikasiCatatan}
            onChange={(kejadian) =>
              setKlarifikasiCatatan(kejadian.target.value)
            }
            rows={4}
            maxLength={2000}
            placeholder="Contoh: mohon lampirkan bukti foto/batas SLS yang dipakai..."
            className="mt-label block w-full rounded-lg border border-line-strong bg-surface px-input py-input text-sm text-ink"
          />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <TombolAksi
            varian="sekunder"
            onClick={() => setBukaKlarifikasi(false)}
            disabled={mengirim}
          >
            Batal
          </TombolAksi>
          <TombolAksi
            onClick={() => void kirimKlarifikasi()}
            disabled={mengirim || klarifikasiCatatan.trim() === ""}
          >
            {mengirim ? "Mengirim..." : "Kirim permintaan"}
          </TombolAksi>
        </div>
      </Modal>
    </div>
  );
}