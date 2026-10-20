"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { BadgeStatus } from "@/components/proses/badge-status";
import {
  EmptyState,
  Panel,
  TombolAksi,
} from "@/components/dashboard/ui";
import {
  adalahBatal,
  ambilJson,
  pesanKesalahan,
} from "@/lib/api/klien";
import type { JobSistem, StatusSistem } from "@/lib/api/types";
import { formatAngka, formatWaktu } from "@/lib/format";
import { labelTipe } from "@/lib/istilah";

function nilaiMb(nilai: number | null | undefined): string {
  return nilai == null ? "-" : `${formatAngka(Math.round(nilai))} MB`;
}

function nilaiPersen(nilai: number | null | undefined): string {
  return nilai == null ? "-" : `${formatAngka(Math.round(nilai))}%`;
}

function nilaiDurasi(detik: number | null | undefined): string {
  if (detik == null) {
    return "-";
  }
  const jam = Math.floor(detik / 3600);
  const menit = Math.floor((detik % 3600) / 60);
  const sisa = detik % 60;
  if (jam > 0) {
    return `${jam}j ${menit}m ${sisa}d`;
  }
  if (menit > 0) {
    return `${menit}m ${sisa}d`;
  }
  return `${sisa} detik`;
}

function BarPemakaian({
  nilai,
  bahaya = false,
}: {
  nilai: number | null | undefined;
  bahaya?: boolean;
}) {
  const lebar = Math.max(0, Math.min(100, nilai ?? 0));
  return (
    <div
      className="mt-2 h-2 overflow-hidden rounded-full bg-brand-soft"
      aria-hidden="true"
    >
      <div
        className={`h-full rounded-full ${bahaya ? "bg-danger" : "bg-brand"}`}
        style={{ width: `${lebar}%` }}
      />
    </div>
  );
}

function KartuMetrik({
  label,
  nilai,
  keterangan,
  bar,
  bahaya = false,
}: {
  label: string;
  nilai: string;
  keterangan: string;
  bar?: number | null;
  bahaya?: boolean;
}) {
  return (
    <div className="rounded-lg border border-line bg-paper/60 p-4">
      <p className="text-xs font-semibold text-muted">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
        {nilai}
      </p>
      <p className="mt-1 text-xs leading-5 text-muted">{keterangan}</p>
      {bar !== undefined ? (
        <BarPemakaian nilai={bar} bahaya={bahaya} />
      ) : null}
    </div>
  );
}

