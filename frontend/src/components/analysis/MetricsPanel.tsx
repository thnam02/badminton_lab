import { Card } from "@/components/ui/Card";
import { cardTitle } from "@/components/ui/styles";
import { formatMetric } from "@/lib/format";

type Metric = { id: string; label: string; value: number; unit: string };

type Props = {
  metrics: Metric[];
};

export function MetricsPanel({ metrics }: Props) {
  return (
    <Card aria-labelledby="metrics-title" className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="metrics-title" className={cardTitle}>
          For reference only
        </h2>
        <span className="text-xs text-text-muted">Raw measurements from this clip</span>
      </div>
      {metrics.length ? (
        <dl className="grid grid-cols-2 gap-2.5">
          {metrics.map((m) => (
            <div key={m.id} className="min-w-0 rounded-xl bg-surface-2 p-3.5">
              <dt className="text-xs text-text-muted">{m.label}</dt>
              <dd className="font-display text-xl font-bold tabular-nums">
                {formatMetric(m.value, m.unit, m.unit === "" ? 2 : 1)}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-text-muted" role="status">
          Stroke metrics are not available for this analysis.
        </p>
      )}
    </Card>
  );
}
