"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import {
  buttonPrimary,
  buttonSecondary,
  cardTitle,
  inputBase,
  pageTitle,
} from "@/components/ui/styles";
import { MAX_VIDEOS, MIN_VIDEOS, TECHNIQUES } from "@/lib/datasets";
import {
  createDataset,
  fetchPickableAnalyses,
  fetchUploadJob,
  type CreatedDataset,
  type PickableAnalysis,
  type Technique,
  type UploadClipStatus,
  type UploadJob,
} from "@/lib/labelling";

const ACCEPTED = ".mp4,.mov,video/mp4,video/quicktime";
const POLL_MS = 2000;

export const HANDS = [
  { value: "RIGHT", label: "Right-handed" },
  { value: "LEFT", label: "Left-handed" },
  { value: "UNKNOWN", label: "Not sure" },
];
export const VIEWS = [
  { value: "SIDE", label: "Side" },
  { value: "FRONT", label: "Front" },
  { value: "REAR", label: "Behind" },
  { value: "UNKNOWN", label: "Not sure" },
];

const CLIP_STATUS: Record<UploadClipStatus, { label: string; className: string }> = {
  queued: { label: "Waiting", className: "text-text-muted" },
  processing: { label: "Analysing…", className: "text-warn" },
  done: { label: "Ready", className: "text-accent-soft" },
  failed: { label: "Failed", className: "text-danger" },
};

type UploadRow = { key: string; file: File; handedness: string; cameraView: string };

const radioCard =
  "flex min-h-12 cursor-pointer items-center gap-2.5 rounded-xl border-2 px-4 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent";

