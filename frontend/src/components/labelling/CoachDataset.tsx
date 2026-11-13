"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DueText, ProgressBar, StatusPill } from "@/components/datasets/DatasetBits";
import { Card } from "@/components/ui/Card";
import { ChevronRightIcon } from "@/components/ui/icons";
import { buttonPrimary, cardTitle, pageTitle } from "@/components/ui/styles";
import { fetchDataset, type DatasetClip, type DatasetDetail } from "@/lib/labelling";

export function labelHref(datasetId: string, position?: number): string {
  return `/coach/datasets/${datasetId}/label${position ? `?video=${position}` : ""}`;
}

function clipState(c: DatasetClip): { label: string; className: string } {
  if (c.missing) return { label: "Unavailable", className: "text-text-muted" };
  if (c.labelled) return { label: "Done", className: "text-accent-soft" };
  if (c.status === "in_progress") return { label: "Not done · started", className: "text-warn" };
  return { label: "Not done", className: "text-text-muted" };
}

/** One dataset for the coach: its videos, done or not, and where to carry on. */
export function CoachDataset({ datasetId }: { datasetId: string }) {
  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDataset(datasetId)
      .then((d) => !cancelled && setDataset(d))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load"));
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (error) {
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

  const next = dataset.clips.find((c) => !c.labelled && !c.missing);

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-3">
        <Link href="/coach" className="text-base text-text-muted hover:text-text">
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
          </span>
        </p>
        <div className="max-w-md">
          <ProgressBar dataset={dataset} label="Videos labelled" />
        </div>
      </header>

      {dataset.note && (
        <Card className="flex flex-col gap-2" aria-label="Note from the admin">
          <h2 className={cardTitle}>Note from the admin</h2>
          <p className="whitespace-pre-wrap text-lg text-text-soft">{dataset.note}</p>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-4">
        {next ? (
          <Link href={labelHref(dataset.dataset_id, next.position)} className={`${buttonPrimary} px-8 text-lg`}>
            Continue
            <ChevronRightIcon />
          </Link>
        ) : dataset.clips.length > 0 ? (
          <p className="text-lg text-accent-soft">All videos labelled. Thank you!</p>
        ) : null}
        {next && (
          <span className="text-text-muted">
            Next: video {next.position} of {dataset.clips.length}
          </span>
        )}
      </div>

      <ul aria-label="Videos" className="flex max-w-[860px] flex-col gap-2">
        {dataset.clips.map((c) => {
          const state = clipState(c);
          const row = "flex min-h-14 items-center justify-between gap-4 rounded-xl bg-surface px-5 py-2";
          return (
            <li key={c.analysis_id}>
              {c.missing ? (
                <span className={row}>
                  <span className="text-lg">Video {c.position}</span>
                  <span className={`font-semibold ${state.className}`}>{state.label}</span>
                </span>
              ) : (
                <Link
                  href={labelHref(dataset.dataset_id, c.position)}
                  className={`${row} border border-transparent text-text hover:border-accent hover:text-text`}
                >
                  <span className="text-lg">Video {c.position}</span>
                  <span className={`flex items-center gap-2 font-semibold ${state.className}`}>
                    {state.label}
                    <ChevronRightIcon />
                  </span>
                </Link>
              )}
            </li>
          );
        })}
        {dataset.processing_count > 0 && (
          <li className="flex min-h-14 items-center rounded-xl border border-dashed border-border px-5 text-text-muted">
            {dataset.processing_count} more {dataset.processing_count === 1 ? "video is" : "videos are"} being
            prepared.
          </li>
        )}
      </ul>
    </div>
  );
}
