/** Pure helpers for the history page — presentation only, no new data. */

import type { AnalysisSummary } from "./types";

export type StrokeKind = "clear" | "smash";

export function strokeKind(item: AnalysisSummary): StrokeKind | null {
  const raw = String(item.stroke_type_raw || item.stroke_type || "").toUpperCase();
  if (raw.includes("CLEAR")) return "clear";
  if (raw.includes("SMASH")) return "smash";
  return null;
}

export function isSideView(item: AnalysisSummary): boolean {
  return String(item.camera_view || "").toUpperCase() === "SIDE";
}

function score(value: number | null | undefined): number | null {
  if (value == null || Number.isNaN(Number(value))) return null;
  return Number(value);
}

/** BASE score in [0, 1], or null when scores are unavailable or BASE is missing. */
export function baseScore(item: AnalysisSummary): number | null {
  if (!item.composite_scores?.available) return null;
  return score(item.composite_scores.base_score);
}

export function scoreLabel(value: number | null): string {
  return value == null ? "n/a" : String(Math.round(value * 100));
}

/** Side-view BASE scores, oldest first. */
export function baseTrend(items: AnalysisSummary[]): number[] {
  return items
    .filter((item) => isSideView(item) && baseScore(item) != null)
    .sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")))
    .map((item) => baseScore(item) as number);
}

export function mostCommonIssue(
  items: AnalysisSummary[]
): { code: string; count: number } | null {
  const counts = new Map<string, number>();
  for (const item of items) {
    if (item.main_issue) counts.set(item.main_issue, (counts.get(item.main_issue) || 0) + 1);
  }
  let best: { code: string; count: number } | null = null;
  for (const [code, count] of counts) {
    if (!best || count > best.count) best = { code, count };
  }
  return best;
}
