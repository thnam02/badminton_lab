"use client";

import {
  describeStatValue,
  formatStatValue,
  type ReviewQuestion,
  type StatLabel,
  type StatRating,
} from "@/lib/labelling";

type Props = {
  question: ReviewQuestion;
  value: StatLabel | undefined;
  /** The question belongs to the moment currently shown on the video. */
  active: boolean;
  onChange: (next: StatLabel) => void;
};

const RATING_STYLES: Record<StatRating, string> = {
  good: "border-accent bg-accent/15",
  needs_work: "border-warn bg-warn/15",
  looks_wrong: "border-text-muted bg-text-muted/15",
  cant_see: "border-text-muted bg-text-muted/15",
};

export function QuestionCard({ question: q, value, active, onChange }: Props) {
  const rating = value?.rating ?? null;
  const comment = value?.comment ?? "";
  const measured = q.kind === "measured";

  return (
    <fieldset
      data-active={active || undefined}
      className={`m-0 flex flex-col gap-2.5 rounded-2xl bg-surface px-4 py-3.5 ${
        active ? "border-2 border-accent" : "border border-border"
      }`}
    >
      <legend className="sr-only">{q.title}</legend>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="font-bold">{q.title}</span>
          <span className="text-sm text-text-muted">{q.hint}</span>
          {measured && q.measured_at && (
            <span className="text-xs text-text-muted">Measured: {q.measured_at.label.toLowerCase()}</span>
          )}
        </div>
        <span
          className={`whitespace-nowrap font-display text-xl font-bold ${
            measured && q.available ? "text-text" : "text-text-muted"
          }`}
          title={measured ? describeStatValue(q.value, q.unit) : undefined}
        >
          {measured ? formatStatValue(q.value, q.unit) : "You judge"}
        </span>
      </div>
      {q.available ? (
        <>
          <div className="grid grid-cols-3 gap-1.5">
            {q.rating_options.map((opt) => {
              const on = rating === opt.id;
              return (
                <label
                  key={opt.id}
                  title={opt.hint}
                  className={`flex min-h-12 cursor-pointer items-center justify-center rounded-xl border-2 px-1.5 text-center text-[15px] font-semibold has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${
                    on ? RATING_STYLES[opt.id] : "border-border bg-surface-2 hover:border-text-muted/50"
                  }`}
                >
                  <input
                    type="radio"
                    name={`rating-${q.id}`}
                    value={opt.id}
                    checked={on}
                    onChange={() => onChange({ rating: opt.id, comment })}
                    className="sr-only"
                  />
                  {opt.label}
                </label>
              );
            })}
          </div>
          <input
            type="text"
            value={comment}
            maxLength={1000}
            placeholder="Comment (optional)"
            aria-label={`Comment on ${q.title}`}
            onChange={(e) => onChange({ rating, comment: e.target.value })}
            className="min-h-12 rounded-[10px] border border-border bg-surface-2 px-3 text-[15px] text-text"
          />
        </>
      ) : (
        <p className="text-sm text-text-muted">
          Not measured in this clip, so there&apos;s nothing to rate.
        </p>
      )}
    </fieldset>
  );
}
