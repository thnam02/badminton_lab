"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { HitFinder } from "@/components/labelling/HitFinder";
import { StatRatingCard } from "@/components/labelling/StatRatingCard";
import { Card } from "@/components/ui/Card";
import { mediaUrl } from "@/lib/api";
import {
  COACH_NAME_KEY,
  EMPTY_DRAFT,
  exportUrl,
  fetchBatch,
  fetchClip,
  fetchClipLabel,
  saveClipLabel,
  type LabelDraft,
  type LabellingBatch,
  type LabellingClip,
  type StatLabel,
} from "@/lib/labelling";

const AUTOSAVE_DELAY_MS = 800;

type SaveState = "idle" | "saving" | "saved" | "error";

type Props = { batchId: string };

export function LabellingWorkspace({ batchId }: Props) {
  const [coach, setCoach] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState("");

  useEffect(() => {
    const saved = window.localStorage.getItem(COACH_NAME_KEY) ?? "";
    setCoach(saved.trim() ? saved : "");
    setNameInput(saved);
  }, []);

  if (coach === null) {
    return (
      <p className="text-text-muted" role="status">
        Loading…
      </p>
    );
  }

  if (!coach.trim()) {
    return (
      <Card className="flex max-w-xl flex-col gap-4">
        <h2 className="font-display text-2xl font-bold">Before you start</h2>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            const name = nameInput.trim();
            if (!name) return;
            window.localStorage.setItem(COACH_NAME_KEY, name);
            setCoach(name);
          }}
        >
          <label className="flex flex-col gap-2 text-lg font-semibold">
            Your name
            <input
              type="text"
              autoComplete="name"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              className="min-h-14 rounded-[14px] border border-border bg-surface-2 px-4 text-lg font-normal text-text"
            />
          </label>
          <button
            type="submit"
            disabled={!nameInput.trim()}
            className="min-h-14 rounded-2xl bg-accent px-6 text-lg font-bold text-bg disabled:opacity-40"
          >
            Start reviewing
          </button>
        </form>
      </Card>
    );
  }

  return (
    <Workspace
      batchId={batchId}
      coach={coach}
      onChangeCoach={() => {
        window.localStorage.removeItem(COACH_NAME_KEY);
        setCoach("");
      }}
    />
  );
}

function Workspace({
  batchId,
  coach,
  onChangeCoach,
}: {
  batchId: string;
  coach: string;
  onChangeCoach: () => void;
}) {
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
    setDirty(false);
    setSaveState("idle");
    Promise.all([fetchClip(currentId), fetchClipLabel(currentId, coach)])
      .then(([c, saved]) => {
        if (cancelled) return;
        setClip(c);
        setDraft(
          saved.label
            ? {
                corrected_hit_frame: saved.label.corrected_hit_frame,
                stats: saved.label.stats,
                overall_rating: saved.label.overall_rating,
                feedback: saved.label.feedback,
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
        <p className="text-base text-text-muted">
          Reviewing as <strong className="text-text">{coach}</strong>{" "}
          <button
            type="button"
            onClick={onChangeCoach}
            className="ml-1 inline-flex min-h-12 items-center rounded-lg px-2 text-base text-accent hover:bg-surface-2"
          >
            Not you?
          </button>
        </p>
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

  return (
    <div className="flex flex-col gap-7">
      {header}
      <p className="text-xl text-text-soft">
        Watch the stroke, then rate what the app measured. There are no right answers to aim
        for: just tell us what you see.
      </p>

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
        <div className="flex flex-wrap items-start gap-7">
          <section
            aria-label="Step 1: find the hit"
            className="flex min-w-0 flex-[999_1_560px] flex-col gap-4 lg:sticky lg:top-4"
          >
            <StepHeading n={1}>Find the moment the racket hits the shuttle</StepHeading>
            <p className="text-base text-text-muted">
              {clip.stroke_label}
              {current?.source_file ? ` · ${current.source_file}` : ""}
              {clip.camera_view ? ` · ${clip.camera_view.toLowerCase()} view` : ""}
              {clip.handedness ? ` · ${clip.handedness.toLowerCase()}-handed` : ""}
            </p>
            <HitFinder
              videoUrl={mediaUrl(clip.video_url)}
              overlayUrl={mediaUrl(clip.overlay_video_url)}
              fps={clip.fps ?? 30}
              frameCount={clip.frame_count ?? 1}
              systemFrame={clip.system_contact_frame}
              hitFrame={draft.corrected_hit_frame}
              onMarkHit={(f) =>
                update({ corrected_hit_frame: f === clip.system_contact_frame ? null : f })
              }
              onUseSystemHit={() => update({ corrected_hit_frame: null })}
            />
          </section>

          <div className="flex min-w-0 flex-[1_1_400px] flex-col gap-7">
            <section aria-label="Step 2: rate the measurements" className="flex flex-col gap-3.5">
              <StepHeading n={2}>How do these look?</StepHeading>
              {clip.stats.map((stat) => (
                <StatRatingCard
                  key={stat.id}
                  stat={stat}
                  options={clip.rating_options}
                  value={draft.stats[stat.id]}
                  onChange={(v) => setStat(stat.id, v)}
                />
              ))}
            </section>

            <section aria-label="Step 3: overall" className="flex flex-col gap-3.5">
              <StepHeading n={3}>Overall, how good was this stroke?</StepHeading>
              <fieldset className="grid grid-cols-5 gap-2">
                <legend className="sr-only">Overall rating</legend>
                {clip.overall_ratings.map((r) => {
                  const on = draft.overall_rating === r.value;
                  return (
                    <label
                      key={r.value}
                      className={`flex min-h-[76px] cursor-pointer flex-col items-center justify-center rounded-[14px] border-2 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${
                        on ? "border-accent bg-accent/10" : "border-border bg-surface-2"
                      }`}
                    >
                      <input
                        type="radio"
                        name="overall"
                        checked={on}
                        onChange={() => update({ overall_rating: r.value })}
                        className="sr-only"
                      />
                      <strong className="text-2xl">{r.value}</strong>
                      <span className="text-sm text-text-muted">{r.label}</span>
                    </label>
                  );
                })}
              </fieldset>
              <label className="flex flex-col gap-2 text-lg font-semibold">
                Anything else? (optional)
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={draft.feedback}
                  onChange={(e) => update({ feedback: e.target.value })}
                  placeholder="Type or use your keyboard's microphone"
                  className="resize-y rounded-[14px] border border-border bg-surface p-3 text-lg font-normal text-text"
                />
              </label>
            </section>

            <button
              type="button"
              onClick={() => void saveAndNext()}
              disabled={saveState === "saving"}
              className="min-h-[76px] rounded-[20px] bg-accent text-xl font-bold text-bg hover:bg-accent-soft disabled:opacity-60"
            >
              Save and go to next clip →
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
          </div>
        </div>
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

function StepHeading({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-3 font-display text-2xl font-bold sm:text-[26px]">
      <span
        aria-hidden
        className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-accent text-xl text-bg"
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
