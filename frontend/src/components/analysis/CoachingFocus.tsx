import { Card } from "@/components/ui/Card";
import { CheckCircleIcon } from "@/components/ui/icons";
import {
  buttonSecondary,
  cardTitle,
  detailsSummary,
  eyebrow,
} from "@/components/ui/styles";
import { formatMetric, formatPercentile } from "@/lib/format";
import type { CoachingReportView } from "@/lib/types";

type Props = {
  coaching: CoachingReportView;
  onSeek?: (seconds: number) => void;
  /** Set when some checks did not run: replaces any "no focus" wording. */
  assessmentGapNote?: string;
};

export function CoachingFocus({ coaching, onSeek, assessmentGapNote }: Props) {
  if (!coaching.available) {
    return (
      <Card className="flex flex-col gap-2">
        <h2 className={cardTitle}>Coaching</h2>
        <p className="text-sm text-text-muted" role="status">
          Analysis complete. Coaching guidance is temporarily unavailable.
        </p>
        {coaching.caveats?.map((c) => (
          <p key={c} className="text-sm text-text-muted">
            {c}
          </p>
        ))}
      </Card>
    );
  }

  const main = coaching.main_focus;

  return (
    <>
      <Card
        as="article"
        aria-label="Main focus"
        className="flex flex-col gap-5 p-6 sm:p-8"
      >
        {main ? (
          <>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 flex-col gap-2">
                <p className={eyebrow}>Your main focus</p>
                <h2 className="font-display text-[26px] font-bold leading-tight tracking-[-0.01em] sm:text-[30px]">
                  {main.title}
                </h2>
              </div>
              {main.seek_timestamp != null && onSeek && (
                <button
                  type="button"
                  className={buttonSecondary}
                  onClick={() => onSeek(main.seek_timestamp!)}
                >
                  Show this moment in the video
                </button>
              )}
            </div>
            <p className="max-w-3xl leading-relaxed text-text-soft">{main.explanation}</p>
            {main.evidence && (
              <details className="border-t border-border pt-2">
                <summary className={detailsSummary}>View evidence</summary>
                <dl className="flex flex-wrap gap-x-8 gap-y-3 pt-2 text-sm">
                  <div>
                    <dt className="text-text-muted">{main.title}</dt>
                    <dd className="font-display text-xl font-bold">
                      {formatMetric(main.evidence.measured, main.evidence.unit)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-text-muted">Reference median</dt>
                    <dd className="font-display text-xl font-bold">
                      {formatMetric(main.evidence.reference_median, main.evidence.unit)}
                    </dd>
                  </div>
                  {formatPercentile(main.evidence.reference_percentile) && (
                    <div>
                      <dt className="text-text-muted">Percentile vs reference</dt>
                      <dd className="font-display text-xl font-bold">
                        {formatPercentile(main.evidence.reference_percentile)}
                      </dd>
                    </div>
                  )}
                </dl>
              </details>
            )}
            <details className={main.evidence ? "" : "border-t border-border pt-2"}>
              <summary className={detailsSummary}>Why am I seeing this?</summary>
              <p className="pb-1 text-sm text-text-muted">
                This coaching text explains deterministic technique findings. The
                numbers above come from measurement and the reference group — not
                from the AI narrative alone.
              </p>
            </details>
          </>
        ) : (
          <>
            <p className={eyebrow}>Your main focus</p>
            <p className="text-text-soft">
              {coaching.summary ||
                assessmentGapNote ||
                "No primary coaching focus for this stroke."}
            </p>
          </>
        )}
      </Card>

      {coaching.secondary.length > 0 && (
        <section aria-labelledby="secondary-findings" className="flex flex-col gap-3">
          <h2 id="secondary-findings" className={cardTitle}>
            Secondary findings
          </h2>
          <ul className="grid gap-3 lg:grid-cols-2">
            {coaching.secondary.map((item) => (
              <li
                key={item.issue_code}
                className="rounded-[18px] border border-border bg-surface p-5"
              >
                <h3 className="font-display font-semibold">{item.title}</h3>
                <p className="mt-1 text-sm text-text-soft">{item.explanation}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

export function StrengthsCard({ strengths }: { strengths: CoachingReportView["strengths"] }) {
  return (
    <Card aria-labelledby="strengths-title" className="flex flex-col gap-3.5">
      <h2 id="strengths-title" className={cardTitle}>
        What went well
      </h2>
      <ul className="flex flex-col gap-3">
        {strengths.map((s) => (
          <li key={s.description} className="flex items-start gap-3">
            <CheckCircleIcon className="flex-none text-accent" />
            <p className="text-text-soft">{s.description}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
