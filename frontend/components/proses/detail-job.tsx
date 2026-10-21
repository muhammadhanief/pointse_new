"use client";

import { useEffect, useRef } from "react";

import { IkonTutup } from "@/components/dashboard/icons";
import type { Run } from "@/lib/api/types";
import { kodeWilayah } from "@/lib/auth/peran";
import { formatAngka, formatTanggal, formatWaktu } from "@/lib/format";
import { istilahProses, labelNomorJob } from "@/lib/istilah";
import { namaKabupaten } from "@/lib/wilayah/kabupaten";

import { BadgeStatus } from "./badge-status";
import { UnduhanJob } from "./unduhan-job";

function Info({ label, nilai }: { label: string; nilai: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-medium text-ink">{nilai}</dd>
    </div>
  );
}

export function DetailJob({
  run,
  onTutup,
}: {
  run: Run | null;
  onTutup: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (run) {
      if (!dialog.open) {
        dialog.showModal();
      }
      const overflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = overflow;
      };
    }

    if (dialog.open) {
      dialog.close();
    }
  }, [run]);

  const judul =
    run?.tipe === "A" ? "Peta SLS/SubSLS Final" : "Titik Hasil Perbaikan";
  const terhenti =
    run?.status === "gagal" && /terhenti/i.test(run.pesan ?? "");
  const sumber =
    run?.tipe === "A"
      ? run.geotag_master_nomor
        ? `Master geotag ke-${run.geotag_master_nomor}`
        : "-"
      : run?.sumber_run_a_nomor
        ? `Peta SLS/SubSLS ke-${run.sumber_run_a_nomor}`
        : "-";
  const detailTitik =
    run?.status === "sukses"
      ? run.detail_tersedia
        ? "Tersimpan"
        : "Sudah dipangkas"
      : run?.status === "gagal"
        ? "Tidak tersedia"
        : "Belum ada";

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="judul-detail-job"
      onClose={onTutup}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onTutup();
        }
      }}
      className="m-auto w-[min(64rem,calc(100vw-2rem))] max-h-[85vh] overflow-hidden rounded-xl border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-ink/40"
    >
      {run ? (
        <div className="max-h-[85vh] overflow-y-auto p-kartu">
          <div className="flex items-start justify-between gap-field">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                Detail job
              </p>
              <h2
                id="judul-detail-job"
                className="mt-1 text-base font-semibold tracking-tight text-ink"
              >
                {judul} · {labelNomorJob(run.nomor_urut)}
              </h2>
              <p className="mt-1 text-xs text-muted">
                {kodeWilayah(run.kdprov, run.kdkab)} ·{" "}
                {namaKabupaten(run.kdprov, run.kdkab) ?? "-"}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <BadgeStatus status={run.status} terhenti={terhenti} />
              <button
                type="button"
                onClick={onTutup}
                aria-label="Tutup detail job"
                className="grid h-9 w-9 place-items-center rounded-lg text-muted transition-colors hover:bg-paper hover:text-ink"
              >
                <IkonTutup className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="mt-3 grid gap-field lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
            <div className="lg:col-start-2 lg:row-start-1">
              <UnduhanJob run={run} />
            </div>

            <div className="min-w-0 lg:col-start-1 lg:row-start-1">
              <dl className="grid gap-x-3 gap-y-2 text-sm sm:grid-cols-2">
                <Info label="Wilayah" nilai={`${run.kdprov}/${run.kdkab}`} />
                <Info label="Pengguna" nilai={run.user ?? "-"} />
                <Info
                  label="Tanggal data"
                  nilai={formatTanggal(run.tanggal_data)}
                />
                <Info label="Dibuat" nilai={formatWaktu(run.created_at)} />
                <Info label="Mulai" nilai={formatWaktu(run.started_at)} />
                <Info label="Selesai" nilai={formatWaktu(run.finished_at)} />
                <Info label="Heartbeat" nilai={formatWaktu(run.heartbeat_at)} />
                <Info
                  label="Jumlah baris"
                  nilai={formatAngka(run.jumlah_baris)}
                />
                <Info
                  label="Tanpa wilayah"
                  nilai={formatAngka(run.jumlah_tanpa_wilayah)}
                />
                <Info
                  label={run.tipe === "A" ? "Master geotag" : "Sumber peta"}
                  nilai={sumber}
                />
                <Info label="Detail titik" nilai={detailTitik} />
              </dl>

              <div className="mt-3 rounded-lg bg-paper px-3 py-2 text-sm">
                <p className="text-xs text-muted">Berkas input</p>
                <p className="mt-1 break-all font-medium text-ink">
                  {run.nama_file_input}
                </p>
                <p className="mt-2 text-xs text-muted">Berkas peta</p>
                <p className="mt-1 break-all font-medium text-ink">
                  {run.nama_file_peta}
                </p>
                <p className="mt-2 text-xs text-muted">
                  Layer input: {run.layer_input ?? "-"}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Layer peta: {run.layer_peta ?? "-"}
                </p>
              </div>

              {run.pesan ? (
                <p
                  className={`mt-3 rounded-lg px-3 py-2 text-sm leading-normal ${
                    run.status === "gagal"
                      ? "bg-danger-soft text-danger"
                      : "bg-paper text-ink"
                  }`}
                >
                  {istilahProses(run.pesan)}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </dialog>
  );
}
