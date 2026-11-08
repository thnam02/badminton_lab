import { Card } from "@/components/ui/Card";
import { cardTitle, eyebrow } from "@/components/ui/styles";
import { formatMetric } from "@/lib/format";
import type { DisplayMetric } from "@/lib/types";

type Metric = { id: string; label: string; value: number; unit: string; note?: string | null };

type Props = {
  metrics: Metric[];
  /** Tier 3 metrics: context only, never technique issues. */
  displayMetrics?: DisplayMetric[];
};

export function MetricsPanel({ metrics, displayMetrics = [] }: Props) {
  return (
    <Card aria-labelledby="metrics-title" className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="metrics-title" className={cardTitle}>
          Measurements
        </h2>
        <span className="text-xs text-text-muted">Raw measurements from this clip</span>
      </div>
      {!metrics.length && !displayMetrics.length ? (
        <p className="text-sm text-text-muted" role="status">
          Stroke metrics are not available for this analysis.
        </p>
      ) : (
        <>
          {displayMetrics.length > 0 && (
            <section aria-label="For reference only" className="flex flex-col gap-2">
              <h3 className={eyebrow}>For reference only</h3>
              <p className="text-xs text-text-muted">
                Shown for context. These values are not judged as technique faults.
              </p>
              <MetricTiles rows={displayMetrics} />
            </section>
          )}
          {metrics.length > 0 && (
            <section aria-label="Stroke metrics" className="flex flex-col gap-2">
              {displayMetrics.length > 0 && <h3 className={eyebrow}>Stroke metrics</h3>}
              <MetricTiles rows={metrics} />
            </section>
          )}
        </>
      )}
    </Card>
  );
}

function MetricTiles({ rows }: { rows: Metric[] }) {
  return (
    <dl className="grid grid-cols-2 gap-2.5">
      {rows.map((m) => (
        <div key={m.id} className="min-w-0 rounded-xl bg-surface-2 p-3.5">
          <dt className="text-xs text-text-muted">{m.label}</dt>
          <dd className="font-display text-xl font-bold tabular-nums">
            {formatMetric(m.value, m.unit, m.unit === "" ? 2 : 1)}
          </dd>
          {m.note && <dd className="mt-0.5 text-xs text-text-muted">{m.note}</dd>}
        </div>
      ))}
    </dl>
  );
}
