"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BoundaryPicture } from "@/components/coach/BoundaryPicture";
import { RuleMatchPanel } from "@/components/coach/RuleMatchPanel";
import { Card } from "@/components/ui/Card";
import { buttonPrimary, inputBase } from "@/components/ui/styles";
import {
  COACH_NAME_KEY,
  checkCoachRule,
  fetchRuleOptions,
  saveCoachRule,
  type RuleCheck,
  type RuleDraft,
  type RuleOptions,
} from "@/lib/coach";

const STROKES = [
  { id: "FOREHAND_CLEAR", label: "Clear" },
  { id: "FOREHAND_SMASH", label: "Smash" },
];

const MOMENT_ICONS: Record<string, string> = {
  preparation: "M28 15v18M28 33l-8 18M28 33l8 18M28 20l-9 8M28 20l9 6",
  backswing_end: "M28 17v16M28 33l-8 18M28 33l8 18M28 21l-9 6M28 21l8-4l-2-10",
  contact: "M26 19v16M26 35l-8 16M26 35l8 16M26 23l-9 6M26 23l6-12l2-10",
  follow_through: "M28 17v16M28 33l-8 18M28 33l8 18M28 21l-10 10M28 21l-6 14",
};

const CHECK_DEBOUNCE_MS = 250;

const choice =
  "flex cursor-pointer border-2 font-semibold transition has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent";
const choiceOn = "border-accent bg-accent/10";
const choiceOff = "border-border bg-surface-2 hover:border-text-muted/50";
const choiceDisabled = "cursor-not-allowed border-border bg-surface-2 opacity-50";

