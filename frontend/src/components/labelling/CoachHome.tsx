"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SessionGate } from "@/components/auth/SessionGate";
import { Card } from "@/components/ui/Card";
import { ChevronRightIcon } from "@/components/ui/icons";
import { pageTitle } from "@/components/ui/styles";
import { fetchBatches, type BatchSummary } from "@/lib/labelling";

export function CoachHome() {
  return (
    <SessionGate>{(me) => <BatchList coach={me.name} />}</SessionGate>
  );
}

function BatchList({ coach }: { coach: string }) {
  const [batches, setBatches] = useState<BatchSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setBatches(null);
    fetchBatches(coach)
      .then((b) => !cancelled && setBatches(b))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load"));
    return () => {
      cancelled = true;
    };
  }, [coach]);

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-2">
        <h1 className={pageTitle}>Hi {coach}</h1>
        <p className="text-lg text-text-muted">Clips waiting for your review.</p>
      </header>

      {error ? (
        <p className="text-lg text-danger" role="alert">
          {error}
        </p>
      ) : !batches ? (
        <p className="text-text-muted" role="status">
          Loading batches…
        </p>
      ) : batches.length === 0 ? (
        <Card>
          <p className="text-lg text-text-muted">
            No clips to review yet. The admin will add some for you.
          </p>
        </Card>
      ) : (
        <ul aria-label="Labelling batches" className="flex flex-col gap-3">
          {batches.map((b) => {
            const done = b.clip_count > 0 && b.labelled_count >= b.clip_count;
            const pct = b.clip_count ? Math.round((b.labelled_count / b.clip_count) * 100) : 0;
            return (
              <li key={b.batch_id}>
                <Link
                  href={`/coach/${b.batch_id}`}
                  className="flex min-h-[88px] items-center gap-5 rounded-[18px] border border-border bg-surface px-5 py-4 text-text hover:border-accent hover:text-text"
                >
                  <div className="flex min-w-0 flex-1 flex-col gap-2">
                    <span className="font-display text-xl font-semibold">{b.name}</span>
                    <span className="text-base text-text-muted">
                      {b.clip_count} {b.clip_count === 1 ? "clip" : "clips"} ·{" "}
                      {done ? "All reviewed" : `${b.labelled_count} reviewed by you`}
                    </span>
                    <span
                      role="progressbar"
                      aria-label={`${b.name}: clips reviewed`}
                      aria-valuemin={0}
                      aria-valuemax={b.clip_count}
                      aria-valuenow={b.labelled_count}
                      className="h-2.5 w-full max-w-md overflow-hidden rounded-full bg-border"
                    >
                      <span
                        className="block h-full rounded-full bg-accent"
                        style={{ width: `${pct}%` }}
                      />
                    </span>
                  </div>
                  <span className="flex items-center gap-1 text-lg font-semibold text-accent">
                    {done ? "Open" : b.labelled_count > 0 ? "Continue" : "Start"}
                    <ChevronRightIcon />
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
