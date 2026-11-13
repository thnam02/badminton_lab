"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { cardTitle, pageTitle } from "@/components/ui/styles";
import { mediaUrl } from "@/lib/api";
import {
  fetchClip,
  fetchClipLabel,
  fetchDataset,
  formatStatValue,
  type DatasetDetail,
  type LabellingClip,
  type SavedLabel,
} from "@/lib/labelling";

type Loaded = { dataset: DatasetDetail; clip: LabellingClip; label: SavedLabel | null };

/** The coach's answers for one video, read-only, for the admin. */
export function LabelView({ datasetId, analysisId }: { datasetId: string; analysisId: string }) {
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchDataset(datasetId), fetchClip(analysisId), fetchClipLabel(analysisId)])
      .then(([dataset, clip, saved]) => !cancelled && setData({ dataset, clip, label: saved.label }))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load"));
    return () => {
      cancelled = true;
    };
  }, [datasetId, analysisId]);

  if (error) {
    return (
      <p className="text-lg text-danger" role="alert">
        {error}
      </p>
    );
  }
  if (!data) {
    return (
      <p className="text-text-muted" role="status">
        Loading…
      </p>
    );
  }

  const { dataset, clip, label } = data;
  const position = dataset.clips.find((c) => c.analysis_id === analysisId)?.position;
  const videoUrl = mediaUrl(clip.overlay_video_url ?? clip.video_url);
  const fix =
    label?.most_important_fix === "not_listed"
      ? "Something not listed"
      : clip.fix_options.find((o) => o.id === label?.most_important_fix)?.title;
  const overall = clip.overall_ratings.find((r) => r.value === label?.overall_rating)?.label;

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-2">
        <Link href={`/admin/datasets/${dataset.dataset_id}`} className="text-sm text-text-muted hover:text-text">
          ← {dataset.technique_label} · {dataset.title}
        </Link>
        <h1 className={pageTitle}>
          Video {position ?? "?"} of {dataset.total}
        </h1>
        <p className="text-lg text-text-muted">
          {label
            ? `Labelled by ${label.coach}, last saved ${new Date(label.updated_at).toLocaleString("en-GB", {
                day: "numeric",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              })}. Read-only.`
            : "Not labelled yet."}
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card className="flex flex-col gap-3">
          {videoUrl ? (
            <video src={videoUrl} controls playsInline className="w-full rounded-xl bg-black" />
          ) : (
            <p className="text-text-muted">Video unavailable.</p>
          )}
          <p className="text-sm text-text-muted">
            Hit frame: {label?.corrected_hit_frame ?? clip.system_contact_frame ?? "unknown"}
            {label?.corrected_hit_frame != null &&
              label.corrected_hit_frame !== clip.system_contact_frame &&
              ` (moved from ${clip.system_contact_frame ?? "none"})`}
          </p>
        </Card>

        {label && (
          <Card className="flex flex-col gap-3">
            <h2 className={cardTitle}>Overall</h2>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
              <dt className="text-text-muted">Rating</dt>
              <dd>{overall ?? "Not given"}</dd>
              <dt className="text-text-muted">Most important fix</dt>
              <dd>{fix ?? "Not given"}</dd>
              <dt className="text-text-muted">Feedback</dt>
              <dd className="whitespace-pre-wrap">{label.feedback || "—"}</dd>
              <dt className="text-text-muted">Other comments</dt>
              <dd className="whitespace-pre-wrap">{label.general_comment || "—"}</dd>
            </dl>
          </Card>
        )}
      </div>

      {label &&
        clip.moments.map((m) => {
          const questions = clip.questions.filter((q) => q.moment === m.id);
          if (questions.length === 0) return null;
          return (
            <Card key={m.id} className="flex flex-col gap-3" aria-label={m.title}>
              <h2 className={cardTitle}>{m.title}</h2>
              <ul className="flex flex-col gap-1.5">
                {questions.map((q) => {
                  const answer = label.stats[q.id];
                  const rating = q.rating_options.find((o) => o.id === answer?.rating)?.label;
                  return (
                    <li
                      key={q.id}
                      className="grid gap-x-4 gap-y-1 rounded-xl bg-surface-2 px-4 py-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]"
                    >
                      <span className="font-medium">{q.title}</span>
                      <span className="text-text-muted">
                        {q.kind === "measured" ? formatStatValue(q.value, q.unit) : "Judged by eye"}
                      </span>
                      <span className={rating ? "font-semibold" : "text-text-muted"}>
                        {rating ?? "No answer"}
                      </span>
                      {answer?.comment && (
                        <span className="whitespace-pre-wrap text-sm text-text-soft sm:col-span-3">
                          “{answer.comment}”
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          );
        })}
    </div>
  );
}
