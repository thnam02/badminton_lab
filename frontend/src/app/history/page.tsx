"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PageContainer } from "@/components/shell/PageContainer";
import { Card } from "@/components/ui/Card";
import { ChevronRightIcon, PlayerIcon } from "@/components/ui/icons";
import { buttonSecondary, chip, pageTitle } from "@/components/ui/styles";
import { fetchAnalyses, mediaUrl } from "@/lib/api";
import {
  cameraViewLabel,
  confidenceLabel,
  formatDate,
  issueTitleFromCode,
} from "@/lib/format";
import {
  baseScore,
  baseTrend,
  isSideView,
  mostCommonIssue,
  scoreLabel,
  strokeKind,
} from "@/lib/history";
import { BETA_SCORE_TOOLTIP } from "@/lib/scores";
import type { AnalysisSummary } from "@/lib/types";

function band(score?: number | null): string {
  if (score == null) return "—";
  if (score >= 0.75) return confidenceLabel("HIGH");
  if (score >= 0.5) return confidenceLabel("MODERATE");
  return confidenceLabel("LOW");
}

type Filter = "all" | "clear" | "smash" | "side";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "clear", label: "Clear" },
  { id: "smash", label: "Smash" },
  { id: "side", label: "Side view only" },
];

function matches(item: AnalysisSummary, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "side") return isSideView(item);
  return strokeKind(item) === filter;
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export default function HistoryPage() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    fetchAnalyses(40)
      .then(setItems)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load history")
      )
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(() => items.filter((i) => matches(i, filter)), [items, filter]);

  const compareHref = useMemo(() => {
    if (selected.length !== 2) return null;
    const [left, right] = items
      .filter((i) => selected.includes(i.analysis_id))
      .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));
    if (!left || !right) return null;
    const qs = new URLSearchParams({ left: left.analysis_id, right: right.analysis_id });
    return `/compare?${qs}`;
  }, [items, selected]);

  function toggle(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 2 ? [...prev, id] : prev
    );
  }

  const compareLabel = `Compare selected (${selected.length})`;

  return (
    <PageContainer>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <header className="flex flex-col gap-2">
          <h1 className={pageTitle}>Your strokes</h1>
          <p className="text-text-muted">
            Recent analyses on this machine. No account required. Select two to
            compare side by side.
          </p>
        </header>
        {compareHref ? (
          <Link href={compareHref} className={buttonSecondary}>
            {compareLabel}
          </Link>
        ) : (
          <button type="button" disabled className={buttonSecondary}>
            {compareLabel}
          </button>
        )}
      </div>

      {loading && (
        <p className="text-text-muted" role="status">
          Loading history…
        </p>
      )}
      {error && (
        <p className="text-danger" role="alert">
          {error}
        </p>
      )}
      {!loading && !error && items.length === 0 && (
        <Card>
          <p className="text-text-muted">
            No analyses yet. <Link href="/analyze">Analyze a stroke</Link>.
          </p>
        </Card>
      )}

      {items.length > 0 && (
        <>
          <SummaryTiles items={items} />

          <div role="group" aria-label="Filter" className="flex flex-wrap gap-2">
            {FILTERS.map((f) => {
              const on = filter === f.id;
              return (
                <button
                  key={f.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setFilter(f.id)}
                  className={`min-h-11 rounded-full px-4 text-sm transition ${
                    on
                      ? "bg-text font-semibold text-bg"
                      : "border border-border bg-surface text-text hover:border-text-muted"
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>

          {visible.length === 0 ? (
            <p className="text-text-muted" role="status">
              No analyses match this filter.
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {visible.map((item) => (
                <HistoryRow
                  key={item.analysis_id}
                  item={item}
                  checked={selected.includes(item.analysis_id)}
                  selectable={selected.includes(item.analysis_id) || selected.length < 2}
                  onToggle={() => toggle(item.analysis_id)}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </PageContainer>
  );
}

function SummaryTiles({ items }: { items: AnalysisSummary[] }) {
  const clears = items.filter((i) => strokeKind(i) === "clear").length;
  const smashes = items.filter((i) => strokeKind(i) === "smash").length;
  const breakdown = [
    clears ? plural(clears, "clear", "clears") : null,
    smashes ? plural(smashes, "smash", "smashes") : null,
  ].filter(Boolean);
  const common = mostCommonIssue(items);
  const trend = baseTrend(items);

  return (
    <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr))]">
      <Card className="flex flex-col gap-1.5 p-[22px]">
        <h2 className="text-[13px] text-text-muted">Analyses</h2>
        <p className="font-display text-[34px] font-bold leading-tight">{items.length}</p>
        {breakdown.length > 0 && (
          <p className="text-[13px] text-text-muted">{breakdown.join(" · ")}</p>
        )}
      </Card>
      {common && (
        <Card className="flex flex-col gap-1.5 p-[22px]">
          <h2 className="text-[13px] text-text-muted">Most common focus</h2>
          <p className="font-display text-[22px] font-semibold leading-snug">
            {issueTitleFromCode(common.code)}
          </p>
          <p className="text-[13px] text-text-muted">
            Came up in {common.count} of {items.length}
          </p>
        </Card>
      )}
      {trend.length >= 2 && (
        <Card className="flex flex-col gap-2.5 p-[22px]">
          <h2 className="text-[13px] text-text-muted">Base score over time</h2>
          <Sparkline values={trend} />
          <p className="text-[13px] text-text-muted">Side-view clips only</p>
        </Card>
      )}
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const w = 240;
  const h = 56;
  const pad = 6;
  const points = values.map((v, i) => {
    const x = pad + (i * (w - 2 * pad)) / (values.length - 1);
    const y = h - pad - Math.max(0, Math.min(1, v)) * (h - 2 * pad);
    return [x, y] as const;
  });
  const d = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const [lx, ly] = points[points.length - 1];
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Base score trend across ${values.length} side-view analyses: ${values
        .map((v) => scoreLabel(v))
        .join(", ")}`}
    >
      <path
        d={d}
        fill="none"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-accent"
      />
      <circle cx={lx} cy={ly} r="4" className="fill-accent" />
    </svg>
  );
}

function HistoryRow({
  item,
  checked,
  selectable,
  onToggle,
}: {
  item: AnalysisSummary;
  checked: boolean;
  selectable: boolean;
  onToggle: () => void;
}) {
  const stroke = item.stroke_type || "Forehand Smash";
  const date = formatDate(item.created_at);
  const view = cameraViewLabel(item.camera_view);
  const href = `/analysis/${item.analysis_id}`;
  const video = mediaUrl(item.pose_video_url);
  const base = baseScore(item);

  return (
    <li className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-[18px] border border-border bg-surface p-4">
      <label
        className={`flex h-11 w-11 flex-none items-center justify-center rounded-lg has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
          selectable ? "cursor-pointer hover:bg-surface-2" : "cursor-not-allowed opacity-50"
        }`}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={!selectable}
          onChange={onToggle}
          aria-label={`Select ${stroke} from ${date} for comparison`}
          className="h-5 w-5 accent-accent focus-visible:outline-none"
        />
      </label>
      <div className="flex h-[68px] w-[120px] flex-none items-center justify-center overflow-hidden rounded-[10px] border border-border bg-bg text-accent">
        {video ? (
          <video
            src={`${video}#t=0.1`}
            preload="metadata"
            muted
            playsInline
            tabIndex={-1}
            aria-hidden
            className="h-full w-full object-cover"
          />
        ) : (
          <PlayerIcon />
        )}
      </div>
      <div className="flex min-w-0 flex-[999_1_280px] flex-col">
        <div className="flex flex-wrap items-center gap-x-2.5">
          <Link
            href={href}
            className="inline-flex min-h-11 items-center font-display text-lg font-semibold text-text hover:text-accent-soft"
          >
            {stroke}
          </Link>
          <span className="text-[13px] text-text-muted">
            {[date, view, `Confidence ${band(item.analysis_confidence)}`]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
        <p className="text-sm text-text-soft">
          <span className="text-text-muted">Main finding: </span>
          {item.main_issue ? issueTitleFromCode(item.main_issue) : "None flagged"}
        </p>
      </div>
      <div className="ml-auto flex flex-wrap items-center justify-end gap-2 sm:flex-nowrap">
        <span className={chip} title={BETA_SCORE_TOOLTIP}>
          Base (Beta)&nbsp;<strong className="font-display">{scoreLabel(base)}</strong>
        </span>
        <Link
          href={href}
          aria-label={`Open ${stroke} analysis from ${date}`}
          className="flex h-11 w-11 items-center justify-center rounded-full border border-border text-text hover:border-accent hover:text-text"
        >
          <ChevronRightIcon />
        </Link>
      </div>
    </li>
  );
}
