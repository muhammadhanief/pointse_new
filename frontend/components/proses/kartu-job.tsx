import { kodeWilayah } from "@/lib/auth/peran";
import type { Run } from "@/lib/api/types";
import {
  formatAngka,
  formatTanggal,
  formatWaktu,
} from "@/lib/format";
import {
  istilahProses,
  labelNomorJob,
  labelTipe,
} from "@/lib/istilah";
import { namaKabupaten } from "@/lib/wilayah/kabupaten";

import { BadgeStatus } from "./badge-status";

function Info({ label, nilai }: { label: string; nilai: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 font-medium text-ink">{nilai}</dd>
    </div>
  );
}

export function KartuJob({ run }: { run: Run }) {
  const terhenti =
    run.status === "gagal" &&
    /terhenti/i.test(run.pesan ?? "");
  const kode = kodeWilayah(run.kdprov, run.kdkab);
  const nama = namaKabupaten(run.kdprov, run.kdkab);

  return (
    <article className="py-5 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink">
            {labelTipe(run.tipe)} · {kode}
          </h3>
          <p className="mt-1 text-xs leading-5 text-muted">
            {nama ? `${nama} · ` : ""}Provinsi {run.kdprov} ·{" "}
            {labelNomorJob(run.nomor_urut)} · tanggal data{" "}
            {formatTanggal(run.tanggal_data)} · oleh {run.user ?? "-"}.
          </p>
        </div>
        <BadgeStatus status={run.status} terhenti={terhenti} />
      </div>

      <dl className="mt-4 grid gap-x-6 gap-y-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <Info label="Mulai" nilai={formatWaktu(run.started_at)} />
        <Info label="Selesai" nilai={formatWaktu(run.finished_at)} />
        <Info
          label="Heartbeat"
          nilai={
            run.status === "jalan" || run.status === "gagal"
              ? run.heartbeat_at
                ? formatWaktu(run.heartbeat_at)
                : "Belum ada heartbeat"
              : "-"
          }
        />
        <Info label="Dibuat" nilai={formatWaktu(run.created_at)} />
        <Info
          label={
            run.status === "sukses"
              ? "Jumlah baris"
              : run.status === "gagal"
                ? "Baris sebelum gagal"
                : "Baris tersimpan"
          }
          nilai={formatAngka(run.jumlah_baris)}
        />
        <Info
          label="Tanpa wilayah"
          nilai={formatAngka(run.jumlah_tanpa_wilayah)}
        />
        <Info
          label={run.tipe === "A" ? "Master geotag" : "Sumber peta"}
          nilai={
            run.tipe === "A"
              ? run.geotag_master_nomor
                ? `versi ke-${run.geotag_master_nomor}`
                : "-"
              : run.sumber_run_a_nomor
                ? `Job ke-${run.sumber_run_a_nomor}`
                : "-"
          }
        />
        <Info
          label="Detail titik"
          nilai={
            run.status === "sukses"
              ? run.detail_tersedia
                ? "Tersimpan"
                : "Sudah dipangkas"
              : run.status === "gagal"
                ? "Tidak tersedia"
                : "Belum ada"
          }
        />
      </dl>

      {run.pesan ? (
        <p className="mt-3 rounded-lg bg-paper px-3 py-2 text-sm leading-6 text-ink">
          {istilahProses(run.pesan)}
        </p>
      ) : null}

      <p className="mt-3 break-words text-xs leading-5 text-muted">
        Berkas: {run.nama_file_input}. Peta: {run.nama_file_peta}.
      </p>
    </article>
  );
}
