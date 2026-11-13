"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { DueText, ProgressBar, StatusPill } from "@/components/datasets/DatasetBits";
import { Card } from "@/components/ui/Card";
import { buttonPrimary, buttonSecondary, cardTitle, inputBase, pageTitle } from "@/components/ui/styles";
import {
  exportUrl,
  fetchDataset,
  updateDataset,
  type ClipStatus,
  type DatasetDetail,
} from "@/lib/labelling";

const POLL_MS = 3000;

const LABEL_STATUS: Record<ClipStatus, { label: string; className: string }> = {
  done: { label: "Labelled", className: "text-accent-soft" },
  in_progress: { label: "Started", className: "text-warn" },
  not_started: { label: "Not labelled", className: "text-text-muted" },
};

const CONTEXT: Record<string, string> = {
  RIGHT: "Right-handed",
  LEFT: "Left-handed",
  SIDE: "side view",
  FRONT: "front view",
  REAR: "view from behind",
};

/** Admin view of one dataset: videos and their labels, due date, note, export. */
export function AdminDataset({ datasetId }: { datasetId: string }) {
  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      fetchDataset(datasetId)
        .then(setDataset)
        .catch((err) => setError(err instanceof Error ? err.message : "Could not load the dataset")),
    [datasetId]
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!dataset?.processing_count) return;
    const timer = window.setTimeout(() => void load(), POLL_MS);
    return () => window.clearTimeout(timer);
  }, [dataset, load]);

  if (error && !dataset) {
    return (
      <p className="text-lg text-danger" role="alert">
        {error}
      </p>
    );
  }
  if (!dataset) {
    return (
      <p className="text-text-muted" role="status">
        Loading dataset…
      </p>
    );
  }

  const pending = dataset.uploads.flatMap((job) =>
    job.clips.filter((c) => c.status !== "done").map((c) => ({ ...c, job_id: job.job_id }))
  );

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-3">
        <Link href="/admin" className="text-sm text-text-muted hover:text-text">
          ← All datasets
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className={pageTitle}>
            {dataset.technique_label} · {dataset.title}
          </h1>
          <StatusPill status={dataset.status} />
        </div>
        <p className="text-lg">
          <DueText dataset={dataset} />
          <span className="text-text-muted">
            {" "}
            · {dataset.labelled_count} of {dataset.video_count} labelled
            {dataset.created_at &&
              ` · created ${new Date(dataset.created_at).toLocaleDateString("en-GB", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}`}
          </span>
        </p>
        <div className="max-w-md">
          <ProgressBar dataset={dataset} label="Videos labelled" />
        </div>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="flex flex-col gap-4">
          <h2 className={cardTitle}>Videos</h2>
          <ul aria-label="Videos" className="flex flex-col gap-1.5">
            {dataset.clips.map((c) => {
              const s = LABEL_STATUS[c.status];
              const context = [c.handedness, c.camera_view]
                .map((v) => (v ? CONTEXT[v] : null))
                .filter(Boolean)
                .join(", ");
              return (
                <li
                  key={c.analysis_id}
                  className="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-1 rounded-xl bg-surface-2 px-4 py-2"
                >
                  <span className="w-8 text-text-muted tabular-nums">{c.position}</span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate font-medium">
                      {c.source_file || `Video ${c.analysis_id.slice(0, 8)}`}
                    </span>
                    {context && <span className="text-[13px] text-text-muted">{context}</span>}
                  </span>
                  <span className={`text-sm font-semibold ${c.missing ? "text-danger" : s.className}`}>
                    {c.missing ? "Analysis missing" : s.label}
                  </span>
                  {!c.missing && (
                    <Link
                      href={`/admin/datasets/${dataset.dataset_id}/videos/${c.analysis_id}`}
                      className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm text-accent hover:bg-surface"
                      aria-label={`View label for video ${c.position}`}
                    >
                      View label
                    </Link>
                  )}
                </li>
              );
            })}
            {pending.map((c, i) => (
              <li
                key={`${c.job_id}-${i}`}
                className="flex min-h-14 flex-wrap items-center gap-x-4 rounded-xl border border-dashed border-border px-4 py-2"
              >
                <span className="w-8" />
                <span className="min-w-0 flex-1 truncate">{c.source_file}</span>
                <span
                  className={`text-sm font-semibold ${c.status === "failed" ? "text-danger" : "text-warn"}`}
                >
                  {c.status === "failed"
                    ? `Failed${c.error ? `: ${c.error}` : ""}`
                    : c.status === "processing"
                      ? "Analysing…"
                      : "Waiting to be analysed"}
                </span>
              </li>
            ))}
          </ul>
          {dataset.clips.length === 0 && pending.length === 0 && (
            <p className="text-text-muted">No videos in this dataset.</p>
          )}
        </Card>

        <div className="flex flex-col gap-5">
          <DetailsForm dataset={dataset} onSaved={load} />
          <Card className="flex flex-col gap-3">
            <h2 className={cardTitle}>Export labels</h2>
            <p className="text-sm text-text-muted">One row per video per question.</p>
            <div className="flex flex-wrap gap-2">
              <a href={exportUrl(dataset.dataset_id, "csv")} className={buttonSecondary}>
                Download CSV
              </a>
              <a href={exportUrl(dataset.dataset_id, "json")} className={buttonSecondary}>
                Download JSON
              </a>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function DetailsForm({ dataset, onSaved }: { dataset: DatasetDetail; onSaved: () => Promise<void> }) {
  const [due, setDue] = useState(dataset.due_date ?? "");
  const [note, setNote] = useState(dataset.note);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const changed = due !== (dataset.due_date ?? "") || note !== dataset.note;

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      await updateDataset(dataset.dataset_id, {
        ...(due !== (dataset.due_date ?? "") ? { due_date: due } : {}),
        note,
      });
      await onSaved();
      setMessage({ ok: true, text: "Saved." });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : "Could not save" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <h2 className={cardTitle}>Due date and note</h2>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (changed && due && !saving) void save();
        }}
      >
        <label className="flex flex-col gap-2 font-semibold">
          Due date
          <input
            type="date"
            value={due}
            onChange={(e) => setDue(e.target.value)}
            className={`${inputBase} font-normal`}
          />
        </label>
        <label className="flex flex-col gap-2 font-semibold">
          Note for the coach
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            className={`${inputBase} py-2 font-normal`}
          />
        </label>
        <button type="submit" disabled={!changed || !due || saving} className={buttonPrimary}>
          {saving ? "Saving…" : "Save changes"}
        </button>
        {message && (
          <p className={message.ok ? "text-accent-soft" : "text-danger"} role={message.ok ? "status" : "alert"}>
            {message.text}
          </p>
        )}
      </form>
    </Card>
  );
}
