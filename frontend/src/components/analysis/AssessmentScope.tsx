import { InfoIcon } from "@/components/ui/icons";
import { cardTitle } from "@/components/ui/styles";
import type { AssessmentScope } from "@/lib/types";

export const NOT_ASSESSED_HEADING = "Not assessed from this camera angle";
export const NO_ISSUES_HEADING = "No technique issues found";

const scopeCard = "rounded-card border border-dashed border-border bg-surface p-6";

export function LimitedViewNotice({ scope }: { scope?: AssessmentScope | null }) {
  if (!scope?.limited_view || !scope.limited_view_message) return null;
  return (
    <aside
      aria-label="Limited camera angle"
      className="flex items-start gap-2 rounded-card border border-warn/40 bg-warn/10 px-5 py-3 text-sm text-text"
    >
      <InfoIcon className="mt-[3px] flex-none text-warn" />
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
        <section aria-label={heading} className={scopeCard}>
          <h2 className={cardTitle}>{heading}</h2>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-text-soft">
            {(scope.unchecked ?? []).map((u) => (
              <li key={u.code}>{u.reason}</li>
            ))}
          </ul>
        </section>
      )}
      {scope.limited_view && (
        <section aria-label={NOT_ASSESSED_HEADING} className={scopeCard}>
          <h2 className={cardTitle}>{NOT_ASSESSED_HEADING}</h2>
          {scope.not_assessed.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-text-soft">
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
          className="rounded-card border border-border bg-surface p-6"
        >
          <h2 className={cardTitle}>{NO_ISSUES_HEADING}</h2>
          <p className="mt-1 text-sm text-text-muted">
            All {scope.applicable_count} technique checks ran and none flagged anything in this
            stroke.
          </p>
        </section>
      )}
    </>
  );
}