function todayIso(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

/** Why the form can't be sent yet, or null when it can. */
export function blockedReason(count: number, dueDate: string): string | null {
  if (count < MIN_VIDEOS) {
    const more = MIN_VIDEOS - count;
    return `Add ${more} more ${more === 1 ? "video" : "videos"} (a dataset has ${MIN_VIDEOS} to ${MAX_VIDEOS}).`;
  }
  if (count > MAX_VIDEOS) {
    const extra = count - MAX_VIDEOS;
    return `Remove ${extra} ${extra === 1 ? "video" : "videos"} (a dataset has at most ${MAX_VIDEOS}).`;
  }
  if (!dueDate) return "Choose a due date.";
  return null;
}

export function CreateDataset() {
  const [technique, setTechnique] = useState<Technique>(TECHNIQUES[0].id);
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [uploads, setUploads] = useState<UploadRow[]>([]);
  const [picked, setPicked] = useState<PickableAnalysis[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [created, setCreated] = useState<CreatedDataset | null>(null);
  const [error, setError] = useState<string | null>(null);

  const count = uploads.length + picked.length;
  const blocked = blockedReason(count, dueDate);
  const sending = uploadProgress !== null;

  function addFiles(list: FileList | null) {
    if (!list) return;
    const files = Array.from(list);
    const videos = files.filter((f) => /\.(mp4|mov)$/i.test(f.name));
    const skipped = files.length - videos.length;
    setError(skipped ? `Skipped ${skipped} file(s) that are not .mp4 or .mov.` : null);
    setUploads((prev) => {
      const seen = new Set(prev.map((r) => r.key));
      const rows = videos
        .map((file) => ({ key: `${file.name}:${file.size}`, file, handedness: "RIGHT", cameraView: "SIDE" }))
        .filter((r) => !seen.has(r.key));
      return [...prev, ...rows];
    });
  }

  function updateUpload(key: string, change: Partial<UploadRow>) {
    setUploads((prev) => prev.map((r) => (r.key === key ? { ...r, ...change } : r)));
  }

  async function submit() {
    setError(null);
    setUploadProgress(0);
    try {
      setCreated(
        await createDataset(
          {
            technique,
            dueDate,
            note,
            videos: uploads.map(({ file, handedness, cameraView }) => ({ file, handedness, cameraView })),
            existingIds: picked.map((a) => a.analysis_id),
          },
          setUploadProgress
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the dataset");
    } finally {
      setUploadProgress(null);
    }
  }

  if (created) return <Processing created={created} picked={picked} />;

  return (
    <div className="flex flex-col gap-7">
      <header className="flex max-w-[760px] flex-col gap-2">
        <Link href="/admin" className="text-sm text-text-muted hover:text-text">
          ← All datasets
        </Link>
        <h1 className={pageTitle}>Create dataset</h1>
        <p className="text-lg text-text-muted">
          {MIN_VIDEOS} to {MAX_VIDEOS} videos of one technique. New uploads run through the analysis
          pipeline (about a minute each) before the coach can label them.
        </p>
      </header>

      <form
        className="flex max-w-[900px] flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (!blocked && !sending) void submit();
        }}
      >
        <Card className="flex flex-col gap-3">
          <fieldset className="flex flex-col gap-2">
            <legend className={`${cardTitle} mb-3`}>Technique</legend>
            <div className="flex flex-wrap gap-2">
              {TECHNIQUES.map((t) => (
                <label
                  key={t.id}
                  className={`${radioCard} ${
                    technique === t.id ? "border-accent bg-accent/10" : "border-border bg-surface-2"
                  }`}
                >
                  <input
                    type="radio"
                    name="technique"
                    value={t.id}
                    checked={technique === t.id}
                    onChange={() => {
                      setTechnique(t.id);
                      setPicked([]);
                    }}
                    className="h-[18px] w-[18px] accent-accent"
                  />
                  {t.label}
                </label>
              ))}
            </div>
          </fieldset>
        </Card>

        <Card className="flex flex-col gap-4">
          <h2 className={cardTitle}>Upload new videos</h2>
          <label className="flex min-h-28 cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-text-muted/40 bg-bg px-6 py-6 text-center hover:border-accent has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent">
            <span className="font-semibold">Choose video files</span>
            <span className="text-[13px] text-text-muted">MP4 or MOV, one stroke per video.</span>
            <input
              type="file"
              multiple
              accept={ACCEPTED}
              className="sr-only"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
          {uploads.length > 0 && (
            <ul aria-label="Videos to upload" className="flex flex-col gap-2">
              {uploads.map((r) => (
                <li
                  key={r.key}
                  className="flex flex-wrap items-center gap-3 rounded-xl bg-surface-2 px-3.5 py-2.5"
                >
                  <span className="min-w-0 flex-1 truncate font-medium">{r.file.name}</span>
                  <select
                    aria-label={`Handedness for ${r.file.name}`}
                    value={r.handedness}
                    onChange={(e) => updateUpload(r.key, { handedness: e.target.value })}
                    className={`${inputBase} w-auto`}
                  >
                    {HANDS.map((h) => (
                      <option key={h.value} value={h.value}>
                        {h.label}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label={`Camera view for ${r.file.name}`}
                    value={r.cameraView}
                    onChange={(e) => updateUpload(r.key, { cameraView: e.target.value })}
                    className={`${inputBase} w-auto`}
                  >
                    {VIEWS.map((v) => (
                      <option key={v.value} value={v.value}>
                        {v.label} view
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => setUploads((prev) => prev.filter((x) => x.key !== r.key))}
                    aria-label={`Remove ${r.file.name}`}
                    className="min-h-11 rounded-lg px-3 text-text hover:bg-surface"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <ExistingPicker technique={technique} picked={picked} onChange={setPicked} />

        <Card className="flex flex-col gap-4">
          <h2 className={cardTitle}>For the coach</h2>
          <label className="flex max-w-xs flex-col gap-2 font-semibold">
            Due date
            <input
              type="date"
              min={todayIso()}
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className={`${inputBase} font-normal`}
            />
          </label>
          <label className="flex flex-col gap-2 font-semibold">
            Note (optional)
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="e.g. Focus on the elbow at the hit."
              className={`${inputBase} py-2 font-normal`}
            />
          </label>
        </Card>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <p id="create-hint" className="text-[15px] text-text-muted" role="status">
            {sending
              ? `Uploading… ${Math.round((uploadProgress ?? 0) * 100)}%`
              : `${count} of ${MIN_VIDEOS}–${MAX_VIDEOS} videos. ${blocked ?? "Ready to create."}`}
          </p>
          <button
            type="submit"
            disabled={Boolean(blocked) || sending}
            aria-describedby="create-hint"
            className={`${buttonPrimary} px-7 py-3 text-base`}
          >
            {sending ? "Uploading…" : "Create dataset"}
          </button>
        </div>
        {error && (
          <p className="text-danger" role="alert">
            {error}
          </p>
        )}
      </form>
    </div>
  );
}

function describeAnalysis(a: PickableAnalysis): string {
  const hand = HANDS.find((h) => h.value === a.handedness)?.label ?? "Handedness unknown";
  const view = VIEWS.find((v) => v.value === a.camera_view)?.label ?? "Unknown";
  const when = a.created_at ? new Date(a.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
  return [when, hand, `${view} view`].filter(Boolean).join(" · ");
}

function ExistingPicker({
  technique,
  picked,
  onChange,
}: {
  technique: Technique;
  picked: PickableAnalysis[];
  onChange: (next: PickableAnalysis[]) => void;
}) {
  const [analyses, setAnalyses] = useState<PickableAnalysis[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setAnalyses(null);
    setError(null);
    fetchPickableAnalyses(technique)
      .then((a) => !cancelled && setAnalyses(a))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load"));
    return () => {
      cancelled = true;
    };
  }, [technique]);

  const chosen = new Set(picked.map((a) => a.analysis_id));
  const label = TECHNIQUES.find((t) => t.id === technique)?.label.toLowerCase();

  return (
    <Card className="flex flex-col gap-4">
      <details>
        <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-3">
          <span className={cardTitle}>Or pick videos already analysed</span>
          <span className="text-sm text-text-muted">{picked.length} picked</span>
        </summary>
        <div className="mt-3">
          {error ? (
            <p className="text-danger" role="alert">
              {error}
            </p>
          ) : !analyses ? (
            <p className="text-text-muted">Loading…</p>
          ) : analyses.length === 0 ? (
            <p className="text-text-muted">No {label} analyses yet.</p>
          ) : (
            <ul aria-label="Analysed videos" className="flex max-h-[420px] flex-col gap-1.5 overflow-y-auto">
              {analyses.map((a) => (
                <li key={a.analysis_id}>
                  <label className="flex min-h-12 cursor-pointer items-center gap-3 rounded-xl bg-surface-2 px-3.5 py-2">
                    <input
                      type="checkbox"
                      checked={chosen.has(a.analysis_id)}
                      onChange={(e) =>
                        onChange(
                          e.target.checked
                            ? [...picked, a]
                            : picked.filter((p) => p.analysis_id !== a.analysis_id)
                        )
                      }
                      className="h-[18px] w-[18px] accent-accent"
                    />
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span>{describeAnalysis(a)}</span>
                      <span className="truncate text-[13px] text-text-muted">
                        {a.analysis_id.slice(0, 8)}
                        {a.datasets.length > 0 && ` · already in ${a.datasets.join(", ")}`}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </Card>
  );
}

function Processing({ created, picked }: { created: CreatedDataset; picked: PickableAnalysis[] }) {
  const { dataset } = created;
  const [job, setJob] = useState<UploadJob | null>(created.job);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const timer = window.setTimeout(() => {
      fetchUploadJob(job.job_id)
        .then(setJob)
        .catch((err) => setError(err instanceof Error ? err.message : "Lost track of the upload"));
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [job]);

  const total = picked.length + (job?.total ?? 0);
  const ready = picked.length + (job?.done_count ?? 0);
  const failed = job?.failed_count ?? 0;
  const status =
    !job || job.status === "done"
      ? `Finished: ${ready} of ${total} videos ready${failed ? `, ${failed} failed` : ""}.`
      : job.status === "interrupted"
        ? `Processing stopped because the server restarted; ${job.remaining_count} video(s) didn't run.`
        : `Analysing videos: ${ready + failed} of ${total} finished. You can leave this page; processing continues on the server.`;

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-2">
        <h1 className={pageTitle}>
          {dataset.technique_label} · {dataset.title}
        </h1>
        <p className="text-lg text-text-muted" role="status" aria-live="polite">
          {status}
        </p>
      </header>

      <div
        role="progressbar"
        aria-label="Videos processed"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={ready + failed}
        className="h-3 w-full max-w-xl overflow-hidden rounded-full bg-border"
      >
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${total ? Math.round(((ready + failed) / total) * 100) : 0}%` }}
        />
      </div>

      <ul aria-label="Video processing" className="flex max-w-[860px] flex-col gap-1.5">
        {picked.map((a) => (
          <li
            key={a.analysis_id}
            className="flex min-h-12 flex-wrap items-center justify-between gap-x-4 rounded-xl bg-surface px-4 py-2"
          >
            <span className="truncate">Analysed video {a.analysis_id.slice(0, 8)}</span>
            <span className="text-sm font-semibold text-accent-soft">Ready</span>
          </li>
        ))}
        {job?.clips.map((c, i) => {
          const s = CLIP_STATUS[c.status];
          return (
            <li
              key={`${i}-${c.source_file}`}
              className="flex min-h-12 flex-wrap items-center justify-between gap-x-4 rounded-xl bg-surface px-4 py-2"
            >
              <span className="truncate">{c.source_file}</span>
              <span className={`text-sm font-semibold ${s.className}`}>
                {s.label}
                {c.error ? `: ${c.error}` : ""}
              </span>
            </li>
          );
        })}
      </ul>

      <div className="flex flex-wrap gap-3">
        <Link href={`/admin/datasets/${dataset.dataset_id}`} className={buttonPrimary}>
          Open dataset
        </Link>
        <Link href="/admin" className={buttonSecondary}>
          All datasets
        </Link>
      </div>
      {error && (
        <p className="text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
