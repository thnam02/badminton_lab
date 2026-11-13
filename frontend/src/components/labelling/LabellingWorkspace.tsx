"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SessionGate } from "@/components/auth/SessionGate";
import { HitFinder, type HitFinderHandle } from "@/components/labelling/HitFinder";
import { PoseOverlay } from "@/components/labelling/PoseOverlay";
import { QuestionCard } from "@/components/labelling/QuestionCard";
import { Card } from "@/components/ui/Card";
import { mediaUrl } from "@/lib/api";
import { fetchPose, type PoseFeed } from "@/lib/overlay";
import {
  EMPTY_DRAFT,
  exportUrl,
  fetchBatch,
  fetchClip,
  fetchClipLabel,
  saveClipLabel,
  type LabelDraft,
  type LabellingBatch,
  type LabellingClip,
  type MomentId,
  type ReviewMoment,
  type StatLabel,
} from "@/lib/labelling";

const AUTOSAVE_DELAY_MS = 800;

type SaveState = "idle" | "saving" | "saved" | "error";

type Props = { batchId: string };

export function LabellingWorkspace({ batchId }: Props) {
  return (
    <SessionGate>{(me) => <Workspace batchId={batchId} coach={me.name} />}</SessionGate>
  );
}

function Workspace({ batchId, coach }: { batchId: string; coach: string }) {
  const [batch, setBatch] = useState<LabellingBatch | null>(null);
  const [index, setIndex] = useState<number | null>(null);
  const [clip, setClip] = useState<LabellingClip | null>(null);
  const [draft, setDraft] = useState<LabelDraft>(EMPTY_DRAFT);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const editCount = useRef(0);
  const finderRef = useRef<HitFinderHandle>(null);
  const [activeMoment, setActiveMoment] = useState<MomentId>("contact");
  const [pose, setPose] = useState<PoseFeed | null>(null);
  const [showAngles, setShowAngles] = useState(true);
  const [showSkeleton, setShowSkeleton] = useState(true);

  const refreshBatch = useCallback(
    () => fetchBatch(batchId, coach).then((b) => (setBatch(b), b)),
    [batchId, coach]
  );

  useEffect(() => {
    refreshBatch()
      .then((b) => {
        const firstOpen = b.clips.findIndex((c) => !c.labelled && !c.missing);
        setIndex(firstOpen >= 0 ? firstOpen : 0);
        setFinished(firstOpen < 0 && b.total > 0);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load batch"));
  }, [refreshBatch]);

  const current = batch && index != null ? batch.clips[index] : null;
  // Batch refreshes after every save; only a different clip may reload the draft.
  const currentId = current && !current.missing ? current.analysis_id : null;

  useEffect(() => {
    if (!currentId) {
      setClip(null);
      return;
    }
    let cancelled = false;
    setClip(null);
    setPose(null);
    setDirty(false);
    setSaveState("idle");
    fetchPose(currentId)
      .then((p) => !cancelled && setPose(p))
      .catch(() => !cancelled && setPose(null));
    Promise.all([fetchClip(currentId), fetchClipLabel(currentId, coach)])
      .then(([c, saved]) => {
        if (cancelled) return;
        setClip(c);
        setActiveMoment("contact");
        // The analysed video already has the skeleton drawn in.
        setShowSkeleton(Boolean(c.raw_video_url));
        setDraft(
          saved.label
            ? {
                corrected_hit_frame: saved.label.corrected_hit_frame,
                stats: saved.label.stats,
                overall_rating: saved.label.overall_rating,
                most_important_fix: saved.label.most_important_fix ?? null,
                feedback: saved.label.feedback,
                general_comment: saved.label.general_comment ?? "",
              }
            : EMPTY_DRAFT
        );
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load clip"));
    return () => {
      cancelled = true;
    };
  }, [currentId, coach]);

  const save = useCallback(async () => {
    if (!currentId) return true;
    setSaveState("saving");
    const savedEdit = editCount.current;
    try {
      await saveClipLabel(currentId, { ...draftRef.current, coach, batch_id: batchId });
      // Edits made while saving stay dirty so the next autosave sends them.
      if (editCount.current === savedEdit) setDirty(false);
      setSaveState("saved");
      setSaveError(null);
      await refreshBatch();
      return true;
    } catch (err) {
      setSaveState("error");
      setSaveError(err instanceof Error ? err.message : "Could not save");
      return false;
    }
  }, [currentId, coach, batchId, refreshBatch]);

  useEffect(() => {
    if (!dirty) return;
    const timer = window.setTimeout(() => void save(), AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [dirty, draft, save]);

  function update(patch: Partial<LabelDraft>) {
    editCount.current += 1;
    setDraft((d) => ({ ...d, ...patch }));
    setDirty(true);
  }

  function setStat(id: string, value: StatLabel) {
    editCount.current += 1;
    setDraft((d) => ({ ...d, stats: { ...d.stats, [id]: value } }));
    setDirty(true);
  }

  async function goTo(next: number) {
    if (dirty && !(await save())) return;
    window.scrollTo({ top: 0, behavior: "smooth" });
    setIndex(next);
  }

  async function saveAndNext() {
    if (!batch || index == null) return;
    if (!(await save())) return;
    const order = [...batch.clips.keys()].map((k) => (index + 1 + k) % batch.total);
    const fresh = await refreshBatch();
    const next = order.find((i) => i !== index && !fresh.clips[i].labelled && !fresh.clips[i].missing);
    if (next === undefined) {
      setFinished(true);
      return;
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
    setIndex(next);
  }

  if (error) {
    return (
      <Card role="alert">
        <p className="text-lg text-danger">{error}</p>
      </Card>
    );
  }
  if (!batch || index == null) {
    return (
      <p className="text-text-muted" role="status">
        Loading clips…
      </p>
    );
  }

  const done = batch.labelled_count;
  const progress = batch.total ? Math.round((done / batch.total) * 100) : 0;
  const header = (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-col">
        <h1 className="font-display text-2xl font-bold sm:text-[28px]">{batch.name}</h1>
      </div>
      <div className="flex items-center gap-4">
        <div
          role="progressbar"
          aria-label="Clips reviewed"
          aria-valuemin={0}
          aria-valuemax={batch.total}
          aria-valuenow={done}
          className="h-3 w-40 overflow-hidden rounded-full bg-border sm:w-56"
        >
          <div className="h-full rounded-full bg-accent" style={{ width: `${progress}%` }} />
        </div>
        <span className="text-lg font-semibold tabular-nums">
          {finished ? `${done} of ${batch.total} done` : `Clip ${index + 1} of ${batch.total}`}
        </span>
      </div>
    </div>
  );

  if (finished) {
    return (
      <div className="flex flex-col gap-7">
        {header}
        <Card className="flex flex-col gap-4">
          <h2 className="font-display text-2xl font-bold">
            {done === batch.total ? "All clips reviewed. Thank you!" : "No more clips waiting"}
          </h2>
          <p className="text-lg text-text-soft">
            You reviewed {done} of {batch.total} clips. You can go back and change any answer.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => {
                setFinished(false);
                setIndex(0);
              }}
              className="min-h-14 rounded-2xl border-2 border-border bg-surface-2 px-6 text-lg font-semibold"
            >
              Back to clip 1
            </button>
            <a
              href={exportUrl(batch.batch_id, "csv")}
              className="inline-flex min-h-14 items-center rounded-2xl px-4 text-lg font-semibold"
            >
              Download labels (CSV)
            </a>
          </div>
        </Card>
      </div>
    );
  }

  const highlight = new Set(
    (clip?.questions ?? []).filter((q) => q.moment === activeMoment).flatMap((q) => q.joints)
  );

  function showMoment(moment: ReviewMoment) {
    setActiveMoment(moment.id);
    if (moment.frame != null) finderRef.current?.seekTo(moment.frame);
  }

  return (
    <div className="flex flex-col gap-6">
      {header}

      {current?.missing ? (
        <Card role="alert" className="flex flex-col gap-4">
          <p className="text-lg">This clip&apos;s analysis files are missing, so it can&apos;t be reviewed.</p>
          <NavButtons
            index={index}
            total={batch.total}
            onPrev={() => void goTo(index - 1)}
            onNext={() => void goTo(index + 1)}
          />
        </Card>
      ) : !clip ? (
        <p className="text-text-muted" role="status">
          Loading clip…
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-2.5">
            <h2 className="font-display text-[30px] font-bold">{clip.stroke_label}</h2>
            <span className="text-[15px] text-text-muted">
              {[
                current?.source_file,
                clip.handedness && clip.handedness !== "UNKNOWN"
                  ? `${clip.handedness.toLowerCase()}-handed`
                  : null,
                clip.camera_view && clip.camera_view !== "UNKNOWN"
                  ? `${clip.camera_view.toLowerCase()} view`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </div>

          <div className="flex flex-wrap items-start gap-6">
            <section
              aria-label="Video with angles"
              className="flex min-w-0 flex-[1_1_440px] flex-col gap-3.5 lg:sticky lg:top-4"
            >
              <div role="tablist" aria-label="Jump to a moment" className="grid grid-cols-3 gap-2">
                {clip.moments.map((m) => {
                  const on = activeMoment === m.id;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      role="tab"
                      aria-selected={on}
                      onClick={() => showMoment(m)}
                      className={`min-h-[52px] rounded-[14px] px-2 text-base ${
                        on
                          ? "bg-accent font-bold text-bg"
                          : "border-2 border-border bg-surface font-semibold text-text hover:border-text-muted/50"
                      }`}
                    >
                      {m.title}
                    </button>
                  );
                })}
              </div>
              <HitFinder
                ref={finderRef}
                videoUrl={mediaUrl(clip.video_url)}
                overlayUrl={mediaUrl(clip.overlay_video_url)}
                fps={clip.fps ?? 30}
                frameCount={clip.frame_count ?? 1}
                systemFrame={clip.system_contact_frame}
                hitFrame={draft.corrected_hit_frame}
                renderOverlay={(frame, videoSize) => (
                  <PoseOverlay
                    pose={pose}
                    frame={frame}
                    videoSize={videoSize}
                    showSkeleton={showSkeleton}
                    showAngles={showAngles}
                    highlight={highlight}
                  />
                )}
                controls={
                  <div className="flex flex-wrap gap-x-4 text-sm text-text-soft">
                    <label className="flex min-h-12 cursor-pointer items-center gap-2">
                      <input
                        type="checkbox"
                        checked={showAngles}
                        onChange={(e) => setShowAngles(e.target.checked)}
                        className="h-5 w-5 accent-accent"
                      />
                      Show angles
                    </label>
                    <label className="flex min-h-12 cursor-pointer items-center gap-2">
                      <input
                        type="checkbox"
                        checked={showSkeleton}
                        onChange={(e) => setShowSkeleton(e.target.checked)}
                        className="h-5 w-5 accent-accent"
                      />
                      Show skeleton
                    </label>
                    {!pose && (
                      <span className="flex min-h-12 items-center text-text-muted">
                        Angles unavailable for this clip.
                      </span>
                    )}
                  </div>
                }
                onMarkHit={(f) =>
                  update({ corrected_hit_frame: f === clip.system_contact_frame ? null : f })
                }
                onUseSystemHit={() => update({ corrected_hit_frame: null })}
              />
            </section>

            <form
              aria-label={`${clip.stroke_label} checklist`}
              onSubmit={(e) => e.preventDefault()}
              className="flex min-w-0 flex-[999_1_560px] flex-col gap-[22px]"
            >
              {clip.moments.map((m, i) => {
                const questions = clip.questions.filter((q) => q.moment === m.id);
                if (questions.length === 0) return null;
                const on = activeMoment === m.id;
                return (
                  <section
                    key={m.id}
                    aria-labelledby={`moment-${m.id}`}
                    className="flex flex-col gap-2.5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h3
                        id={`moment-${m.id}`}
                        className={`font-display text-[22px] font-bold ${on ? "text-accent-soft" : "text-text"}`}
                      >
                        {i + 1} · {m.title}
                      </h3>
                      <button
                        type="button"
                        onClick={() => showMoment(m)}
                        aria-label={`Show this moment: ${m.title}`}
                        className="min-h-12 rounded-full border border-border bg-surface px-3.5 text-sm text-text hover:border-text-muted/50"
                      >
                        Show this moment
                      </button>
                    </div>
                    {questions.map((q) => (
                      <QuestionCard
                        key={q.id}
                        question={q}
                        value={draft.stats[q.id]}
                        active={on}
                        onChange={(v) => setStat(q.id, v)}
                      />
                    ))}
                  </section>
                );
              })}
            </form>
          </div>

          <section
            aria-labelledby="overall-title"
            className="flex flex-col gap-4 rounded-[22px] border border-border bg-surface p-6"
          >
            <h2 id="overall-title" className="font-display text-2xl font-bold">
              Overall
            </h2>
            <fieldset className="m-0 grid grid-cols-5 gap-2 border-0 p-0">
              <legend className="mb-2 p-0 font-semibold">
                How good was this {clip.stroke_label.toLowerCase().replace(/^forehand /, "")}?
              </legend>
              {clip.overall_ratings.map((r) => {
                const on = draft.overall_rating === r.value;
                return (
                  <label
                    key={r.value}
                    className={`flex min-h-[54px] cursor-pointer items-center justify-center rounded-xl text-center has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${
                      on ? "border-[3px] border-accent bg-accent/10 font-bold" : "border-2 border-border bg-surface-2"
                    }`}
                  >
                    <input
                      type="radio"
                      name="overall"
                      checked={on}
                      onChange={() => update({ overall_rating: r.value })}
                      className="sr-only"
                    />
                    {r.label}
                  </label>
                );
              })}
            </fieldset>
            <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr))]">
              <label className="flex flex-col gap-2 font-semibold">
                Most important thing to fix
                <select
                  value={draft.most_important_fix ?? ""}
                  onChange={(e) => update({ most_important_fix: e.target.value || null })}
                  className="min-h-12 rounded-xl border border-border bg-surface-2 px-3 font-normal text-text"
                >
                  <option value="">Choose…</option>
                  {clip.fix_options.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-2 font-semibold">
                What would you tell this player?
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={draft.feedback}
                  onChange={(e) => update({ feedback: e.target.value })}
                  className="resize-y rounded-xl border border-border bg-surface-2 p-3 font-normal text-text"
                />
              </label>
            </div>
            <label className="flex flex-col gap-2 font-semibold">
              General comment (anything else, including about the video or the measurements)
              <textarea
                rows={3}
                maxLength={4000}
                value={draft.general_comment}
                onChange={(e) => update({ general_comment: e.target.value })}
                placeholder="E.g. camera is behind the player, not side-on; the angles look off"
                className="resize-y rounded-xl border border-border bg-surface-2 p-3 font-normal text-text"
              />
            </label>
            <button
              type="button"
              onClick={() => void saveAndNext()}
              disabled={saveState === "saving"}
              className="min-h-16 rounded-[18px] bg-accent text-[19px] font-bold text-bg hover:bg-accent-soft disabled:opacity-60"
            >
              Save and next clip →
            </button>
            <p className="text-center text-base text-text-muted" role="status" aria-live="polite">
              {saveState === "saving"
                ? "Saving…"
                : saveState === "error"
                  ? `Couldn't save: ${saveError}. Your answers are still here; try again.`
                  : saveState === "saved"
                    ? "Saved. Your answers save automatically; you can stop and come back any time."
                    : "Your answers save automatically. You can stop and come back any time."}
            </p>
            <NavButtons
              index={index}
              total={batch.total}
              onPrev={() => void goTo(index - 1)}
              onNext={() => void goTo(index + 1)}
            />
          </section>
        </>
      )}
    </div>
  );
}

function NavButtons({
  index,
  total,
  onPrev,
  onNext,
}: {
  index: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  const cls =
    "min-h-12 rounded-xl border-2 border-border bg-surface-2 px-4 text-base font-semibold disabled:opacity-40";
  return (
    <div className="flex justify-between gap-3">
      <button type="button" className={cls} onClick={onPrev} disabled={index <= 0}>
        ← Previous clip
      </button>
      <button type="button" className={cls} onClick={onNext} disabled={index >= total - 1}>
        Skip to next clip →
      </button>
    </div>
  );
}
