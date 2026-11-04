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

export function isPartialAssessment(scope?: AssessmentScope | null): boolean {
  return Boolean(scope?.coverage_known && !scope.complete && (scope.applicable_count ?? 0) > 0);
}

/** Replacement for "no focus / no issues" wording when not everything was checked. */
export function assessmentGapNote(scope?: AssessmentScope | null): string | undefined {
  if (scope?.limited_view) return "Not assessed from this camera angle.";
  if (isPartialAssessment(scope)) return "Some items could not be checked for this stroke.";
  return undefined;
}

/**
 * Summary of what was checked. "No technique issues found" appears only when
 * every applicable rule ran and the camera angle allowed the full rule set.
 */
export function TechniqueCheckSummary({
  scope,
  findingsCount,
}: {
  scope?: AssessmentScope | null;
  findingsCount: number;
}) {
  if (!scope) return null;
  const partial = isPartialAssessment(scope);
  const heading = `Checked ${scope.checked_count ?? 0} of ${scope.applicable_count ?? 0} items`;
  return (
    <>
      {partial && (
        <section
          aria-label={heading}
          className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg)] p-4"
        >
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
            {heading}
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[var(--fg)]">
            {(scope.unchecked ?? []).map((u) => (
              <li key={u.code}>{u.reason}</li>
            ))}
          </ul>
        </section>
      )}
      {scope.limited_view && (
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
      )}
      {!scope.limited_view && scope.complete && findingsCount === 0 && (
        <section
          aria-label={NO_ISSUES_HEADING}
          className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4"
        >
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
            {NO_ISSUES_HEADING}
          </h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            All {scope.applicable_count} technique checks ran and none flagged anything in this
            stroke.
          </p>
        </section>
      )}
    </>
  );
}
