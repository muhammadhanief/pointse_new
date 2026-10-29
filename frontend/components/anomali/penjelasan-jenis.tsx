"use client";

import { Modal } from "@/components/dashboard/modal";
import { ISTILAH, PENGANTAR } from "@/lib/anomali/istilah";

/** Modal penjelasan tiap jenis pencermatan titik. */
export function PenjelasanJenis({
  terbuka,
  onTutup,
}: {
  terbuka: boolean;
  onTutup: () => void;
}) {
  return (
    <Modal
      terbuka={terbuka}
      judul="Arti jenis pencermatan titik"
      onTutup={onTutup}
      ukuran="lg"
    >
      <p className="rounded-lg border border-accent/30 bg-accent-soft/50 px-3 py-2 text-sm leading-6 text-ink">
        {PENGANTAR}
      </p>

      <dl className="mt-4 space-y-4">
        {ISTILAH.map((satu) => (
          <div
            key={satu.kode}
            className="border-b border-line pb-4 last:border-0 last:pb-0"
          >
            <dt className="text-sm font-semibold text-ink">{satu.judul}</dt>
            <dd className="mt-1 text-sm leading-6 text-muted">
              {satu.isi}
              {satu.solusi ? (
                <p className="mt-2 border-l-2 border-accent pl-3 text-ink">
                  <span className="font-semibold">Solusi: </span>
                  {satu.solusi}
                </p>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 text-xs leading-5 text-muted">
        Kolom kode yang kosong bukan data hilang: memang titik itu tidak ada di
        sumber tersebut. Titik yang sudah dihitung pada run lama bisa masih
        memakai keterangan versi sebelumnya sampai run B-nya dihitung ulang.
      </p>
    </Modal>
  );
}
