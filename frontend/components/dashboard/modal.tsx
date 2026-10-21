"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

import { IkonTutup } from "./icons";

export function Modal({
  terbuka,
  judul,
  onTutup,
  children,
  ukuran = "md",
}: {
  terbuka: boolean;
  judul: string;
  onTutup: () => void;
  children: ReactNode;
  ukuran?: "md" | "lg";
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const judulId = useId();
  const lebar =
    ukuran === "lg"
      ? "w-[min(64rem,calc(100vw-2rem))]"
      : "w-[min(42rem,calc(100vw-2rem))]";

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }

    if (terbuka) {
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
  }, [terbuka]);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={judulId}
      onClose={onTutup}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onTutup();
        }
      }}
      className={`m-auto ${lebar} max-h-[85vh] overflow-hidden rounded-xl border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-ink/40`}
    >
      <div className="flex max-h-[85vh] flex-col">
        <div className="flex items-start justify-between gap-field border-b border-line p-kartu">
          <h2
            id={judulId}
            className="text-base font-semibold tracking-tight text-ink"
          >
            {judul}
          </h2>
          <button
            type="button"
            onClick={onTutup}
            aria-label="Tutup"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-paper hover:text-ink"
          >
            <IkonTutup className="h-4 w-4" />
          </button>
        </div>
        <div className="overflow-y-auto p-kartu">{children}</div>
      </div>
    </dialog>
  );
}
