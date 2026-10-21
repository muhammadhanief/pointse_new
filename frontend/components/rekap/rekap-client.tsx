"use client";

import { useState } from "react";

import { PerjalananB } from "./perjalanan-b";
import { PerjalananBProvinsi } from "./perjalanan-b-provinsi";
import { TabulasiRekap } from "./tabulasi-rekap";

type Tab = "tabel" | "grafik" | "tren";

function RekapTabs({
  tab,
  onTab,
}: {
  tab: Tab;
  onTab: (tab: Tab) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Tampilan rekap"
      className="flex flex-wrap gap-field"
    >
      {(
        [
          ["tabel", "Tabel"],
          ["grafik", "Grafik"],
          ["tren", "Tren"],
        ] as const
      ).map(([nilai, label]) => (
        <button
          key={nilai}
          type="button"
          role="tab"
          id={`tab-rekap-${nilai}`}
          aria-selected={tab === nilai}
          aria-controls="panel-rekap"
          onClick={() => onTab(nilai)}
          className={`min-h-8 rounded-lg px-tombol text-sm font-semibold transition-colors ${
            tab === nilai
              ? "bg-brand text-white"
              : "border border-line bg-surface text-muted hover:border-brand hover:text-brand-strong"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function RekapClient({
  kdprov,
  kdkabAwal,
}: {
  kdprov: string;
  kdkabAwal: string | null;
}) {
  const [tab, setTab] = useState<Tab>("tabel");

  if (tab === "tren") {
    return (
      <div className="space-y-field">
        <div className="flex flex-wrap items-center gap-1.5">
          <RekapTabs tab={tab} onTab={setTab} />
        </div>
        <div id="panel-rekap" role="tabpanel">
          {kdkabAwal ? (
            <PerjalananB kdkab={kdkabAwal} />
          ) : (
            <PerjalananBProvinsi kdprov={kdprov} />
          )}
        </div>
      </div>
    );
  }

  return (
    <div id="panel-rekap" role="tabpanel">
      <TabulasiRekap
        kdprov={kdprov}
        kdkabAwal={kdkabAwal}
        tampilan={tab}
        kontrol={<RekapTabs tab={tab} onTab={setTab} />}
      />
    </div>
  );
}
