"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { cardTitle, chip } from "@/components/ui/styles";
import {
  SEVERITY_LABELS,
  fetchRuleDrafts,
  formatBoundaryValue,
  type RuleDraft,
} from "@/lib/coach";
import { formatDate } from "@/lib/format";

const IMPORTANCE_LABELS: Record<string, string> = {
  tip: "A small tip",
  worth_fixing: "Worth fixing",
  must_fix_first: "Must fix first",
};

const AGREEMENT: Record<string, { label: string; className: string }> = {
  separates_well: { label: "Separates well", className: "border-accent/50 text-accent-soft" },
  overlaps: { label: "Overlaps", className: "border-danger/50 text-danger" },
  not_enough_data: { label: "Not enough data", className: "border-border text-text-muted" },
};

export function RuleDraftList() {
  const [drafts, setDrafts] = useState<RuleDraft[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRuleDrafts()
      .then(setDrafts)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load drafts"));
  }, []);

  if (error) {
    return (
      <p className="text-danger" role="alert">
        {error}
      </p>
    );
  }
  if (!drafts) {
    return (
      <p className="text-text-muted" role="status">
        Loading drafts…
      </p>
    );
  }
  if (drafts.length === 0) {
    return (
      <Card>
        <p className="text-text-muted">
          No coach drafts yet. Rules saved in My rules appear here for the team to review.
        </p>
      </Card>
    );
  }

  return (
    <ul className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr))]">
      {drafts.map((d) => {
        const agreement = AGREEMENT[d.agreement.status] ?? AGREEMENT.not_enough_data;
        return (
          <li key={d.id}>
            <Card as="article" className="flex h-full flex-col gap-3 p-5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <h2 className={cardTitle}>{d.title}</h2>
                  <span className="text-xs text-text-muted">
                    {d.stroke_label} · {d.metric_label}
                  </span>
                </div>
                <span
                  className={`whitespace-nowrap rounded-full border px-2.5 py-1 text-xs ${agreement.className}`}
                >
                  {agreement.label}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className={chip}>By {d.coach}</span>
                <span className={`${chip} border-dashed`}>Draft · not used in analysis</span>
              </div>
              <dl className="grid grid-cols-3 gap-2 text-[13px]">
                <div>
                  <dt className="text-text-muted">Boundary</dt>
                  <dd className="font-semibold">
                    {d.boundary.label} ({formatBoundaryValue(d.boundary.value, d.boundary.unit)})
                  </dd>
                </div>
                <div>
                  <dt className="text-text-muted">Importance</dt>
                  <dd className="font-semibold">
                    {IMPORTANCE_LABELS[d.importance] ?? d.importance} · up to{" "}
                    {SEVERITY_LABELS[d.severity_cap] ?? d.severity_cap}
                  </dd>
                </div>
                <div>
                  <dt className="text-text-muted">Clips</dt>
                  <dd className="font-semibold">
                    {d.agreement.caught}/{d.agreement.fault_clips} caught ·{" "}
                    {d.agreement.false_flags} false
                  </dd>
                </div>
              </dl>
              {d.message && (
                <p className="text-sm text-text-soft">&ldquo;{d.message}&rdquo;</p>
              )}
              <p className="mt-auto text-xs text-text-muted">Saved {formatDate(d.created_at)}</p>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
