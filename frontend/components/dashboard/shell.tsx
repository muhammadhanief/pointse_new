"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type {
  ComponentType,
  KeyboardEvent as ReactKeyboardEvent,
  ReactNode,
  SVGProps,
} from "react";

import { hapusToken } from "@/lib/api/token";
import type { SesiPengguna } from "@/lib/auth/types";
import {
  PERAN_ADMIN_PROVINSI,
  labelPeran,
  labelWilayah,
  type NamaPeran,
} from "@/lib/auth/peran";

import {
  IkonBeranda,
  IkonEkspor,
  IkonKeluar,
  IkonMaster,
  IkonMenu,
  IkonPengecekan,
  IkonRekap,
  IkonSistem,
  IkonTutup,
  IkonUnggah,
} from "./icons";

type SesiRingkas = Pick<
  SesiPengguna,
  "nama" | "peran" | "kdprov" | "kdkab"
>;

type Ikon = ComponentType<SVGProps<SVGSVGElement>>;

type ItemMenu = {
  href: string;
  label: string;
  ikon: Ikon;
  peran?: NamaPeran[];
};

type GrupMenu = {
  label: string;
  item: ItemMenu[];
};

const MENU: GrupMenu[] = [
  {
    label: "Ringkasan",
    item: [{ href: "/", label: "Beranda", ikon: IkonBeranda }],
  },
  {
    label: "Proses",
    item: [
      {
        href: "/proses/identifikasi",
        label: "1. Identifikasi Titik",
        ikon: IkonUnggah,
      },
      {
        href: "/proses/pengecekan",
        label: "2. Pengecekan Titik",
        ikon: IkonPengecekan,
      },
    ],
  },
  {
    label: "Hasil",
    item: [
      { href: "/rekap", label: "Rekap progres", ikon: IkonRekap },
      { href: "/ekspor", label: "Ekspor", ikon: IkonEkspor },
    ],
  },
  {
    label: "Administrasi",
    item: [
      {
        href: "/master-geotag",
        label: "Master geotag",
        ikon: IkonMaster,
        peran: [PERAN_ADMIN_PROVINSI],
      },
      {
        href: "/sistem",
        label: "Status sistem",
        ikon: IkonSistem,
        peran: [PERAN_ADMIN_PROVINSI],
      },
    ],
  },
];

function menuUntuk(peran: NamaPeran): GrupMenu[] {
  return MENU.map((grup) => ({
    ...grup,
    item: grup.item.filter((item) => !item.peran || item.peran.includes(peran)),
  })).filter((grup) => grup.item.length > 0);
}

function ItemNavigasi({
  item,
  aktif,
  onPilih,
}: {
  item: ItemMenu;
  aktif: boolean;
  onPilih?: () => void;
}) {
  const IkonItem = item.ikon;

  return (
    <Link
      href={item.href}
      onClick={onPilih}
      aria-current={aktif ? "page" : undefined}
      className={`flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors ${
        aktif
          ? "bg-brand text-white"
          : "text-ink/80 hover:bg-brand-soft hover:text-brand-strong"
      }`}
    >
      <IkonItem className="h-[18px] w-[18px] shrink-0" />
      <span>{item.label}</span>
    </Link>
  );
}

