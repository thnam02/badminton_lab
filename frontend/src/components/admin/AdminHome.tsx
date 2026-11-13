"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DueText, ProgressBar, StatusPill } from "@/components/datasets/DatasetBits";
import { Card } from "@/components/ui/Card";
import { buttonPrimary, cardTitle, pageTitle } from "@/components/ui/styles";
import { groupByTechnique } from "@/lib/datasets";
import { fetchDatasets, type DatasetSummary } from "@/lib/labelling";

/** Every dataset per technique, with the coach's progress and due dates. */
export function AdminHome() {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDatasets()
      .then(setDatasets)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load datasets"));
  }, []);

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-2">
          <h1 className={pageTitle}>Datasets</h1>
          <p className="text-lg text-text-muted">Videos the coach labels, grouped by technique.</p>
        </div>
        <Link href="/admin/datasets/new" className={buttonPrimary}>
          Create dataset
        </Link>
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
        groupByTechnique(datasets).map((section) => (
          <Card key={section.id} className="flex flex-col gap-4" aria-labelledby={`tech-${section.id}`}>
            <h2 id={`tech-${section.id}`} className={cardTitle}>
              {section.label}
            </h2>
            {section.datasets.length === 0 ? (
              <p className="text-text-muted">No datasets yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] border-separate border-spacing-y-1.5 text-left">
                  <thead className="text-xs uppercase tracking-[0.06em] text-text-muted">
                    <tr>
                      <th className="px-3 font-semibold">Dataset</th>
                      <th className="px-3 font-semibold">Videos</th>
                      <th className="px-3 font-semibold">Labelled</th>
                      <th className="px-3 font-semibold">Due</th>
                      <th className="px-3 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {section.datasets.map((d) => (
                      <DatasetRow key={d.dataset_id} dataset={d} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        ))
      )}
    </div>
  );
}

function DatasetRow({ dataset: d }: { dataset: DatasetSummary }) {
  const overdue = d.status === "overdue";
  const cell = `px-3 py-3 ${overdue ? "bg-danger/10" : "bg-surface-2"}`;
  return (
    <tr data-status={d.status}>
      <td className={`${cell} rounded-l-xl ${overdue ? "border-l-4 border-danger" : ""}`}>
        <Link href={`/admin/datasets/${d.dataset_id}`} className="font-semibold text-text hover:text-accent">
          {d.title}
        </Link>
        {d.processing_count > 0 && (
          <span className="ml-2 text-sm text-warn">{d.processing_count} processing</span>
        )}
      </td>
      <td className={cell}>{d.video_count}</td>
      <td className={`${cell} w-[28%]`}>
        <span className="flex items-center gap-3">
          <span className="whitespace-nowrap tabular-nums">
            {d.labelled_count}/{d.video_count}
          </span>
          <ProgressBar dataset={d} label={`${d.title}: videos labelled`} />
        </span>
      </td>
      <td className={cell}>
        <DueText dataset={d} />
      </td>
      <td className={`${cell} rounded-r-xl`}>
        <StatusPill status={d.status} />
      </td>
    </tr>
  );
}
