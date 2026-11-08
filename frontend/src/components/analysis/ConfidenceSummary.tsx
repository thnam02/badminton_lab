import { Card } from "@/components/ui/Card";
import { cardTitle } from "@/components/ui/styles";
import { confidenceLabel } from "@/lib/format";
import type { ConfidenceLevel, ConfidenceSummary } from "@/lib/types";

type Props = {
  confidence: ConfidenceSummary;
  limitations?: string[];
};

/** Limitations arrive highest priority first; only the top few are shown. */
export const MAX_LIMITATIONS = 3;

function barClass(level: ConfidenceLevel): string {
  if (level === "LOW") return "bg-warn";
  if (level === "MODERATE") return "bg-accent-soft";
  return "bg-accent";
}

export function ConfidenceSummaryPanel({ confidence, limitations }: Props) {
  const shown = (limitations ?? []).slice(0, MAX_LIMITATIONS);

  return (
    <Card aria-labelledby="confidence-title" className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="confidence-title" className={cardTitle}>
          How sure are we?
        </h2>
        <p className="text-sm">
          <span className="text-text-muted">Overall </span>
          <span className="font-semibold">{confidenceLabel(confidence.overall)}</span>
        </p>
      </div>

      {confidence.message && (
        <p className="text-sm text-text-soft">{confidence.message}</p>
      )}

      {confidence.components.length > 0 && (
        <ul className="flex flex-col gap-2.5 text-sm">
          {confidence.components.map((c) => (
            <li
              key={c.id}
              className="grid grid-cols-[minmax(0,9.5rem)_1fr_auto] items-center gap-3"
            >
              <span className="text-text-soft">{c.label}</span>
              <span className="h-1.5 rounded-full bg-border" aria-hidden>
                <span
                  className={`block h-full rounded-full ${barClass(c.level)}`}
                  style={{ width: `${Math.max(0, Math.min(1, c.score)) * 100}%` }}
                />
              </span>
              <span
                className="text-text-muted"
                aria-label={`${c.label}: ${confidenceLabel(c.level)}`}
              >
                {confidenceLabel(c.level)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {shown.length > 0 && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <h3 className="text-sm font-semibold text-text-muted">Limitations</h3>
          <ul
            aria-label="Limitations"
            className="flex list-disc flex-col gap-1.5 pl-5 text-sm text-text-soft"
          >
            {shown.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
