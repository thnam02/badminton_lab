"use client";

import { useState } from "react";
import { buttonSecondary, detailsSummary, eyebrow } from "@/components/ui/styles";
import { formatPercentile, confidenceLabel } from "@/lib/format";
import {
  coachingCopyForIssue,
  findingSeverityLabel,
  formatConfidencePct,
  formatEvidenceValue,
  formatPlayerMeasurement,
  phaseChipLabel,
  playerIssueTitle,
  TENTATIVE_HINT_NOTE,
} from "@/lib/techniqueCopy";
import type { TechniqueIssueView } from "@/lib/types";

type Variant = "main" | "compact" | "insufficient";

type Props = {
  issue: TechniqueIssueView;
  variant?: Variant;
  active?: boolean;
  fps?: number | null;
  onShowMoment?: (issue: TechniqueIssueView) => void;
};

export function TechniqueIssueCard({
  issue,
  variant,
  active,
  fps,
  onShowMoment,
}: Props) {
  const mode: Variant =
    variant ||
    (issue.is_insufficient_evidence ? "insufficient" : "compact");

  if (mode === "insufficient" || issue.is_insufficient_evidence) {
    return <InsufficientCard issue={issue} active={active} />;
  }

  if (mode === "main") {
    return (
      <MainFocusCard
        issue={issue}
        active={active}
        fps={fps}
        onShowMoment={onShowMoment}
      />
    );
  }

  return (
    <CompactFindingCard
      issue={issue}
      active={active}
      fps={fps}
      onShowMoment={onShowMoment}
    />
  );
}

const activeRing = "ring-2 ring-accent ring-offset-2 ring-offset-bg";

function InsufficientCard({
  issue,
  active,
}: {
  issue: TechniqueIssueView;
  active?: boolean;
}) {
  return (
    <article
      className={`flex flex-col gap-2 rounded-[18px] border border-dashed border-text-muted/40 bg-surface p-5 ${
        active ? activeRing : ""
      }`}
      aria-label="Unable to assess reliably"
    >
      <p className={eyebrow}>Unable to assess reliably</p>
      <h3 className="font-display text-lg font-semibold text-text">
        {playerIssueTitle(issue.code)}
      </h3>
      <p className="text-sm leading-relaxed text-text-soft">
        {issue.status_reason ||
          "We could not measure this part of the stroke with enough confidence to give coaching advice."}
      </p>
      <p className="text-xs text-text-muted">
        {phaseChipLabel(issue.phase_label)} · not counted as a technique fault
      </p>
    </article>
  );
}

