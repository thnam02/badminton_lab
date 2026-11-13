"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SessionGate } from "@/components/auth/SessionGate";
import { DueText, ProgressBar, StatusPill } from "@/components/datasets/DatasetBits";
import { pageTitle } from "@/components/ui/styles";
import { groupByTechnique, sortForCoach } from "@/lib/datasets";
import { fetchDatasets, type DatasetSummary } from "@/lib/labelling";

export function CoachHome() {
  return <SessionGate>{(me) => <Home coach={me.name} />}</SessionGate>;
}

function Home({ coach }: { coach: string }) {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDatasets()
      .then((d) => !cancelled && setDatasets(d))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load"));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className={pageTitle}>Hi {coach}</h1>
        <p className="text-lg text-text-muted">Your datasets to label, most urgent first.</p>
      </header>

      {error ? (
        <p className="text-lg text-danger" role="alert">
          {error}
        </p>
      ) : !datasets ? (
        <p className="text-text-muted" role="status">
          Loading datasets…
        </p>
      ) : (
        groupByTechnique(sortForCoach(datasets)).map((section) => (
          <section key={section.id} aria-labelledby={`tech-${section.id}`} className="flex flex-col gap-3">
            <h2 id={`tech-${section.id}`} className="font-display text-2xl font-semibold">
              {section.label}
            </h2>
            {section.datasets.length === 0 ? (
              <p className="text-lg text-text-muted">Nothing to label yet.</p>
            ) : (
              <ul
                aria-label={`${section.label} datasets`}
                className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
              >
                {section.datasets.map((d) => (
                  <li key={d.dataset_id}>
                    <DatasetCard dataset={d} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))
      )}
    </div>
  );
}

function DatasetCard({ dataset: d }: { dataset: DatasetSummary }) {
  return (
    <Link
      href={`/coach/datasets/${d.dataset_id}`}
      className={`flex h-full flex-col gap-3 rounded-[18px] border bg-surface px-5 py-4 text-text hover:text-text ${
        d.status === "overdue" ? "border-danger/70 hover:border-danger" : "border-border hover:border-accent"
      }`}
    >
      <span className="flex items-start justify-between gap-3">
        <span className="font-display text-xl font-semibold">{d.title}</span>
        <StatusPill status={d.status} />
      </span>
      <span className="text-base text-text-muted">
        {d.video_count} {d.video_count === 1 ? "video" : "videos"} · {d.labelled_count} labelled
        {d.processing_count > 0 && ` · ${d.processing_count} being prepared`}
      </span>
      <ProgressBar dataset={d} label={`${d.title}: videos labelled`} />
      <span className="text-base">
        <DueText dataset={d} />
      </span>
    </Link>
  );
}
