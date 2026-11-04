import type { AssessmentScope } from "@/lib/types";

export const NOT_ASSESSED_HEADING = "Not assessed from this camera angle";
export const NO_ISSUES_HEADING = "No technique issues found";

export function LimitedViewNotice({ scope }: { scope?: AssessmentScope | null }) {
  if (!scope?.limited_view || !scope.limited_view_message) return null;
  return (
    <aside
      aria-label="Limited camera angle"
      className="rounded-lg border border-[var(--accent)]/40 bg-[var(--accent-soft)] px-4 py-3 text-sm text-[var(--fg)]"
    >
      {scope.limited_view_message}
    </aside>
  );
}

/**
 * Summary of what was checked. Never claims "no issues" when side-view-only
 * checks were skipped because of the camera angle.
 */
export function TechniqueCheckSummary({
  scope,
  findingsCount,
}: {
  scope?: AssessmentScope | null;
  findingsCount: number;
}) {
  if (scope?.limited_view) {
    return (
      <section
        aria-label={NOT_ASSESSED_HEADING}
        className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg)] p-4"
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          {NOT_ASSESSED_HEADING}
        </h2>
        {scope.not_assessed.length > 0 && (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[var(--fg)]">
            {scope.not_assessed.map((c) => (
              <li key={c.code}>{c.title}</li>
            ))}
          </ul>
        )}
      </section>
    );
  }
  if (scope && findingsCount === 0) {
    return (
      <section
        aria-label={NO_ISSUES_HEADING}
        className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4"
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          {NO_ISSUES_HEADING}
        </h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          None of the technique checks flagged anything in this stroke.
        </p>
      </section>
    );
  }
  return null;
}
