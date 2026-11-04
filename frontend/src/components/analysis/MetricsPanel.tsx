import { formatMetric } from "@/lib/format";
import type { DisplayMetric } from "@/lib/types";

type Metric = { id: string; label: string; value: number; unit: string; note?: string | null };

type Props = {
  metrics: Metric[];
  /** Tier 3 metrics: context only, never technique issues. */
  displayMetrics?: DisplayMetric[];
};

export function MetricsPanel({ metrics, displayMetrics = [] }: Props) {
  if (!metrics.length && !displayMetrics.length) {
    return (
      <p className="text-sm text-[var(--muted)]" role="status">
        Stroke metrics are not available for this analysis.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {displayMetrics.length > 0 && (
        <section aria-label="For reference only" className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            For reference only
          </h4>
          <p className="text-xs text-[var(--muted)]">
            Shown for context. These values are not judged as technique faults.
          </p>
          <MetricTable caption="Reference-only metrics" rows={displayMetrics} />
        </section>
      )}
      {metrics.length > 0 && <MetricTable caption="Stroke metrics" rows={metrics} />}
    </div>
  );
}

function MetricTable({ caption, rows }: { caption: string; rows: Metric[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)]">
      <table className="min-w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-[var(--border)] text-xs uppercase tracking-wide text-[var(--muted)]">
          <tr>
            <th className="px-4 py-3 font-semibold">Metric</th>
            <th className="px-4 py-3 font-semibold">Value</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.id} className="border-b border-[var(--border)] last:border-0">
              <td className="px-4 py-3">
                {m.label}
                {m.note && (
                  <span className="mt-0.5 block text-xs text-[var(--muted)]">{m.note}</span>
                )}
              </td>
              <td className="px-4 py-3 font-medium">
                {formatMetric(m.value, m.unit, m.unit === "" ? 2 : 1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
