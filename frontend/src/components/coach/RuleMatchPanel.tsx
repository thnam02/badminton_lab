"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckCircleIcon, WarnIcon } from "@/components/ui/icons";
import { buttonPrimary, buttonSecondary } from "@/components/ui/styles";
import { formatBoundaryValue, type RuleCheck } from "@/lib/coach";
import { formatTimestamp } from "@/lib/format";

type Props = {
  check: RuleCheck | null;
  coach: string;
  strokeLabel: string;
  unit: string;
  agreementLabels: Record<string, string>;
  onUseSuggestion: (pictureId: string) => void;
};

function clips(n: number): string {
  return n === 1 ? "clip" : "clips";
}

const STATUS_CLASSES: Record<string, string> = {
  separates_well: "border-accent/50 bg-accent/10 text-accent-soft",
  overlaps: "border-danger/50 text-danger",
  not_enough_data: "border-border text-text-muted",
};

export function RuleMatchPanel({
  check,
  coach,
  strokeLabel,
  unit,
  agreementLabels,
  onUseSuggestion,
}: Props) {
  const [showDisagreements, setShowDisagreements] = useState(false);
  const [keptChoice, setKeptChoice] = useState<string | null>(null);

  return (
    <section
      aria-labelledby="rule-match-title"
      className="flex flex-col gap-4 rounded-card border-2 border-accent bg-surface p-6"
    >
      <h2 id="rule-match-title" className="font-display text-xl font-bold">
        How your rule matches your clips
      </h2>
      {renderBody()}
    </section>
  );

  function renderBody() {
    if (!coach.trim()) {
      return (
        <p className="text-text-muted">
          Add your name above to compare this rule with the clips you reviewed.
        </p>
      );
    }
    if (!check) {
      return (
        <p className="text-text-muted" role="status">
          Checking your clips…
        </p>
      );
    }
    if (!check.supported) {
      return (
        <p className="flex items-start gap-2 text-warn" role="status">
          <WarnIcon className="mt-1.5 flex-none" />
          {check.reason}
        </p>
      );
    }
    const m = check.match;
    const question = check.target.label_question_title;
    const noun = check.target.problem_noun;
    if (m.reviewed_clips === 0) {
      return (
        <p className="text-text-muted">
          You haven&apos;t reviewed any {strokeLabel} clips yet. Review some clips, then
          come back to see how this rule matches them.
        </p>
      );
    }
    if (m.fault_clips + m.fine_clips + m.unmeasured.length === 0) {
      return (
        <p className="text-text-muted">
          You reviewed {m.reviewed_clips} {strokeLabel} {clips(m.reviewed_clips)} but
          didn&apos;t answer &ldquo;{question}&rdquo; with yes or no for any of them.
        </p>
      );
    }
    const suggestion = m.suggested;
    const showSuggestion =
      suggestion && suggestion.steps_from_choice !== 0 && keptChoice !== suggestion.picture_id;

    return (
      <>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-text-soft">
            You reviewed {m.reviewed_clips} {strokeLabel} {clips(m.reviewed_clips)} and said
            &ldquo;{question}&rdquo; in {m.fault_clips}.
          </p>
          <span
            className={`rounded-full border px-3 py-1 text-[13px] ${STATUS_CLASSES[m.agreement_status]}`}
          >
            {agreementLabels[m.agreement_status]}
          </span>
        </div>

        <ul className="flex flex-col gap-3">
          {m.fault_clips > 0 && (
            <Line ok={m.missed === 0}>
              <strong>
                Catches {m.caught} of your {m.fault_clips}
              </strong>{" "}
              {noun} {clips(m.fault_clips)}
              {m.missed > 0 && (
                <>
                  {" "}
                  and <strong>misses {m.missed}</strong>
                </>
              )}
            </Line>
          )}
          {m.fine_clips > 0 && (
            <Line ok={m.false_flags === 0}>
              {m.false_flags > 0 ? (
                <>
                  <strong>
                    Also flags {m.false_flags} {clips(m.false_flags)}
                  </strong>{" "}
                  you said {m.false_flags === 1 ? "was" : "were"} fine
                </>
              ) : (
                <>Flags none of the clips you said were fine</>
              )}
            </Line>
          )}
          {m.unmeasured.length > 0 && (
            <li className="text-sm text-text-muted">
              {m.unmeasured.length} {clips(m.unmeasured.length)} couldn&apos;t be measured
              {m.unmeasured[0].reason ? ` (${m.unmeasured[0].reason})` : ""}.
            </li>
          )}
        </ul>

        {suggestion && (
          <div className="flex flex-col gap-1.5 rounded-[14px] bg-surface-2 p-3.5">
            <span className="text-sm text-text-muted">Our suggestion from your clips</span>
            {suggestion.steps_from_choice === 0 ? (
              <span>Your choice already fits your reviews best.</span>
            ) : (
              <span>
                <strong>&ldquo;{suggestion.label}&rdquo;</strong> fits your reviews better:
                catches {suggestion.caught} of {m.fault_clips}, flags {suggestion.false_flags}{" "}
                fine {clips(suggestion.false_flags)}.
              </span>
            )}
          </div>
        )}

        {m.disagreements.length > 0 && (
          <div className="flex flex-col gap-3">
            <button
              type="button"
              aria-expanded={showDisagreements}
              onClick={() => setShowDisagreements((v) => !v)}
              className={buttonSecondary}
            >
              {showDisagreements ? "Hide" : "Show me"} the {m.disagreements.length}{" "}
              {clips(m.disagreements.length)} that disagree
            </button>
            {showDisagreements && (
              <ul aria-label="Clips that disagree" className="flex flex-col gap-2">
                {m.disagreements.map((d) => (
                  <li
                    key={d.analysis_id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-surface-2 px-3.5 py-2.5 text-sm"
                  >
                    <span>
                      {d.kind === "missed"
                        ? "You said yes, rule didn't flag it"
                        : "You said fine, rule flags it"}
                      <span className="text-text-muted">
                        {" "}
                        · measured {formatBoundaryValue(d.value, unit)}
                      </span>
                    </span>
                    <Link
                      href={
                        d.timestamp != null
                          ? `/analysis/${d.analysis_id}?t=${d.timestamp.toFixed(2)}`
                          : `/analysis/${d.analysis_id}`
                      }
                      className="inline-flex min-h-11 items-center font-medium"
                    >
                      Open at {formatTimestamp(d.timestamp)}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {showSuggestion && (
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className={buttonSecondary}
              onClick={() => setKeptChoice(suggestion.picture_id)}
            >
              Keep my choice
            </button>
            <button
              type="button"
              className={buttonPrimary}
              onClick={() => onUseSuggestion(suggestion.picture_id)}
            >
              Use suggestion
            </button>
          </div>
        )}
      </>
    );
  }
}

function Line({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <li
      className={`flex items-start gap-3 rounded-[14px] p-3.5 ${
        ok ? "bg-accent/10" : "bg-warn/10"
      }`}
    >
      {ok ? (
        <CheckCircleIcon className="mt-0.5 flex-none text-accent" />
      ) : (
        <WarnIcon className="mt-1.5 flex-none text-warn" />
      )}
      <span>{children}</span>
    </li>
  );
}
