import type { DatasetStatus, DatasetSummary, Technique } from "./labelling";

export const TECHNIQUES: { id: Technique; label: string }[] = [
  { id: "FOREHAND_CLEAR", label: "Forehand clear" },
  { id: "FOREHAND_SMASH", label: "Forehand smash" },
];

export const MIN_VIDEOS = 5;
export const MAX_VIDEOS = 10;

export const STATUS_LABEL: Record<DatasetStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  done: "Done",
  overdue: "Overdue",
};

export function techniqueLabel(technique: string | null): string {
  return TECHNIQUES.find((t) => t.id === technique)?.label ?? "Other";
}

/** Datasets per technique, keeping the given order inside each section. */
export function groupByTechnique(
  datasets: DatasetSummary[]
): { id: Technique; label: string; datasets: DatasetSummary[] }[] {
  return TECHNIQUES.map((t) => ({ ...t, datasets: datasets.filter((d) => d.technique === t.id) }));
}

/** Overdue first, then nearest due date (no date after dated ones), finished datasets last. */
export function sortForCoach(datasets: DatasetSummary[]): DatasetSummary[] {
  const key = (d: DatasetSummary) =>
    [
      d.status === "overdue" ? 0 : 1,
      d.status === "done" ? 1 : 0,
      d.due_date ? 0 : 1,
      d.due_date ?? "",
      d.number ?? 0,
    ] as const;
  return [...datasets].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    for (let i = 0; i < ka.length; i++) {
      if (ka[i] < kb[i]) return -1;
      if (ka[i] > kb[i]) return 1;
    }
    return 0;
  });
}

/** "20 Nov" (the year is added when it isn't this year). */
export function formatDue(iso: string, today: Date = new Date()): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    ...(y !== today.getFullYear() ? { year: "numeric" } : {}),
    timeZone: "UTC",
  });
}

/** "3 days left", "Due today", "Overdue", or "" when there is nothing to say. */
export function timeLeft(d: Pick<DatasetSummary, "status" | "days_left" | "due_date">): string {
  if (d.status === "overdue") return "Overdue";
  if (d.status === "done" || d.days_left == null) return "";
  if (d.days_left <= 0) return "Due today";
  return d.days_left === 1 ? "1 day left" : `${d.days_left} days left`;
}

export function progressPercent(d: Pick<DatasetSummary, "labelled_count" | "video_count">): number {
  return d.video_count ? Math.round((d.labelled_count / d.video_count) * 100) : 0;
}
