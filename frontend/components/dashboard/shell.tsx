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

import { ambilJson } from "@/lib/api/klien";
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
  IkonKeluar,
  IkonMaster,
  IkonMenu,
  IkonPengecekan,
  IkonPengguna,
  IkonRekap,
  IkonRiwayat,
  IkonSidebar,
  IkonSistem,
  IkonTutup,
  IkonUnggah,
} from "./icons";

type SesiRingkas = Pick<
  SesiPengguna,
  "nama" | "peran" | "kdprov" | "kdkab" | "foto_url"
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
        label: "1. Unggah Peta SLS/SubSLS Final",
        ikon: IkonUnggah,
      },
      {
        href: "/proses/pengecekan",
        label: "2. Unggah Titik Hasil Perbaikan",
        ikon: IkonPengecekan,
      },
    ],
  },
  {
    label: "Pemantauan",
    item: [
      { href: "/riwayat", label: "Riwayat upload", ikon: IkonRiwayat },
    ],
  },
  {
    label: "Hasil",
    item: [
      { href: "/rekap", label: "Rekap progres", ikon: IkonRekap },
    ],
  },
  {
    label: "Administrasi",
    item: [
      {
        href: "/pengguna",
        label: "Pengguna aktif",
        ikon: IkonPengguna,
        peran: [PERAN_ADMIN_PROVINSI],
      },
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
  ringkas = false,
}: {
  item: ItemMenu;
  aktif: boolean;
  onPilih?: () => void;
  ringkas?: boolean;
}) {
  const IkonItem = item.ikon;

  return (
    <Link
      href={item.href}
      onClick={onPilih}
      aria-current={aktif ? "page" : undefined}
      title={ringkas ? item.label : undefined}
      className={`flex min-h-10 items-center rounded-lg py-menu text-xs font-medium leading-snug transition-colors ${
        ringkas ? "justify-center px-2" : "gap-2.5 px-menu"
      } ${
        aktif
          ? "bg-brand text-white"
          : "text-ink/80 hover:bg-brand-soft hover:text-brand-strong"
      }`}
    >
      <IkonItem className="h-[18px] w-[18px] shrink-0" />
      <span className={ringkas ? "sr-only" : undefined}>{item.label}</span>
    </Link>
  );
}