function MainFocusCard({
  issue,
  active,
  fps,
  onShowMoment,
}: {
  issue: TechniqueIssueView;
  active?: boolean;
  fps?: number | null;
  onShowMoment?: (issue: TechniqueIssueView) => void;
}) {
  const copy = coachingCopyForIssue(issue);
  const plainMeasure = formatPlayerMeasurement(issue, fps);

  return (
    <article
      aria-label="Main focus"
      className={`flex flex-col gap-6 rounded-card border border-border bg-surface p-6 sm:p-8 ${
        active ? activeRing : ""
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-2">
          <p className={eyebrow}>Your main focus</p>
          <h2 className="font-display text-[26px] font-bold leading-tight tracking-[-0.01em] text-text sm:text-[30px]">
            {copy.title}
          </h2>
          <p className="text-sm text-text-muted">
            {phaseChipLabel(issue.phase_label)} · {findingSeverityLabel(issue)}
          </p>
          {issue.tentative && <TentativeBadge />}
        </div>
        {issue.seek_timestamp != null && onShowMoment && (
          <button
            type="button"
            onClick={() => onShowMoment(issue)}
            className={buttonSecondary}
          >
            Show this moment
          </button>
        )}
      </div>

      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr))]">
        <FocusTile label="What we saw" body={copy.whatHappened}>
          {plainMeasure !== "—" && (
            <p className="text-sm text-text-muted">
              In plain terms: <span className="text-text">{plainMeasure}</span>
            </p>
          )}
        </FocusTile>
        <FocusTile label="Why it matters" body={copy.whyItMatters} />
        <FocusTile label="Try next" body={copy.coachingFocus} />
      </div>

      <EvidenceDetails issue={issue} />
    </article>
  );
}

function CompactFindingCard({
  issue,
  active,
  fps,
  onShowMoment,
}: {
  issue: TechniqueIssueView;
  active?: boolean;
  fps?: number | null;
  onShowMoment?: (issue: TechniqueIssueView) => void;
}) {
  const [open, setOpen] = useState(false);
  const copy = coachingCopyForIssue(issue);
  const plainMeasure = formatPlayerMeasurement(issue, fps);

  return (
    <article
      className={`rounded-[18px] border border-border bg-surface ${
        active ? activeRing : ""
      }`}
    >
      <button
        type="button"
        className="flex min-h-11 w-full items-start justify-between gap-3 rounded-[18px] px-5 py-4 text-left"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <div className="min-w-0">
          <h3 className="font-display text-base font-semibold text-text">{copy.title}</h3>
          <p className="mt-1 text-xs text-text-muted">
            {phaseChipLabel(issue.phase_label)} · {findingSeverityLabel(issue)}
          </p>
          {issue.tentative && <TentativeBadge />}
        </div>
        <span className="mt-0.5 shrink-0 text-sm font-medium text-accent">
          {open ? "Hide" : "Details"}
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-3 border-t border-border px-5 py-4">
          <CopyBlock label="What we saw" body={copy.whatHappened} />
          {plainMeasure !== "—" && (
            <p className="text-sm text-text-muted">
              In plain terms: <span className="text-text">{plainMeasure}</span>
            </p>
          )}
          <CopyBlock label="Why it matters" body={copy.whyItMatters} />
          <CopyBlock label="Try next" body={copy.coachingFocus} />
          {issue.seek_timestamp != null && onShowMoment && (
            <button
              type="button"
              onClick={() => onShowMoment(issue)}
              className={`${buttonSecondary} self-start`}
            >
              Show this moment
            </button>
          )}
          <EvidenceDetails issue={issue} />
        </div>
      )}
    </article>
  );
}

function FocusTile({
  label,
  body,
  children,
}: {
  label: string;
  body: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-[14px] bg-surface-2 p-5">
      <h3 className="font-display font-semibold text-accent-soft">{label}</h3>
      <p className="text-text-soft">{body}</p>
      {children}
    </div>
  );
}

function TentativeBadge() {
  return (
    <span
      className="inline-flex self-start rounded-full border border-dashed border-text-muted/40 px-2 py-0.5 text-[11px] font-medium text-text-muted"
      title={TENTATIVE_HINT_NOTE}
    >
      Tentative hint
    </span>
  );
}

function CopyBlock({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <h4 className="font-display text-sm font-semibold text-accent-soft">{label}</h4>
      <p className="mt-1 text-sm leading-relaxed text-text-soft">{body}</p>
    </div>
  );
}

function EvidenceDetails({ issue }: { issue: TechniqueIssueView }) {
  const combined = issue.combined_confidence ?? issue.confidence ?? null;

  return (
    <details className="border-t border-border pt-2">
      <summary className={detailsSummary}>View evidence</summary>
      {issue.tentative && <p className="pt-2 text-sm text-text-soft">{TENTATIVE_HINT_NOTE}</p>}
      <dl className="grid gap-x-6 gap-y-3 pt-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
        <EvidenceItem label="Measured value">
          {formatEvidenceValue(issue.measured_value, issue.unit)}
        </EvidenceItem>
        {issue.tier != null && (
          <EvidenceItem label="Rule tier">
            {issue.tier === 1 ? "Tier 1 (principle)" : "Tier 2 (side-view hint)"}
          </EvidenceItem>
        )}
        <EvidenceItem label="Reference median">
          {formatEvidenceValue(issue.reference_median, issue.unit)}
        </EvidenceItem>
        <EvidenceItem label="Reference range">
          {formatEvidenceValue(issue.reference_low, issue.unit)} –{" "}
          {formatEvidenceValue(issue.reference_high, issue.unit)}
        </EvidenceItem>
        <EvidenceItem label="Percentile vs reference">
          {formatPercentile(issue.reference_percentile) || "—"}
        </EvidenceItem>
        <EvidenceItem label="Confidence">
          {confidenceLabel(issue.confidence_label)} ({formatConfidencePct(combined)})
        </EvidenceItem>
        <div className="sm:col-span-2 lg:col-span-3">
          <dt className="text-text-muted">Reference profile</dt>
          <dd className="break-all font-mono text-xs text-text">
            {issue.reference_profile_id || "—"}
          </dd>
        </div>
      </dl>
    </details>
  );
}

function EvidenceItem({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-text-muted">{label}</dt>
      <dd className="font-display text-xl font-bold text-text">{children}</dd>
    </div>
  );
}
