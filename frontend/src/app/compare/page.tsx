"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { PageContainer } from "@/components/shell/PageContainer";
import { Card } from "@/components/ui/Card";
import {
  buttonPrimary,
  eyebrow,
  inputBase,
  pageTitle,
} from "@/components/ui/styles";
import { fetchAnalyses, fetchCompare, mediaUrl } from "@/lib/api";
import { formatDate, formatMetric } from "@/lib/format";
import type { AnalysisSummary, CompareResponse } from "@/lib/types";

function CompareInner() {
  const params = useSearchParams();
  const leftParam = params.get("left") || "";
  const rightParam = params.get("right") || "";

  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const [left, setLeft] = useState(leftParam);
  const [right, setRight] = useState(rightParam);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAnalyses(40).then(setHistory).catch(() => setHistory([]));
  }, []);

  useEffect(() => {
    if (leftParam) setLeft(leftParam);
    if (rightParam) setRight(rightParam);
  }, [leftParam, rightParam]);

  const canCompare = Boolean(left && right && left !== right);

  async function runCompare() {
    if (!canCompare) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCompare(left, right);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Compare failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (leftParam && rightParam && leftParam !== rightParam) {
      void runCompare();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const options = useMemo(
    () =>
      history.map((h) => ({
        id: h.analysis_id,
        label: `${formatDate(h.created_at)} · ${h.stroke_type || "Stroke"}`,
      })),
    [history]
  );

  return (
    <>
      <header className="flex max-w-3xl flex-col gap-2.5">
        <h1 className={pageTitle}>Compare sessions</h1>
        <p className="text-text-muted">
          Compare two compatible local analyses. No overall improvement score.
        </p>
      </header>

      <Card className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block font-semibold">Previous</span>
          <select
            className={inputBase}
            value={left}
            onChange={(e) => setLeft(e.target.value)}
          >
            <option value="">Select analysis</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1.5 block font-semibold">Current</span>
          <select
            className={inputBase}
            value={right}
            onChange={(e) => setRight(e.target.value)}
          >
            <option value="">Select analysis</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!canCompare || loading}
          onClick={runCompare}
          className={`${buttonPrimary} sm:col-span-2 sm:justify-self-start`}
        >
          {loading ? "Comparing…" : "Compare"}
        </button>
      </Card>

      {error && (
        <p className="text-danger" role="alert">
          {error}
        </p>
      )}

      {result && !result.compatible && (
        <p className="text-warn" role="status">
          {result.compatibility_reason}
        </p>
      )}

      {result?.compatible && (
        <section className="flex flex-col gap-6">
          <div className="overflow-x-auto rounded-card border border-border bg-surface">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                <tr>
                  <th className="px-5 py-3 font-semibold">Metric</th>
                  <th className="px-5 py-3 font-semibold">Previous</th>
                  <th className="px-5 py-3 font-semibold">Current</th>
                  <th className="px-5 py-3 font-semibold">Change</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.label} className="border-b border-border last:border-0">
                    <td className="px-5 py-3 text-text-soft">{row.label}</td>
                    {row.unavailable_note ? (
                      <td colSpan={3} className="px-5 py-3 text-text-muted">
                        {row.unavailable_note}
                      </td>
                    ) : (
                      <>
                        <td className="px-5 py-3">
                          {row.left == null ? "n/a" : formatMetric(row.left, row.unit, 2)}
                        </td>
                        <td className="px-5 py-3">
                          {row.right == null ? "n/a" : formatMetric(row.right, row.unit, 2)}
                        </td>
                        <td className="px-5 py-3 font-medium">{row.change}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            {[result.left, result.right].map((side, idx) => (
              <Card key={side.analysis_id} as="div" className="flex flex-col gap-3">
                <p className={eyebrow}>{idx === 0 ? "Previous" : "Current"}</p>
                <Link
                  href={`/analysis/${side.analysis_id}`}
                  className="inline-flex min-h-11 items-center self-start font-medium"
                >
                  Open analysis
                </Link>
                {side.pose_video_url && (
                  <video
                    src={mediaUrl(side.pose_video_url) || undefined}
                    controls
                    className="aspect-video w-full rounded-xl bg-black"
                  />
                )}
              </Card>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

export default function ComparePage() {
  return (
    <PageContainer>
      <Suspense
        fallback={
          <p className="text-text-muted" role="status">
            Loading compare…
          </p>
        }
      >
        <CompareInner />
      </Suspense>
    </PageContainer>
  );
}
