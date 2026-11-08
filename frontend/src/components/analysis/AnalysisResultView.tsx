"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnalysisHeader } from "@/components/analysis/AnalysisHeader";
import {
  assessmentGapNote,
  LimitedViewNotice,
  TechniqueCheckSummary,
} from "@/components/analysis/AssessmentScope";
import { CoachingFocus, StrengthsCard } from "@/components/analysis/CoachingFocus";
import { CompositeScoresPanel } from "@/components/analysis/CompositeScoresPanel";
import { ConfidenceSummaryPanel } from "@/components/analysis/ConfidenceSummary";
import { DrillCard } from "@/components/analysis/DrillCard";
import { MetricsPanel } from "@/components/analysis/MetricsPanel";
import { OverlayControls } from "@/components/analysis/OverlayControls";
import { PhaseTimeline } from "@/components/analysis/PhaseTimeline";
import { ReferenceComparison } from "@/components/analysis/ReferenceComparison";
import { TechniqueIssueCard } from "@/components/analysis/TechniqueIssueCard";
import {
  VideoPlayer,
  type VideoPlayerHandle,
} from "@/components/analysis/VideoPlayer";
import { Card } from "@/components/ui/Card";
import { InfoIcon } from "@/components/ui/icons";
import { cardTitle, detailsSummary } from "@/components/ui/styles";
import { fetchAnalysis, mediaUrl } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import {
  estimateFpsFromPhases,
  splitMainAndOther,
} from "@/lib/techniqueCopy";
import type { AnalysisResult, TechniqueIssueView } from "@/lib/types";

type Props = {
  analysisId: string;
  /** Start the video here (seconds), e.g. when a coach opens a clip at its hit frame. */
  initialTime?: number;
};

const CONTACT_ESTIMATED_NOTE =
  "Contact time is estimated from your arm speed. The shuttle wasn't tracked at that moment, so it may be a few frames off.";

const autoFitGrid =
  "grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr))]";

