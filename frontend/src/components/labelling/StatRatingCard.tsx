"use client";

import { useState } from "react";
import {
  formatStatValue,
  type ClipStat,
  type LabellingClip,
  type StatLabel,
  type StatRating,
} from "@/lib/labelling";

type Props = {
  stat: ClipStat;
  options: LabellingClip["rating_options"];
  value: StatLabel | undefined;
  onChange: (next: StatLabel) => void;
};

const RATING_STYLES: Record<StatRating, string> = {
  good: "border-accent bg-accent/15",
  needs_work: "border-warn bg-warn/15",
  looks_wrong: "border-danger bg-danger/15",
};

export function StatRatingCard({ stat, options, value, onChange }: Props) {
  const rating = value?.rating ?? null;
  const comment = value?.comment ?? "";
  const [showComment, setShowComment] = useState(Boolean(comment));

  return (
    <fieldset className="flex flex-col gap-3 rounded-[18px] border border-border bg-surface px-5 pb-5 pt-3">
      <legend className="px-1.5 font-display text-lg font-bold">{stat.name}</legend>
      <p className="text-base text-text-muted">{stat.description}</p>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-base">
        <div className="flex gap-1.5">
          <dt className="text-text-muted">When:</dt>
          <dd>{stat.when}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-text-muted">Measured:</dt>
          <dd className="font-semibold">{formatStatValue(stat.value, stat.unit)}</dd>
        </div>
      </dl>
      {stat.available ? (
        <>
          <div className="grid grid-cols-3 gap-2">
            {options.map((opt) => {
              const on = rating === opt.id;
              return (
                <label
                  key={opt.id}
                  title={opt.hint}
                  className={`flex min-h-14 cursor-pointer items-center justify-center rounded-[14px] border-2 px-2 text-center text-base font-semibold has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${
                    on ? RATING_STYLES[opt.id] : "border-border bg-surface-2 hover:border-text-muted/50"
                  }`}
                >
                  <input
                    type="radio"
                    name={`rating-${stat.id}`}
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
          {showComment ? (
            <label className="flex flex-col gap-1.5 text-base font-semibold">
              Comment (optional)
              <textarea
                rows={2}
                maxLength={1000}
                value={comment}
                onChange={(e) => onChange({ rating, comment: e.target.value })}
                className="resize-y rounded-[14px] border border-border bg-surface-2 p-3 font-normal text-text"
              />
            </label>
          ) : (
            <button
              type="button"
              onClick={() => setShowComment(true)}
              className="inline-flex min-h-12 items-center self-start rounded-xl px-3 text-base font-medium text-accent hover:bg-surface-2"
            >
              + Add a comment
            </button>
          )}
        </>
      ) : (
        <p className="text-base text-text-muted">
          Not measured in this clip, so there&apos;s nothing to rate.
        </p>
      )}
    </fieldset>
  );
}
