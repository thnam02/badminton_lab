import { formatMetric, formatPercentile } from "@/lib/format";
import type { ReferenceComparisonData } from "@/lib/types";

type Props = {
  data: ReferenceComparisonData;
  profileHint?: string | null;
};

export function ReferenceComparison({ data, profileHint }: Props) {
  const low = data.reference_low;
  const high = data.reference_high;
  const median = data.reference_median;
  const you = data.player_value;

  let markerPct = 50;
  if (low != null && high != null && high !== low) {
    markerPct = ((you - low) / (high - low)) * 100;
  } else if (median != null) {
    markerPct = you <= median ? 35 : 65;
  }
  markerPct = Math.max(0, Math.min(100, markerPct));

  return (
    <article className="flex flex-col rounded-[18px] border border-border bg-surface p-5">
      <h3 className="font-display font-semibold">{data.title || "Metric"}</h3>
      <p className="mt-1 text-sm text-text-muted">
        Compared with the {data.group_label || "reference group"}
      </p>

      <p className="mt-4 font-display text-3xl font-bold tabular-nums">
        {formatMetric(you, data.unit)}
      </p>
      {formatPercentile(data.percentile) && (
        <p className="text-sm text-text-muted">
          {formatPercentile(data.percentile)} in the comparison group
        </p>
      )}

      <div className="mt-5">
        <div className="mb-1.5 flex justify-between gap-2 text-[11px] uppercase tracking-wide text-text-muted">
          <span>P10 {formatMetric(low, data.unit)}</span>
          <span>Median {formatMetric(median, data.unit)}</span>
          <span>P90 {formatMetric(high, data.unit)}</span>
        </div>
        <div
          className="relative h-2 rounded-full bg-surface-2"
          role="img"
          aria-label={`Your value ${formatMetric(you, data.unit)} versus reference median ${formatMetric(median, data.unit)}`}
        >
          {median != null && low != null && high != null && high !== low && (
            <div
              className="absolute top-0 h-full w-0.5 bg-text-muted"
              style={{
                left: `${((median - low) / (high - low)) * 100}%`,
              }}
              aria-hidden
            />
          )}
          <div
            className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent ring-2 ring-surface"
            style={{ left: `${markerPct}%` }}
            aria-hidden
          />
        </div>
        <p className="mt-2 text-xs font-medium text-accent">You</p>
      </div>

      <p className="mt-4 break-all text-xs text-text-muted">
        {profileHint || data.reference_profile_id || "Reference profile"}
      </p>
    </article>
  );
}