export function AnalysisResultView({ analysisId, initialTime }: Props) {
  const [data, setData] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(initialTime ?? 0);
  const [activeIssue, setActiveIssue] = useState<string | null>(null);
  const [techOpen, setTechOpen] = useState(false);
  const videoRef = useRef<VideoPlayerHandle>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAnalysis(analysisId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load analysis");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  const seek = useCallback((seconds: number, pause = true) => {
    videoRef.current?.seekTo(seconds, { pause });
    setCurrentTime(seconds);
  }, []);

  const onShowIssue = useCallback(
    (issue: TechniqueIssueView) => {
      setActiveIssue(issue.code);
      if (issue.seek_timestamp != null) {
        seek(issue.seek_timestamp, true);
      }
    },
    [seek]
  );

  if (loading) {
    return (
      <p className="text-text-muted" role="status">
        Loading analysis…
      </p>
    );
  }

  if (error || !data) {
    return (
      <Card role="alert" className="flex flex-col gap-2">
        <h1 className="font-display text-xl font-semibold">Analysis unavailable</h1>
        <p className="text-sm text-text-muted">
          {error || "This analysis could not be found."}
        </p>
      </Card>
    );
  }

  const videoSrc = mediaUrl(data.video.pose_video_url);
  const playerSrc =
    videoSrc && initialTime != null ? `${videoSrc}#t=${initialTime.toFixed(2)}` : videoSrc;
  const findings = data.findings || [];
  const insufficient = data.insufficient_evidence || [];
  const { main, other } = splitMainAndOther(findings);
  const preferCoachingHero = Boolean(data.coaching?.available && data.coaching.main_focus);
  const showsCoaching = preferCoachingHero || !main;
  const showStrengths =
    showsCoaching && data.coaching.available && data.coaching.strengths.length > 0;
  const drill = data.coaching.drills[0];
  const fps = estimateFpsFromPhases(data.phases);
  const contactTime = data.contact.timestamp;
  const gapNote = assessmentGapNote(data.assessment_scope);

  return (
    <div className="flex flex-col gap-7">
      <AnalysisHeader analysis={data} videoUrl={videoSrc} />
      <LimitedViewNotice scope={data.assessment_scope} />

      <div className="flex flex-wrap items-stretch gap-6">
        <section
          aria-label="Video and stroke timeline"
          className="flex min-w-0 flex-[999_1_620px] flex-col overflow-hidden rounded-card border border-border bg-surface"
        >
          <div className="relative">
            <VideoPlayer
              ref={videoRef}
              src={playerSrc}
              unavailableMessage="We could not load the annotated analysis video."
              onTimeUpdate={setCurrentTime}
            />
            {videoSrc && contactTime != null && (
              <button
                type="button"
                onClick={() => seek(contactTime, true)}
                className={`absolute left-4 top-4 inline-flex min-h-11 items-center rounded-md bg-bg/85 px-3 text-xs font-semibold uppercase tracking-[0.04em] ${
                  data.contact.shuttle_verified ? "text-accent-soft" : "text-warn"
                }`}
              >
                {data.contact.shuttle_verified ? "Detected contact" : "Estimated contact"} ·{" "}
                {formatTimestamp(contactTime)}
              </button>
            )}
          </div>
          <div className="flex flex-col gap-3.5 px-6 pb-6 pt-5">
            <PhaseTimeline
              phases={data.phases}
              currentTime={currentTime}
              onSeek={(t) => seek(t, true)}
              contactTimestamp={contactTime}
              contactShuttleVerified={data.contact.shuttle_verified}
            />
            {data.contact.available && !data.contact.shuttle_verified && (
              <p className="flex items-start gap-2 text-[13px] text-text-muted">
                <InfoIcon className="mt-[3px] flex-none" />
                {CONTACT_ESTIMATED_NOTE}
              </p>
            )}
          </div>
        </section>

        <aside
          aria-label="Technique scores"
          className="flex min-w-0 flex-[1_1_340px] flex-col gap-4"
        >
          <CompositeScoresPanel scores={data.composite_scores} />
        </aside>
      </div>

      {preferCoachingHero ? (
        <CoachingFocus
          coaching={data.coaching}
          onSeek={(t) => seek(t, true)}
          assessmentGapNote={gapNote}
        />
      ) : main ? (
        <TechniqueIssueCard
          issue={main}
          variant="main"
          active={activeIssue === main.code}
          fps={fps}
          onShowMoment={onShowIssue}
        />
      ) : (
        <CoachingFocus
          coaching={data.coaching}
          onSeek={(t) => seek(t, true)}
          assessmentGapNote={gapNote}
        />
      )}

      <TechniqueCheckSummary scope={data.assessment_scope} findingsCount={findings.length} />

      <SecondaryFindings
        other={preferCoachingHero ? findings.filter((f) => f.code !== data.coaching.main_focus?.issue_code) : other}
        insufficient={insufficient}
        activeIssue={activeIssue}
        fps={fps}
        onShowMoment={onShowIssue}
      />

      {(showStrengths || drill) && (
        <div className={autoFitGrid}>
          {showStrengths && <StrengthsCard strengths={data.coaching.strengths} />}
          {drill && <DrillCard drill={drill} />}
        </div>
      )}

      {data.reference_comparisons.length > 0 && (
        <section aria-labelledby="reference-comparison" className="flex flex-col gap-3">
          <h2 id="reference-comparison" className={cardTitle}>
            Reference comparison
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {data.reference_comparisons.map((ref) => (
              <ReferenceComparison
                key={`${ref.metric_id}-${ref.title}`}
                data={ref}
                profileHint={data.reference_profile_id}
              />
            ))}
          </div>
        </section>
      )}

      <div className={autoFitGrid}>
        <MetricsPanel metrics={data.metrics} displayMetrics={data.display_metrics} />
        <ConfidenceSummaryPanel
          confidence={data.confidence}
          limitations={data.limitations}
        />
      </div>

      <details
        className="rounded-card border border-border bg-surface px-6 py-2"
        open={techOpen}
        onToggle={(e) => setTechOpen((e.target as HTMLDetailsElement).open)}
      >
        <summary className={`${detailsSummary} font-semibold`}>
          Technical details
        </summary>
        <div className="flex flex-col gap-6 pb-4 pt-2">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-text-muted">Analysis ID</dt>
              <dd className="break-all font-mono text-xs text-text">{data.analysis_id}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Reference profile</dt>
              <dd className="break-all font-mono text-xs text-text">
                {data.reference_profile_id || "—"}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted">Analysis status</dt>
              <dd>{data.analysis_status}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Coaching status</dt>
              <dd>{data.coaching_status}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Contact</dt>
              <dd>
                {data.contact.shuttle_verified
                  ? "Detected contact (shuttle-verified)"
                  : "Estimated contact (not verified by shuttle)"}
              </dd>
            </div>
          </dl>

          <div className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold text-text">Overlays</h3>
            <OverlayControls modes={data.video.overlay_modes || []} />
          </div>
        </div>
      </details>
    </div>
  );
}

function SecondaryFindings({
  other,
  insufficient,
  activeIssue,
  fps,
  onShowMoment,
}: {
  other: TechniqueIssueView[];
  insufficient: TechniqueIssueView[];
  activeIssue: string | null;
  fps: number | null;
  onShowMoment: (issue: TechniqueIssueView) => void;
}) {
  if (other.length === 0 && insufficient.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-7">
      {other.length > 0 && (
        <section aria-labelledby="other-findings" className="flex flex-col gap-3">
          <h2 id="other-findings" className={cardTitle}>
            Other findings
          </h2>
          <div className="grid items-start gap-3 lg:grid-cols-2">
            {other.map((issue) => (
              <TechniqueIssueCard
                key={issue.code}
                issue={issue}
                variant="compact"
                active={activeIssue === issue.code}
                fps={fps}
                onShowMoment={onShowMoment}
              />
            ))}
          </div>
        </section>
      )}

      {insufficient.length > 0 && (
        <section aria-labelledby="unable-to-assess" className="flex flex-col gap-3">
          <div>
            <h2 id="unable-to-assess" className={cardTitle}>
              Unable to assess reliably
            </h2>
            <p className="mt-1 text-sm text-text-muted">
              These are confidence limits, not technique faults.
            </p>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {insufficient.map((issue) => (
              <TechniqueIssueCard
                key={`ie-${issue.code}`}
                issue={issue}
                variant="insufficient"
                active={activeIssue === issue.code}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
