export default function DashboardLoading() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="space-y-field"
    >
      <p className="text-sm text-muted">Memuat ruang kerja...</p>

      <div className="border-b border-line pb-4">
        <div className="h-9 w-64 max-w-full animate-pulse rounded-md bg-line/60" />
        <div className="mt-1 h-4 w-full max-w-xl animate-pulse rounded bg-line/40" />
      </div>

      <div className="grid gap-field xl:grid-cols-2">
        <div className="h-60 animate-pulse rounded-xl border border-line bg-surface" />
        <div className="h-60 animate-pulse rounded-xl border border-line bg-surface" />
      </div>
    </div>
  );
}