export function CoachRuleBuilder() {
  const [options, setOptions] = useState<RuleOptions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [coach, setCoach] = useState("");
  const [stroke, setStroke] = useState(STROKES[0].id);
  const [moment, setMoment] = useState("contact");
  const [part, setPart] = useState("elbow");
  const [boundaryBySet, setBoundaryBySet] = useState<Record<string, string>>({});
  const [importance, setImportance] = useState("worth_fixing");
  const [message, setMessage] = useState("");
  const [check, setCheck] = useState<RuleCheck | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<RuleDraft | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setCoach(window.localStorage.getItem(COACH_NAME_KEY) ?? "");
    fetchRuleOptions()
      .then(setOptions)
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Could not load"));
  }, []);

  const target = useMemo(
    () => options?.targets.find((t) => t.body_part === part && t.moment === moment) ?? null,
    [options, part, moment]
  );
  const boundarySet = target ? options?.boundary_sets[target.boundary_set] : undefined;
  const pictures = boundarySet?.pictures ?? [];
  const boundaryId = target
    ? boundaryBySet[target.boundary_set] ?? pictures[Math.floor(pictures.length / 2)]?.id
    : undefined;

  useEffect(() => {
    if (!options) return;
    setCheck(null);
    if (!coach.trim() && target) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      checkCoachRule({
        coach,
        stroke_type: stroke,
        moment,
        body_part: part,
        boundary_id: boundaryId ?? "",
      })
        .then((result) => {
          if (!cancelled) setCheck(result);
        })
        .catch((err) => {
          if (!cancelled) {
            setCheck({
              supported: false,
              reason: err instanceof Error ? err.message : "Could not check this rule.",
            });
          }
        });
    }, CHECK_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [options, coach, stroke, moment, part, boundaryId, target]);

  useEffect(() => {
    setSaved(null);
    setSaveError(null);
  }, [coach, stroke, moment, part, boundaryId, importance, message]);

  const strokeLabel = STROKES.find((s) => s.id === stroke)?.label.toLowerCase() ?? "";
  const mustFixAllowed =
    check?.supported === true && check.match.agreement_status === "separates_well";
  const importanceBlocked = importance === "must_fix_first" && !mustFixAllowed;
  const saveBlockedReason = !coach.trim()
    ? "Add your name to save this rule."
    : !target
      ? "This rule can't be saved because we have no measurement for it."
      : importanceBlocked
        ? '"Must fix first" needs a rule that separates well on your reviewed clips.'
        : null;

  function chooseBoundary(id: string) {
    if (target) setBoundaryBySet((prev) => ({ ...prev, [target.boundary_set]: id }));
  }

  async function save() {
    if (!target || !boundaryId) return;
    setSaving(true);
    setSaveError(null);
    try {
      setSaved(
        await saveCoachRule({
          coach,
          stroke_type: stroke,
          moment,
          body_part: part,
          boundary_id: boundaryId,
          importance,
          message,
        })
      );
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save this rule.");
    } finally {
      setSaving(false);
    }
  }

  if (loadError) {
    return (
      <Card role="alert">
        <p className="text-danger">Could not load the rule builder: {loadError}</p>
      </Card>
    );
  }
  if (!options) {
    return (
      <p className="text-text-muted" role="status">
        Loading rule builder…
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-start gap-7 text-[17px]">
      <div className="flex min-w-0 flex-[999_1_640px] flex-col gap-6">
        <Card className="flex flex-col gap-3">
          <label className="flex flex-col gap-2 font-semibold">
            Your name
            <input
              type="text"
              value={coach}
              autoComplete="name"
              placeholder="e.g. Linh"
              onChange={(e) => {
                setCoach(e.target.value);
                window.localStorage.setItem(COACH_NAME_KEY, e.target.value);
              }}
              className={`${inputBase} max-w-sm font-normal`}
            />
          </label>
          <p className="text-[15px] text-text-muted">
            We compare your rule with the clips you reviewed under this name.
          </p>
        </Card>

        <Card className="flex flex-col gap-4">
          <Step n={1}>Which stroke and which moment?</Step>
          <fieldset className="flex flex-wrap gap-2">
            <legend className="sr-only">Stroke</legend>
            {STROKES.map((s) => (
              <label
                key={s.id}
                className={`${choice} items-center gap-2 rounded-[14px] px-[18px] py-3.5 ${
                  stroke === s.id ? choiceOn : choiceOff
                }`}
              >
                <input
                  type="radio"
                  name="stroke"
                  checked={stroke === s.id}
                  onChange={() => setStroke(s.id)}
                  className="h-5 w-5 accent-accent focus-visible:outline-none"
                />
                {s.label}
              </label>
            ))}
          </fieldset>
          <fieldset className="grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(130px,1fr))]">
            <legend className="sr-only">Moment</legend>
            {options.moments.map((m) => {
              const on = moment === m.id;
              return (
                <label
                  key={m.id}
                  className={`${choice} flex-col items-center gap-1.5 rounded-[14px] p-3.5 ${
                    on ? choiceOn : choiceOff
                  }`}
                >
                  <input
                    type="radio"
                    name="moment"
                    checked={on}
                    onChange={() => setMoment(m.id)}
                    className="sr-only"
                  />
                  <svg width="56" height="56" viewBox="0 0 56 56" fill="none" aria-hidden="true">
                    <circle
                      cx={m.id === "contact" ? 26 : 28}
                      cy={m.id === "preparation" ? 10 : m.id === "contact" ? 14 : 12}
                      r="5"
                      className={on ? "stroke-accent" : "stroke-text-soft"}
                      strokeWidth="2.5"
                    />
                    <path
                      d={MOMENT_ICONS[m.id]}
                      className={on ? "stroke-accent" : "stroke-text-soft"}
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />
                  </svg>
                  {m.label}
                </label>
              );
            })}
          </fieldset>
        </Card>

        <Card className="flex flex-col gap-4">
          <Step n={2}>Which part of the body?</Step>
          <fieldset className="flex flex-wrap gap-2">
            <legend className="sr-only">Body part</legend>
            {options.body_parts.map((p) => (
              <label
                key={p.id}
                className={`${choice} items-center gap-2 rounded-[14px] px-[18px] py-3.5 ${
                  part === p.id ? choiceOn : choiceOff
                }`}
              >
                <input
                  type="radio"
                  name="part"
                  checked={part === p.id}
                  onChange={() => setPart(p.id)}
                  className="h-5 w-5 accent-accent focus-visible:outline-none"
                />
                {p.label}
              </label>
            ))}
          </fieldset>
        </Card>

        <Card className="flex flex-col gap-4">
          <Step n={3}>{target ? target.prompt : "Where is the boundary?"}</Step>
          {target && boundarySet ? (
            <>
              <p className="text-text-muted">{target.flag_hint}</p>
              <fieldset className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(110px,1fr))]">
                <legend className="sr-only">{target.prompt}</legend>
                {pictures.map((p) => {
                  const on = boundaryId === p.id;
                  return (
                    <label
                      key={p.id}
                      className={`${choice} flex-col items-center gap-1.5 rounded-2xl px-2 py-3.5 text-center text-base ${
                        on ? choiceOn : choiceOff
                      }`}
                    >
                      <input
                        type="radio"
                        name="boundary"
                        value={p.id}
                        checked={on}
                        onChange={() => chooseBoundary(p.id)}
                        className="sr-only"
                      />
                      <BoundaryPicture set={target.boundary_set} value={p.value} selected={on} />
                      {p.label}
                    </label>
                  );
                })}
              </fieldset>
              <p className="text-[13px] text-text-muted">
                Measured as: {target.metric_label}.
              </p>
            </>
          ) : (
            <p className="text-warn" role="status">
              {check && !check.supported
                ? check.reason
                : "We don't have a measurement for this combination yet."}
            </p>
          )}
        </Card>

        <Card className="flex flex-col gap-4">
          <Step n={4}>How important is this?</Step>
          <fieldset className="grid grid-cols-3 gap-2">
            <legend className="sr-only">Importance</legend>
            {options.importance.map((opt) => {
              const disabled = opt.id === "must_fix_first" && !mustFixAllowed;
              const on = importance === opt.id;
              return (
                <label
                  key={opt.id}
                  className={`${choice} min-h-[60px] items-center justify-center rounded-[14px] px-2 text-center ${
                    disabled ? choiceDisabled : on ? choiceOn : choiceOff
                  }`}
                >
                  <input
                    type="radio"
                    name="importance"
                    checked={on}
                    disabled={disabled}
                    onChange={() => setImportance(opt.id)}
                    className="sr-only"
                  />
                  {opt.label}
                </label>
              );
            })}
          </fieldset>
          {!mustFixAllowed && (
            <p className="text-[15px] text-text-muted">
              &ldquo;Must fix first&rdquo; opens once this rule separates well on at least 5
              faulty and 5 good clips you reviewed.
            </p>
          )}
          <label className="flex flex-col gap-2 font-semibold">
            What would you tell the player? (optional)
            <textarea
              rows={2}
              maxLength={500}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Reach up and hit at the top of your reach, slightly in front."
              className="resize-y rounded-[14px] border border-border bg-surface-2 p-3 font-normal text-text"
            />
          </label>
        </Card>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <p id="save-hint" className="max-w-[460px] text-[15px] text-text-muted">
            {saveBlockedReason ??
              "Your rule goes to the team as a draft. It never changes players' results until the team promotes it."}
          </p>
          <button
            type="button"
            onClick={() => void save()}
            disabled={Boolean(saveBlockedReason) || saving}
            aria-describedby="save-hint"
            className={`${buttonPrimary} px-7 py-3 text-base`}
          >
            {saving ? "Saving…" : "Send to the team as a draft"}
          </button>
        </div>
        {saved && (
          <p className="text-accent-soft" role="status">
            Saved as a draft for the team.{" "}
            <Link href="/coach/studio" className="font-medium">
              See it in the Rule studio
            </Link>
          </p>
        )}
        {saveError && (
          <p className="text-danger" role="alert">
            {saveError}
          </p>
        )}
      </div>

      <aside
        aria-label="Check against your clips"
        className="flex min-w-0 flex-[1_1_380px] flex-col gap-4"
      >
        <RuleMatchPanel
          key={`${stroke}-${moment}-${part}`}
          check={check}
          coach={coach}
          strokeLabel={strokeLabel}
          unit={boundarySet?.unit ?? ""}
          agreementLabels={options.agreement_labels}
          onUseSuggestion={chooseBoundary}
        />
        <p className="px-1.5 text-[15px] text-text-muted">
          Picture boundaries are starting guesses, not validated values. Your reviews decide
          which one fits.
        </p>
      </aside>
    </div>
  );
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-3 font-display text-[22px] font-bold">
      <span
        aria-hidden
        className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-accent text-lg text-bg"
      >
        {n}
      </span>
      <span>
        <span className="sr-only">Step {n}: </span>
        {children}
      </span>
    </h2>
  );
}
