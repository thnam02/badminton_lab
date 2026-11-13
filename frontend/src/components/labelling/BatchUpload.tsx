"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { buttonPrimary, buttonSecondary, cardTitle, inputBase, pageTitle } from "@/components/ui/styles";
import {
  createDataset,
  fetchUploadJob,
  type Technique,
  type UploadClipStatus,
  type UploadJob,
} from "@/lib/labelling";

const ACCEPTED = ".mp4,.mov,video/mp4,video/quicktime";
const POLL_MS = 2000;

const STROKES: { value: Technique; label: string }[] = [
  { value: "FOREHAND_CLEAR", label: "Forehand clear" },
  { value: "FOREHAND_SMASH", label: "Forehand smash" },
];
const HANDS = [
  { value: "RIGHT", label: "Right-handed" },
  { value: "LEFT", label: "Left-handed" },
  { value: "UNKNOWN", label: "Not sure" },
];
const VIEWS = [
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

const radioCard =
  "flex min-h-12 cursor-pointer items-center gap-2.5 rounded-xl border-2 px-4 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent";

export function BatchUpload() {
  const [due, setDue] = useState("");
  const [stroke, setStroke] = useState<Technique>(STROKES[0].value);
  const [hand, setHand] = useState(HANDS[0].value);
  const [view, setView] = useState(VIEWS[0].value);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [job, setJob] = useState<UploadJob | null>(null);
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

  function addFiles(list: FileList | null) {
    if (!list) return;
    const picked = Array.from(list).filter((f) => /\.(mp4|mov)$/i.test(f.name));
    const skipped = list.length - picked.length;
    setError(skipped ? `Skipped ${skipped} file(s) that are not .mp4 or .mov.` : null);
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      return [...prev, ...picked.filter((f) => !seen.has(`${f.name}:${f.size}`))];
    });
  }

  async function submit() {
    setError(null);
    setUploadProgress(0);
    try {
      const created = await createDataset(
        {
          technique: stroke,
          dueDate: due,
          note: "",
          videos: files.map((file) => ({ file, handedness: hand, cameraView: view })),
          existingIds: [],
        },
        setUploadProgress
      );
      setJob(created.job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploadProgress(null);
    }
  }

  if (job) return <JobProgress job={job} error={error} />;

  const uploading = uploadProgress !== null;
  const blocked = !due
    ? "Choose a due date."
    : files.length < 5 || files.length > 10
      ? `Choose 5 to 10 clips (${files.length} chosen).`
      : null;

  return (
    <div className="flex flex-col gap-7">
      <header className="flex max-w-[760px] flex-col gap-2">
        <h1 className={pageTitle}>Upload clips for review</h1>
        <p className="text-lg text-text-muted">
          Each clip is analysed on the server (about a minute each), then appears in the batch
          for coaches to review.
        </p>
      </header>

      <form
        className="flex max-w-[860px] flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (!blocked && !uploading) void submit();
        }}
      >
        <Card className="flex flex-col gap-4">
          <label className="flex flex-col gap-2 font-semibold">
            Due date
            <input
              type="date"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              className={`${inputBase} font-normal`}
            />
          </label>
        </Card>

        <Card className="flex flex-col gap-4">
          <h2 className={cardTitle}>Clips</h2>
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              addFiles(e.dataTransfer.files);
            }}
            className={`flex min-h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-8 text-center has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
              dragging ? "border-accent bg-accent/10" : "border-text-muted/40 bg-bg hover:border-accent"
            }`}
          >
            <span className="font-semibold">Drop clips here or choose files</span>
            <span className="text-[13px] text-text-muted">
              MP4 or MOV, 5 to 10 clips. One stroke per clip works best.
            </span>
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
          {files.length > 0 && (
            <ul aria-label="Chosen clips" className="flex flex-col gap-1.5">
              {files.map((f) => (
                <li
                  key={`${f.name}:${f.size}`}
                  className="flex min-h-12 items-center justify-between gap-3 rounded-xl bg-surface-2 px-3.5"
                >
                  <span className="truncate">{f.name}</span>
                  <span className="flex items-center gap-3 text-sm text-text-muted">
                    {(f.size / (1024 * 1024)).toFixed(1)} MB
                    <button
                      type="button"
                      onClick={() => setFiles((prev) => prev.filter((x) => x !== f))}
                      aria-label={`Remove ${f.name}`}
                      className="min-h-12 rounded-lg px-3 text-text hover:bg-surface"
                    >
                      Remove
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="flex flex-col gap-5">
          <h2 className={cardTitle}>About these clips</h2>
          <p className="-mt-3 text-sm text-text-muted">Applies to every clip in this batch.</p>
          <Choice
            legend="Stroke"
            name="stroke"
            options={STROKES}
            value={stroke}
            onChange={(v) => setStroke(v as Technique)}
          />
          <Choice legend="Which hand holds the racket?" name="hand" options={HANDS} value={hand} onChange={setHand} />
          <Choice legend="Where was the camera?" name="view" options={VIEWS} value={view} onChange={setView} />
        </Card>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <p id="upload-hint" className="text-[15px] text-text-muted" role="status">
            {uploading
              ? `Uploading… ${Math.round((uploadProgress ?? 0) * 100)}%`
              : blocked ?? `${files.length} ${files.length === 1 ? "clip" : "clips"} ready to upload.`}
          </p>
          <button
            type="submit"
            disabled={Boolean(blocked) || uploading}
            aria-describedby="upload-hint"
            className={`${buttonPrimary} px-7 py-3 text-base`}
          >
            {uploading ? "Uploading…" : "Upload and start processing"}
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

function Choice({
  legend,
  name,
  options,
  value,
  onChange,
}: {
  legend: string;
  name: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 font-semibold">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <label
            key={o.value}
            className={`${radioCard} ${
              value === o.value ? "border-accent bg-accent/10" : "border-border bg-surface-2"
            }`}
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              className="h-[18px] w-[18px] accent-accent"
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function JobProgress({ job, error }: { job: UploadJob; error: string | null }) {
  const finished = job.done_count + job.failed_count;
  const pct = job.total ? Math.round((finished / job.total) * 100) : 0;
  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-2">
        <h1 className={pageTitle}>{job.batch_name}</h1>
        <p className="text-lg text-text-muted" role="status" aria-live="polite">
          {job.status === "done"
            ? `Finished: ${job.done_count} of ${job.total} clips ready${
                job.failed_count ? `, ${job.failed_count} failed` : ""
              }.`
            : job.status === "interrupted"
              ? `Processing stopped because the server restarted. ${job.remaining_count} clip(s) didn't run; upload them again as a new batch.`
              : `Analysing clips: ${finished} of ${job.total} finished. You can leave this page; processing continues on the server.`}
        </p>
      </header>

      <div
        role="progressbar"
        aria-label="Clips processed"
        aria-valuemin={0}
        aria-valuemax={job.total}
        aria-valuenow={finished}
        className="h-3 w-full max-w-xl overflow-hidden rounded-full bg-border"
      >
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>

      <ul aria-label="Clip progress" className="flex max-w-[860px] flex-col gap-1.5">
        {job.clips.map((c, i) => {
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
        {job.done_count > 0 && (
          <Link href={`/coach/${job.batch_id}`} className={buttonPrimary}>
            Open batch
          </Link>
        )}
        <Link href="/coach" className={buttonSecondary}>
          All batches
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