function DaftarMenu({
  sesi,
  pathname,
  onPilih,
}: {
  sesi: SesiRingkas;
  pathname: string;
  onPilih?: () => void;
}) {
  const grup = menuUntuk(sesi.peran);

  return (
    <nav aria-label="Menu utama" className="flex-1 overflow-y-auto px-3 py-4">
      <div className="space-y-6">
        {grup.map((satuGrup) => (
          <div key={satuGrup.label}>
            <p className="px-3 text-[11px] font-semibold text-muted">
              {satuGrup.label}
            </p>
            <div className="mt-2 space-y-1">
              {satuGrup.item.map((item) => (
                <ItemNavigasi
                  key={item.href}
                  item={item}
                  aktif={
                    pathname === item.href ||
                    (item.href !== "/" && pathname.startsWith(`${item.href}/`))
                  }
                  onPilih={onPilih}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </nav>
  );
}

function KartuPengguna({ sesi }: { sesi: SesiRingkas }) {
  const inisial = sesi.nama.trim().charAt(0).toUpperCase() || "P";

  return (
    <div className="border-t border-line p-4">
      <div className="flex items-center gap-3">
        <div
          aria-hidden="true"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-soft text-sm font-semibold text-brand-strong"
        >
          {inisial}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{sesi.nama}</p>
          <p className="truncate text-xs text-muted">{labelPeran(sesi.peran)}</p>
        </div>
      </div>
      <p className="mt-2 text-xs leading-5 text-muted">
        {labelWilayah(sesi.kdprov, sesi.kdkab)}
      </p>
      <form
        action="/api/auth/logout"
        method="post"
        className="mt-2"
        onSubmit={() => hapusToken()}
      >
        <button
          type="submit"
          className="flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium text-danger transition-colors hover:bg-danger-soft"
        >
          <IkonKeluar className="h-[18px] w-[18px] shrink-0" />
          Keluar
        </button>
      </form>
    </div>
  );
}

function jagaFokus(event: ReactKeyboardEvent<HTMLElement>) {
  if (event.key !== "Tab") {
    return;
  }

  const fokusable = Array.from(
    event.currentTarget.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled])',
    ),
  );
  if (fokusable.length === 0) {
    return;
  }

  const pertama = fokusable[0];
  const terakhir = fokusable[fokusable.length - 1];

  if (event.shiftKey && document.activeElement === pertama) {
    event.preventDefault();
    terakhir.focus();
  } else if (!event.shiftKey && document.activeElement === terakhir) {
    event.preventDefault();
    pertama.focus();
  }
}

export function Shell({
  sesi,
  children,
}: {
  sesi: SesiRingkas;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [menuSeluler, setMenuSeluler] = useState(false);
  const tombolTutupRef = useRef<HTMLButtonElement>(null);
  const tombolMenuRef = useRef<HTMLButtonElement>(null);

  function tutupMenu() {
    setMenuSeluler(false);
    requestAnimationFrame(() => tombolMenuRef.current?.focus());
  }

  useEffect(() => {
    const layarLebar = window.matchMedia("(min-width: 1024px)");
    function ubahLayar(event: MediaQueryListEvent) {
      if (event.matches) {
        setMenuSeluler(false);
      }
    }

    layarLebar.addEventListener("change", ubahLayar);
    return () => layarLebar.removeEventListener("change", ubahLayar);
  }, []);

  useEffect(() => {
    if (!menuSeluler) {
      return;
    }

    tombolTutupRef.current?.focus();
    const overflowAwal = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function tekanTombol(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuSeluler(false);
        requestAnimationFrame(() => tombolMenuRef.current?.focus());
      }
    }

    document.addEventListener("keydown", tekanTombol);
    return () => {
      document.removeEventListener("keydown", tekanTombol);
      document.body.style.overflow = overflowAwal;
    };
  }, [menuSeluler]);

  return (
    <div className="min-h-dvh bg-paper text-ink">
      <a
        href="#konten"
        inert={menuSeluler ? true : undefined}
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-brand focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        Lewati ke konten
      </a>

      <aside className="fixed inset-y-0 left-0 hidden w-[17rem] flex-col border-r border-line bg-surface lg:flex">
        <div className="border-b border-line px-5 py-5">
          <Link href="/" className="inline-flex flex-col">
            <span className="font-display text-2xl font-semibold tracking-tight text-brand">
              Pointse
            </span>
            <span className="mt-0.5 text-xs font-medium text-muted">
              Monitoring Wilkerstat, BPS
            </span>
          </Link>
        </div>

        <DaftarMenu sesi={sesi} pathname={pathname} />
        <KartuPengguna sesi={sesi} />
      </aside>

      <div
        inert={menuSeluler ? true : undefined}
        className="flex min-h-dvh flex-col lg:pl-[17rem]"
      >
        <header className="sticky top-0 z-30 flex min-h-14 items-center justify-between gap-4 border-b border-line bg-paper px-4 sm:px-6 lg:px-10">
          <div className="flex items-center gap-3">
            <button
              ref={tombolMenuRef}
              type="button"
              aria-expanded={menuSeluler}
              aria-controls={menuSeluler ? "menu-seluler" : undefined}
              aria-haspopup="dialog"
              onClick={() => setMenuSeluler(true)}
              className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-line-strong bg-surface px-3 text-sm font-semibold text-ink transition-colors hover:border-brand lg:hidden"
            >
              <IkonMenu className="h-[18px] w-[18px]" />
              Menu
            </button>
            <Link
              href="/"
              className="font-display text-lg font-semibold tracking-tight text-ink lg:hidden"
            >
              Pointse
            </Link>
            <p className="hidden text-sm text-muted lg:block">
              Monitoring editing batas Wilkerstat
            </p>
          </div>

          <p className="hidden text-right text-xs text-muted sm:block">
            <span className="hidden md:inline">Wilayah kerja </span>
            <span className="font-semibold text-ink">
              {labelWilayah(sesi.kdprov, sesi.kdkab)}
            </span>
          </p>
        </header>

        <main
          id="konten"
          className="mx-auto w-full max-w-[82rem] flex-1 px-4 py-8 sm:px-6 lg:px-10 lg:py-10"
        >
          {children}
        </main>

        <footer className="border-t border-line px-4 py-5 text-xs text-muted sm:px-6 lg:px-10">
          Badan Pusat Statistik, Pointse
        </footer>
      </div>

      {menuSeluler ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            tabIndex={-1}
            aria-label="Tutup menu"
            onClick={tutupMenu}
            className="absolute inset-0 bg-ink/35"
          />
          <aside
            id="menu-seluler"
            role="dialog"
            aria-modal="true"
            aria-label="Menu utama"
            onKeyDown={jagaFokus}
            className="relative flex h-full w-[min(20rem,85vw)] flex-col border-r border-line bg-surface shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <span className="font-display text-lg font-semibold tracking-tight text-brand">
                Pointse
              </span>
              <button
                ref={tombolTutupRef}
                type="button"
                aria-label="Tutup menu"
                onClick={tutupMenu}
                className="grid h-11 w-11 place-items-center rounded-lg text-muted transition-colors hover:bg-brand-soft hover:text-brand-strong"
              >
                <IkonTutup className="h-5 w-5" />
              </button>
            </div>

            <DaftarMenu
              sesi={sesi}
              pathname={pathname}
              onPilih={tutupMenu}
            />
            <KartuPengguna sesi={sesi} />
          </aside>
        </div>
      ) : null}
    </div>
  );
}
