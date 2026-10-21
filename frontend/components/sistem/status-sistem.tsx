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
import { formatAngka, formatBytes, formatWaktu } from "@/lib/format";
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
      className="mt-1 h-2 overflow-hidden rounded-full bg-brand-soft"
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
    <div className="rounded-lg border border-line bg-paper/60 p-kartu">
      <p className="text-xs font-semibold text-muted">{label}</p>
      <p className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
        {nilai}
      </p>
      <p className="mt-bantuan text-xs leading-5 text-muted">{keterangan}</p>
      {bar !== undefined ? (
        <BarPemakaian nilai={bar} bahaya={bahaya} />
      ) : null}
    </div>
  );
}

function BarisJob({ job }: { job: JobSistem }) {
  return (
    <div className="border-b border-line py-2 last:border-0 last:pb-0 first:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-field">
        <div>
          <p className="text-sm font-semibold text-ink">
            Job {job.id} · {labelTipe(job.tipe)}
          </p>
          <p className="mt-bantuan text-xs leading-5 text-muted">
            Wilayah {job.kdprov}/{job.kdkab}
            {job.user ? ` · oleh ${job.user}` : ""}
          </p>
        </div>
        <BadgeStatus status={job.status} />
      </div>

      <dl className="mt-1 grid gap-x-3 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-muted">Mulai</dt>
          <dd className="mt-1 font-medium text-ink">
            {formatWaktu(job.started_at)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Heartbeat</dt>
          <dd className="mt-1 font-medium text-ink">
            {formatWaktu(job.heartbeat_at)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Umur heartbeat</dt>
          <dd className="mt-1 font-medium text-ink">
            {nilaiDurasi(job.umur_heartbeat_detik)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Baris tersimpan</dt>
          <dd className="mt-1 font-medium text-ink">
            {formatAngka(job.jumlah_baris)}
          </dd>
        </div>
      </dl>

      {job.pesan ? (
        <p className="mt-1 rounded-lg bg-paper px-3 py-2 text-sm leading-normal text-ink">
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
        <p className="mt-1 text-sm leading-normal text-muted" role="status">
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
            className="mt-1 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger"
          >
            <p>{galat}</p>
            <button
              type="button"
              onClick={() => void muat()}
              className="mt-1 min-h-9 rounded-lg border border-danger/30 bg-surface px-tombol text-sm font-semibold text-danger"
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
    <div className="space-y-field">
      <div className="flex flex-wrap items-center justify-between gap-field">
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
          className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2 text-sm leading-normal text-danger"
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
          className="rounded-lg border border-accent/30 bg-accent-soft px-3 py-2 text-sm leading-normal text-ink"
        >
          <p className="font-semibold">Perlu perhatian</p>
          <ul className="mt-1 list-disc space-y-field pl-5">
            {status.peringatan.map((pesan) => (
              <li key={pesan}>{pesan}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="grid gap-field sm:grid-cols-2 xl:grid-cols-4">
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
        <div className="mt-3 grid grid-cols-2 gap-field sm:grid-cols-4">
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
              className="rounded-lg border border-line bg-paper/60 px-3 py-2"
            >
              <p className="text-xs font-semibold text-muted">{label}</p>
              <p className="mt-1 font-display text-xl font-semibold text-ink">
                {formatAngka(jumlah)}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-bantuan text-xs leading-5 text-muted">
          Total {formatAngka(antrean.total)} job
          {antrean.tertua_menunggu
            ? ` · job menunggu paling lama sejak ${formatWaktu(
                antrean.tertua_menunggu,
              )}`
            : ""}
          .
        </p>

        {status.job_aktif.length > 0 ? (
          <div className="mt-3">
            <p className="text-sm font-semibold text-ink">Job sedang diproses</p>
            <div className="mt-1">
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
          <div className="mt-3">
            <p className="text-sm font-semibold text-ink">Job terakhir</p>
            <div className="mt-1">
              <BarisJob job={status.job_terakhir} />
            </div>
          </div>
        ) : null}
      </Panel>

      <Panel
        judul="Heartbeat worker"
        deskripsi="Satu baris per proses worker. Worker yang heartbeat-nya lebih lama dari batas dianggap tidak aktif."
      >
        {status.heartbeats.length === 0 ? (
          <EmptyState judul="Belum ada heartbeat worker">
            Jalankan service worker setelah migrasi 0009 agar heartbeat tercatat.
          </EmptyState>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th className="py-2 pl-3 pr-3 font-semibold">Worker</th>
                  <th className="py-2 pr-3 font-semibold">PID</th>
                  <th className="py-2 pr-3 font-semibold">Status</th>
                  <th className="py-2 pr-3 font-semibold">Job</th>
                  <th className="py-2 pr-3 font-semibold">Heartbeat</th>
                  <th className="py-2 text-right font-semibold">Umur</th>
                </tr>
              </thead>
              <tbody>
                {status.heartbeats.map((heartbeat) => (
                  <tr
                    key={heartbeat.worker_id}
                    className="border-b border-line/70 last:border-0"
                  >
                    <td className="break-all py-2 pl-3 pr-3 font-medium text-ink">
                      {heartbeat.worker_id}
                      {heartbeat.hostname ? (
                        <span className="block text-xs font-normal text-muted">
                          {heartbeat.hostname}
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2 pr-3 tabular-nums text-muted">
                      {heartbeat.pid ?? "-"}
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${
                          heartbeat.aktif
                            ? "bg-brand-soft text-brand-strong"
                            : "bg-paper text-muted"
                        }`}
                      >
                        {heartbeat.status}
                        {heartbeat.aktif ? "" : " · tidak aktif"}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-muted">
                      {heartbeat.run_id ? `Job ${heartbeat.run_id}` : "-"}
                    </td>
                    <td className="py-2 pr-3 text-muted">
                      {formatWaktu(heartbeat.heartbeat_at)}
                    </td>
                    <td className="py-2 text-right tabular-nums text-muted">
                      {nilaiDurasi(heartbeat.umur_heartbeat_detik)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel
        judul="Backup harian"
        deskripsi="Status dibaca dari berkas yang ditulis deploy/backup.sh. Backup berjalan di server backend, bukan di cPanel."
      >
        {!status.backup.dikonfigurasi ? (
          <EmptyState judul="Status backup belum dikonfigurasi">
            Isi BACKUP_STATUS_FILE pada environment backend agar hasil backup
            harian terlihat di sini.
          </EmptyState>
        ) : (
          <dl className="mt-1 grid gap-x-3 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-muted">Status terakhir</dt>
              <dd className="mt-1 font-medium text-ink">
                {status.backup.status}
                {status.backup.umur_jam != null
                  ? ` · ${formatAngka(status.backup.umur_jam)} jam lalu`
                  : ""}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Berkas</dt>
              <dd className="mt-1 break-all font-medium text-ink">
                {status.backup.berkas ?? "-"}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Ukuran</dt>
              <dd className="mt-1 font-medium text-ink">
                {formatBytes(status.backup.ukuran_bytes)}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Selesai</dt>
              <dd className="mt-1 font-medium text-ink">
                {formatWaktu(status.backup.waktu_selesai)}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-muted">Pesan</dt>
              <dd className="mt-1 font-medium text-ink">
                {status.backup.pesan ?? "-"}
              </dd>
            </div>
          </dl>
        )}
      </Panel>

      <Panel
        judul="Riwayat kejadian worker"
        deskripsi="Kejadian terbaru (maksimal 50): mulai/berhenti, klaim job, sukses, gagal, job terhenti, dan anggaran memori."
      >
        {status.kejadian.length === 0 ? (
          <EmptyState judul="Belum ada kejadian">
            Kejadian akan tercatat saat worker mulai atau memproses job.
          </EmptyState>
        ) : (
          <div className="mt-3 max-h-[55vh] overflow-auto overscroll-contain rounded-lg border border-line">
            <table className="w-full min-w-[52rem] border-collapse text-[13px]">
              <caption className="sr-only">
                Riwayat kejadian worker, terbaru lebih dulu.
              </caption>
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted">
                  {["Waktu", "Level", "Jenis", "Job", "Worker", "Pesan"].map(
                    (label) => (
                      <th
                        key={label}
                        scope="col"
                        className="sticky top-0 z-10 border-b border-line bg-paper px-3 py-2 font-semibold"
                      >
                        {label}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {status.kejadian.map((kejadian) => (
                  <tr
                    key={kejadian.id}
                    className="border-b border-line/70 last:border-0 hover:bg-brand-soft/20"
                  >
                    <td className="whitespace-nowrap px-3 py-2 text-muted">
                      {formatWaktu(kejadian.created_at)}
                    </td>
                    <td className="px-3 py-2 font-medium text-ink">
                      {kejadian.level}
                    </td>
                    <td className="px-3 py-2 text-muted">{kejadian.jenis}</td>
                    <td className="px-3 py-2 tabular-nums text-muted">
                      {kejadian.run_id ? `Job ${kejadian.run_id}` : "-"}
                    </td>
                    <td className="px-3 py-2 text-muted">
                      {kejadian.worker_id ?? "-"}
                    </td>
                    <td className="max-w-[28rem] break-words px-3 py-2 text-muted">
                      {kejadian.pesan}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel
        judul="Detail server"
        deskripsi="Angka RAM dalam MB. Nilai yang tidak tersedia di sistem operasi ditampilkan sebagai tanda minus."
      >
        <dl className="mt-1 grid gap-x-3 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="text-muted">Host</dt>
            <dd className="mt-1 font-medium text-ink">{sistem.hostname}</dd>
          </div>
          <div>
            <dt className="text-muted">CPU</dt>
            <dd className="mt-1 font-medium text-ink">
              {sistem.cpu == null ? "-" : `${sistem.cpu} core`}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Load average</dt>
            <dd className="mt-1 font-medium text-ink">
              {sistem.load_1 == null
                ? "-"
                : `${sistem.load_1} / ${sistem.load_5} / ${sistem.load_15}`}
            </dd>
          </div>
          <div>
            <dt className="text-muted">RAM API</dt>
            <dd className="mt-1 font-medium text-ink">
              {nilaiMb(memori.api_rss_mb)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Swap terpakai</dt>
            <dd className="mt-1 font-medium text-ink">
              {nilaiMb(memori.swap_terpakai_mb)} dari{" "}
              {nilaiMb(memori.swap_total_mb)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Disk terpakai</dt>
            <dd className="mt-1 font-medium text-ink">
              {nilaiMb(disk.terpakai_mb)} dari {nilaiMb(disk.total_mb)}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Polling worker</dt>
            <dd className="mt-1 font-medium text-ink">
              {konfigurasi.poll_detik} detik
            </dd>
          </div>
          <div>
            <dt className="text-muted">Heartbeat job</dt>
            <dd className="mt-1 font-medium text-ink">
              {konfigurasi.heartbeat_detik} detik
            </dd>
          </div>
          <div>
            <dt className="text-muted">Batas heartbeat</dt>
            <dd className="mt-1 font-medium text-ink">
              {konfigurasi.timeout_menit} menit
            </dd>
          </div>
          <div>
            <dt className="text-muted">Potongan titik</dt>
            <dd className="mt-1 font-medium text-ink">
              {konfigurasi.chunk_titik > 0
                ? `${formatAngka(konfigurasi.chunk_titik)} baris`
                : "Tanpa potongan"}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Maks. worker</dt>
            <dd className="mt-1 font-medium text-ink">
              {konfigurasi.max_workers}
            </dd>
          </div>
        </dl>
      </Panel>
    </div>
  );
}