function DaftarMenu({
  sesi,
  pathname,
  onPilih,
  ringkas = false,
}: {
  sesi: SesiRingkas;
  pathname: string;
  onPilih?: () => void;
  ringkas?: boolean;
}) {
  const grup = menuUntuk(sesi.peran);

  return (
    <nav
      aria-label="Menu utama"
      className={`flex-1 overflow-y-auto ${ringkas ? "p-2" : "p-sidebar"}`}
    >
      <div className={ringkas ? "space-y-2" : "space-y-1"}>
        {grup.map((satuGrup, indeks) => (
          <div
            key={satuGrup.label}
            className={
              ringkas && indeks > 0 ? "border-t border-line pt-2" : undefined
            }
          >
            <p
              className={
                ringkas
                  ? "sr-only"
                  : "mb-1 mt-3 px-3 text-[11px] font-semibold uppercase tracking-wide text-muted first:mt-0"
              }
            >
              {satuGrup.label}
            </p>
            <div className="space-y-1">
              {satuGrup.item.map((item) => (
                <ItemNavigasi
                  key={item.href}
                  item={item}
                  aktif={
                    pathname === item.href ||
                    (item.href !== "/" && pathname.startsWith(`${item.href}/`))
                  }
                  onPilih={onPilih}
                  ringkas={ringkas}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </nav>
  );
}

function KartuPengguna({
  sesi,
  ringkas = false,
}: {
  sesi: SesiRingkas;
  ringkas?: boolean;
}) {
  const [fotoGagal, setFotoGagal] = useState(false);
  const inisial = sesi.nama.trim().charAt(0).toUpperCase() || "P";

  return (
    <div className={`border-t border-line ${ringkas ? "p-2" : "p-sidebar"}`}>
      <div
        className={
          ringkas
            ? "flex flex-col items-center gap-2"
            : "flex items-center gap-2"
        }
      >
        {sesi.foto_url && !fotoGagal ? (
          <img
            src={sesi.foto_url}
            alt=""
            aria-hidden="true"
            title={ringkas ? sesi.nama : undefined}
            loading="lazy"
            onError={() => setFotoGagal(true)}
            className="h-8 w-8 shrink-0 rounded-md border border-line object-cover"
          />
        ) : (
          <div
            aria-hidden="true"
            title={ringkas ? sesi.nama : undefined}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-brand-soft text-xs font-semibold text-brand-strong"
          >
            {inisial}
          </div>
        )}
        {ringkas ? (
          <span className="sr-only">{sesi.nama}</span>
        ) : (
          <p className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
            {sesi.nama}
          </p>
        )}
        <form action="/api/auth/logout" method="post" onSubmit={() => hapusToken()}>
          <button
            type="submit"
            aria-label="Keluar"
            title="Keluar"
            className="grid h-9 w-9 place-items-center rounded-md text-danger transition-colors hover:bg-danger-soft"
          >
            <IkonKeluar className="h-4 w-4" />
          </button>
        </form>
      </div>
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
  const [ringkas, setRingkas] = useState(false);
  const tombolTutupRef = useRef<HTMLButtonElement>(null);
  const tombolMenuRef = useRef<HTMLButtonElement>(null);

  function tutupMenu() {
    setMenuSeluler(false);
    requestAnimationFrame(() => tombolMenuRef.current?.focus());
  }

  function gantiRingkas() {
    setRingkas((lama) => {
      const baru = !lama;
      try {
        window.localStorage.setItem("pointse.sidebar.ringkas", baru ? "1" : "0");
      } catch {
        // localStorage bisa diblokir; sidebar tetap bisa dibuka/tutup.
      }
      return baru;
    });
  }

  useEffect(() => {
    try {
      setRingkas(window.localStorage.getItem("pointse.sidebar.ringkas") === "1");
    } catch {
      // abaikan
    }
  }, []);

  useEffect(() => {
    let dibatalkan = false;

    async function kirimKehadiran() {
      if (dibatalkan || document.visibilityState === "hidden") {
        return;
      }
      try {
        await ambilJson<{ status: string }>("/kehadiran", { method: "POST" });
      } catch {
        // Kehadiran bersifat pemantauan; kegagalan tidak mengganggu halaman.
      }
    }

    function saatTerlihat() {
      if (document.visibilityState === "visible") {
        void kirimKehadiran();
      }
    }

    void kirimKehadiran();
    const timer = window.setInterval(kirimKehadiran, 60_000);
    document.addEventListener("visibilitychange", saatTerlihat);

    return () => {
      dibatalkan = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", saatTerlihat);
    };
  }, []);

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
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-brand focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        Lewati ke konten
      </a>

      <aside
        id="sidebar-utama"
        className={`fixed inset-y-0 left-0 hidden flex-col border-r border-line bg-surface transition-[width] duration-200 motion-reduce:transition-none lg:flex ${
          ringkas ? "w-16" : "w-[17rem]"
        }`}
      >
        <div className={`border-b border-line ${ringkas ? "p-3" : "p-4"}`}>
          <Link
            href="/"
            title="Pointse"
            className={`inline-flex ${
              ringkas ? "w-full items-center justify-center" : "flex-col"
            }`}
          >
            <span
              aria-hidden={ringkas ? true : undefined}
              className="font-display text-xl font-semibold tracking-tight text-brand"
            >
              {ringkas ? "P" : "Pointse"}
            </span>
            {ringkas ? (
              <span className="sr-only">Pointse</span>
            ) : (
              <span className="mt-1 text-xs font-medium text-muted">
                Monitoring Wilkerstat, BPS
              </span>
            )}
          </Link>
        </div>

        <DaftarMenu sesi={sesi} pathname={pathname} ringkas={ringkas} />
        <KartuPengguna sesi={sesi} ringkas={ringkas} />
      </aside>

      <div
        inert={menuSeluler ? true : undefined}
        className={`flex min-h-dvh flex-col transition-[padding] duration-200 motion-reduce:transition-none ${
          ringkas ? "lg:pl-16" : "lg:pl-[17rem]"
        }`}
      >
        <header className="sticky top-0 z-30 flex min-h-14 items-center justify-between gap-field border-b border-line bg-paper px-konten">
          <div className="flex items-center gap-2">
            <button
              ref={tombolMenuRef}
              type="button"
              aria-expanded={menuSeluler}
              aria-controls={menuSeluler ? "menu-seluler" : undefined}
              aria-haspopup="dialog"
              onClick={() => setMenuSeluler(true)}
              className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-line-strong bg-surface px-tombol py-2 text-sm font-semibold text-ink transition-colors hover:border-brand lg:hidden"
            >
              <IkonMenu className="h-[18px] w-[18px]" />
              Menu
            </button>
            <button
              type="button"
              onClick={gantiRingkas}
              aria-controls="sidebar-utama"
              aria-expanded={!ringkas}
              aria-label={ringkas ? "Buka sidebar" : "Ringkas sidebar"}
              title={ringkas ? "Buka sidebar" : "Ringkas sidebar"}
              className="hidden h-9 w-9 place-items-center rounded-lg border border-line-strong bg-surface text-muted transition-colors hover:border-brand hover:text-brand-strong lg:grid"
            >
              <IkonSidebar
                className={`h-[18px] w-[18px] transition-transform motion-reduce:transition-none ${
                  ringkas ? "rotate-180" : ""
                }`}
              />
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
            <span className="font-semibold text-ink">
              {labelPeran(sesi.peran)}
            </span>
            <span className="hidden md:inline">
              {" "}
              · {labelWilayah(sesi.kdprov, sesi.kdkab)}
            </span>
          </p>
        </header>

        <main
          id="konten"
          className="mx-auto w-full max-w-[82rem] flex-1 px-konten py-konten"
        >
          {children}
        </main>

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
            <div className="flex items-center justify-between border-b border-line p-4">
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
