import { IkonEkspor, IkonTutup } from "@/components/dashboard/icons";

export type NotifikasiUnduhData = {
  nama: string;
  status: "menyiapkan" | "mulai";
};

export function NotifikasiUnduh({
  data,
  onTutup,
}: {
  data: NotifikasiUnduhData;
  onTutup: () => void;
}) {
  const menyiapkan = data.status === "menyiapkan";

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-4 bottom-4 z-50 rounded-xl border border-line bg-surface p-4 shadow-lg sm:left-auto sm:right-6 sm:w-[22rem]"
    >
      <div className="flex items-start gap-3">
        <div
          aria-hidden="true"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand-strong"
        >
          <IkonEkspor className="h-5 w-5" />
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">
            {menyiapkan ? "Menyiapkan unduhan" : "Unduhan dimulai"}
          </p>
          <p className="mt-0.5 break-words text-xs leading-5 text-muted">
            {data.nama}
          </p>
          <p className="mt-1 text-xs leading-5 text-muted">
            {menyiapkan
              ? "Berkas sedang disiapkan di server."
              : "Berkas besar bisa memakan waktu. Cek folder Unduhan browser."}
          </p>
        </div>

        <button
          type="button"
          onClick={onTutup}
          aria-label="Tutup notifikasi unduhan"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-brand-soft hover:text-brand-strong"
        >
          <IkonTutup className="h-5 w-5" />
        </button>
      </div>

      {menyiapkan ? (
        <div
          aria-hidden="true"
          className="mt-3 h-1 w-1/3 animate-pulse rounded-full bg-brand"
        />
      ) : null}
    </div>
  );
}
