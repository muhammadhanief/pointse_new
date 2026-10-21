import type { StatusRun } from "@/lib/api/types";

const LABEL: Record<StatusRun, string> = {
  menunggu: "Menunggu",
  jalan: "Diproses",
  sukses: "Sukses",
  gagal: "Gagal",
};

const GAYA: Record<StatusRun, string> = {
  menunggu: "border-accent/30 bg-accent-soft text-accent-strong",
  jalan: "border-brand/30 bg-brand-soft text-brand-strong",
  sukses: "border-success/30 bg-success-soft text-success",
  gagal: "border-danger/25 bg-danger-soft text-danger",
};

export function BadgeStatus({
  status,
  terhenti = false,
  rata = "end",
}: {
  status: StatusRun;
  terhenti?: boolean;
  rata?: "start" | "end";
}) {
  return (
    <div
      className={`flex flex-wrap items-center gap-field ${
        rata === "start" ? "justify-start" : "justify-end"
      }`}
    >
      <span
        className={`inline-flex min-h-7 items-center rounded-md border px-2 text-xs font-semibold ${GAYA[status]}`}
      >
        {LABEL[status]}
      </span>
      {terhenti ? (
        <span className="text-xs font-semibold text-danger">
          Proses terhenti
        </span>
      ) : null}
    </div>
  );
}