function BarisJob({ job }: { job: JobSistem }) {
  return (
    <div className="border-b border-line py-4 last:border-0 last:pb-0 first:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-ink">
            Job {job.id} · {labelTipe(job.tipe)}
          </p>
          <p className="mt-0.5 text-xs leading-5 text-muted">
            Wilayah {job.kdprov}/{job.kdkab}
            {job.user ? ` · oleh ${job.user}` : ""}
          </p>
        </div>
        <BadgeStatus status={job.status} />
      </div>

      <dl className="mt-3 grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-muted">Mulai</dt>
          <dd className="mt-0.5 font-medium text-ink">
            {formatWaktu(job.started_at)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Heartbeat</dt>
          <dd className="mt-0.5 font-medium text-ink">
            {formatWaktu(job.heartbeat_at)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Umur heartbeat</dt>
          <dd className="mt-0.5 font-medium text-ink">
            {nilaiDurasi(job.umur_heartbeat_detik)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Baris tersimpan</dt>
          <dd className="mt-0.5 font-medium text-ink">
            {formatAngka(job.jumlah_baris)}
          </dd>
        </div>
      </dl>

      {job.pesan ? (
        <p className="mt-3 rounded-lg bg-paper px-3 py-2 text-sm leading-6 text-ink">
          {job.pesan}
        </p>
      ) : null}
    </div>
  );
}

export function StatusSistem() {
  const [status, setStatus] = useState<StatusSistem | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [galat, setGalat] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const muat = useCallback(async (senyap = false) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    if (!senyap) {
      setMemuat(true);
      setGalat(null);
    }

    try {
      const hasil = await ambilJson<StatusSistem>("/sistem/status", {
        signal: controller.signal,
      });
      if (controller.signal.aborted) {
        return;
      }
      setStatus(hasil);
      setGalat(null);
    } catch (galatMuat) {
      if (!adalahBatal(galatMuat)) {
        setGalat(pesanKesalahan(galatMuat));
      }
    } finally {
      if (!controller.signal.aborted) {
        setMemuat(false);
      }
    }
  }, []);

  useEffect(() => {
    // Tunda satu tick agar setState tidak dipanggil langsung di badan effect.
    const awal = window.setTimeout(() => {
      void muat();
    }, 0);

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void muat(true);
      }
    }, 5000);

    function saatTerlihat() {
      if (document.visibilityState === "visible") {
        void muat(true);
      }
    }

    document.addEventListener("visibilitychange", saatTerlihat);
    return () => {
      window.clearTimeout(awal);
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", saatTerlihat);
      controllerRef.current?.abort();
    };
  }, [muat]);

  if (memuat && status === null) {
    return (
      <Panel
        judul="Memuat status sistem"
        deskripsi="Membaca status worker, antrean, dan pemakaian server."
      >
        <p className="mt-4 text-sm leading-6 text-muted" role="status">
          Memuat...
        </p>
      </Panel>
    );
  }

  if (status === null) {
    return (
      <Panel
        judul="Status sistem belum tersedia"
        deskripsi="Backend tidak dapat dihubungi atau status belum terbaca."
      >
        {galat ? (
          <div
            role="alert"
            className="mt-4 rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm leading-6 text-danger"
          >
            <p>{galat}</p>
            <button
              type="button"
              onClick={() => void muat()}
              className="mt-2 min-h-11 rounded-lg border border-danger/30 bg-surface px-3 text-sm font-semibold text-danger"
            >
              Coba lagi
            </button>
          </div>
        ) : null}
      </Panel>
    );
  }

  const { sistem, worker, konfigurasi, antrean } = status;
  const memori = sistem.memori;
  const disk = sistem.disk;
  const ramPenuh = (memori.persen_terpakai ?? 0) >= 85;
  const diskPenuh = (disk.persen_terpakai ?? 0) >= 90;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted" aria-live="polite">
          Terakhir dibaca {formatWaktu(status.waktu)}. Diperbarui otomatis
          setiap 5 detik.
        </p>
        <TombolAksi varian="sekunder" onClick={() => void muat()}>
          Muat ulang
        </TombolAksi>
      </div>

      {galat ? (
        <div
          role="alert"
          className="rounded-lg border border-danger/25 bg-danger-soft px-4 py-3 text-sm leading-6 text-danger"
        >
          <p>{galat}</p>
          <p className="mt-1 text-xs">
            Data terakhir tetap ditampilkan sampai pembaruan berhasil.
          </p>
        </div>
      ) : null}

      {status.peringatan.length > 0 ? (
        <div
          role="alert"
          className="rounded-lg border border-accent/30 bg-accent-soft px-4 py-3 text-sm leading-6 text-ink"
        >
          <p className="font-semibold">Perlu perhatian</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {status.peringatan.map((pesan) => (
              <li key={pesan}>{pesan}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KartuMetrik
          label="Worker"
          nilai={worker.aktif ? "Hidup" : "Mati"}
          keterangan={
            worker.aktif
              ? `PID ${worker.pid ?? "-"} · ${worker.jumlah_proses} proses`
              : "Tidak ada proses worker yang memegang kunci."
          }
        />
        <KartuMetrik
          label="RAM worker"
          nilai={nilaiMb(worker.rss_mb)}
          keterangan={`Anggaran ${formatAngka(worker.batas_memori_mb)} MB`}
          bar={
            worker.rss_mb != null && worker.batas_memori_mb > 0
              ? (worker.rss_mb / worker.batas_memori_mb) * 100
              : undefined
          }
          bahaya={
            worker.rss_mb != null &&
            worker.batas_memori_mb > 0 &&
            worker.rss_mb > worker.batas_memori_mb
          }
        />
        <KartuMetrik
          label="RAM server"
          nilai={nilaiPersen(memori.persen_terpakai)}
          keterangan={`${nilaiMb(memori.terpakai_mb)} terpakai · ${nilaiMb(
            memori.tersedia_mb,
          )} tersedia`}
          bar={memori.persen_terpakai}
          bahaya={ramPenuh}
        />
        <KartuMetrik
          label="Disk data"
          nilai={nilaiPersen(disk.persen_terpakai)}
          keterangan={`${nilaiMb(disk.tersedia_mb)} tersedia dari ${nilaiMb(
            disk.total_mb,
          )}`}
          bar={disk.persen_terpakai}
          bahaya={diskPenuh}
        />
      </div>

      <Panel
        judul="Antrean job"
        deskripsi="Job diproses satu per satu oleh worker; status diperbarui setiap 5 detik."
      >
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {(
            [
              ["Menunggu", antrean.menunggu],
              ["Diproses", antrean.jalan],
              ["Sukses", antrean.sukses],
              ["Gagal", antrean.gagal],
            ] as const
          ).map(([label, jumlah]) => (
            <div
              key={label}
              className="rounded-lg border border-line bg-paper/60 px-3 py-3"
            >
              <p className="text-xs font-semibold text-muted">{label}</p>
              <p className="mt-1 font-display text-xl font-semibold text-ink">
                {formatAngka(jumlah)}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs leading-5 text-muted">
          Total {formatAngka(antrean.total)} job
          {antrean.tertua_menunggu
            ? ` · job menunggu paling lama sejak ${formatWaktu(
                antrean.tertua_menunggu,
              )}`
            : ""}
          .
        </p>

        {status.job_aktif.length > 0 ? (
          <div className="mt-5">
            <p className="text-sm font-semibold text-ink">Job sedang diproses</p>
            <div className="mt-2">
              {status.job_aktif.map((job) => (
                <BarisJob key={job.id} job={job} />
              ))}
            </div>
          </div>
        ) : (
          <EmptyState judul="Tidak ada job yang sedang diproses">
            Worker akan mengambil job berikutnya dalam waktu paling lama{" "}
            {formatAngka(Math.round(konfigurasi.poll_detik))} detik.
          </EmptyState>
        )}

        {status.job_terakhir ? (
          <div className="mt-5">
            <p className="text-sm font-semibold text-ink">Job terakhir</p>
            <div className="mt-2">
              <BarisJob job={status.job_terakhir} />
            </div>
          </div>
        ) : null}
      </Panel>

      <Panel
        judul="Detail server"
        deskripsi="Angka RAM dalam MB. Nilai yang tidak tersedia di sistem operasi ditampilkan sebagai tanda minus."
      >
        <dl className="mt-4 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="text-muted">Host</dt>
            <dd className="mt-0.5 font-medium text-ink">{sistem.hostname}</dd>
          </div>
          <div>
            <dt className="text-muted">CPU</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {sistem.cpu == null ? "-" : `${sistem.cpu} core`}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Load average</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {sistem.load_1 == null
                ? "-"
                : `${sistem.load_1} / ${sistem.load_5} / ${sistem.load_15}`}
            </dd>
          </div>
          <div>
            <dt className="text-muted">RAM API</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {nilaiMb(memori.api_rss_mb)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Swap terpakai</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {nilaiMb(memori.swap_terpakai_mb)} dari{" "}
              {nilaiMb(memori.swap_total_mb)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Disk terpakai</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {nilaiMb(disk.terpakai_mb)} dari {nilaiMb(disk.total_mb)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Polling worker</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {konfigurasi.poll_detik} detik
            </dd>
          </div>
          <div>
            <dt className="text-muted">Heartbeat job</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {konfigurasi.heartbeat_detik} detik
            </dd>
          </div>
          <div>
            <dt className="text-muted">Batas heartbeat</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {konfigurasi.timeout_menit} menit
            </dd>
          </div>
          <div>
            <dt className="text-muted">Potongan titik</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {konfigurasi.chunk_titik > 0
                ? `${formatAngka(konfigurasi.chunk_titik)} baris`
                : "Tanpa potongan"}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Maks. worker</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {konfigurasi.max_workers}
            </dd>
          </div>
        </dl>
      </Panel>
    </div>
  );
}
