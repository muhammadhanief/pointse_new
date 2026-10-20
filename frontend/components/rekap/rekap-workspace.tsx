"use client";

import { useState } from "react";

import { DashboardRekap } from "@/components/rekap/dashboard-rekap";
import { PerjalananB } from "@/components/rekap/perjalanan-b";
import { TargetB } from "@/components/rekap/target-b";
import { daftarKabupaten, labelKabupaten } from "@/lib/wilayah/kabupaten";

type Tab = "ringkasan" | "perjalanan" | "target";

const TAB: { nilai: Tab; label: string }[] = [
  { nilai: "ringkasan", label: "Ringkasan" },
  { nilai: "perjalanan", label: "Perjalanan B" },
  { nilai: "target", label: "Target B" },
];

export function RekapWorkspace({
  kdprov,
  kdkabAwal,
}: {
  kdprov: string;
  kdkabAwal: string | null;
}) {
  const opsi = daftarKabupaten(kdprov);
  const [tab, setTab] = useState<Tab>("ringkasan");
  const [kdkab, setKdkab] = useState(kdkabAwal ?? opsi[0]?.kode ?? "");

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-line pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div role="tablist" aria-label="Bagian rekap" className="flex flex-wrap gap-2">
          {TAB.map((satu) => (
            <button
              key={satu.nilai}
              type="button"
              role="tab"
              id={`tab-${satu.nilai}`}
              aria-selected={tab === satu.nilai}
              aria-controls={`panel-${satu.nilai}`}
              onClick={() => setTab(satu.nilai)}
              className={`min-h-10 rounded-lg px-3 text-sm font-semibold transition-colors ${
                tab === satu.nilai
                  ? "bg-brand text-white"
                  : "border border-line bg-surface text-muted hover:border-brand hover:text-brand-strong"
              }`}
            >
              {satu.label}
            </button>
          ))}
        </div>

        {opsi.length > 0 ? (
          <label className="text-sm font-medium text-ink">
            Kabupaten/kota
            {kdkabAwal ? (
              <span className="mt-1.5 block min-h-10 text-sm font-medium text-muted">
                {labelKabupaten(kdprov, kdkabAwal)}
              </span>
            ) : (
              <select
                value={kdkab}
                onChange={(event) => setKdkab(event.target.value)}
                className="mt-1.5 block min-h-10 min-w-[14rem] rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink"
              >
                {opsi.map((satu) => (
                  <option key={satu.kode} value={satu.kode}>
                    {satu.nama}
                  </option>
                ))}
              </select>
            )}
          </label>
        ) : null}
      </div>

      <div id="panel-ringkasan" role="tabpanel" aria-labelledby="tab-ringkasan">
        {tab === "ringkasan" ? <DashboardRekap /> : null}
      </div>
      <div id="panel-perjalanan" role="tabpanel" aria-labelledby="tab-perjalanan">
        {tab === "perjalanan" ? <PerjalananB kdkab={kdkab} /> : null}
      </div>
      <div id="panel-target" role="tabpanel" aria-labelledby="tab-target">
        {tab === "target" ? <TargetB kdkab={kdkab} /> : null}
      </div>
    </div>
  );
}
