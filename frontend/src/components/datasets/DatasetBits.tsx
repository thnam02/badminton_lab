import { formatDue, progressPercent, STATUS_LABEL, timeLeft } from "@/lib/datasets";
import type { DatasetStatus, DatasetSummary } from "@/lib/labelling";

const STATUS_CLASS: Record<DatasetStatus, string> = {
  not_started: "border-border bg-surface-2 text-text-muted",
  in_progress: "border-warn/50 bg-warn/10 text-warn",
  done: "border-accent/50 bg-accent/10 text-accent-soft",
  overdue: "border-danger/60 bg-danger/15 text-danger",
};

export function StatusPill({ status }: { status: DatasetStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1 text-[13px] font-semibold ${STATUS_CLASS[status]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

export function ProgressBar({ dataset, label }: { dataset: DatasetSummary; label: string }) {
  return (
    <span
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={dataset.video_count}
      aria-valuenow={dataset.labelled_count}
      className="block h-2.5 w-full overflow-hidden rounded-full bg-border"
    >
      <span
        className={`block h-full rounded-full ${dataset.status === "overdue" ? "bg-danger" : "bg-accent"}`}
        style={{ width: `${progressPercent(dataset)}%` }}
      />
    </span>
  );
}

/** "Due 20 Nov · 3 days left", "Due 20 Nov · Overdue" or "No due date". */
export function DueText({ dataset }: { dataset: DatasetSummary }) {
  if (!dataset.due_date) return <span className="text-text-muted">No due date</span>;
  const left = timeLeft(dataset);
  return (
    <span className={dataset.status === "overdue" ? "font-semibold text-danger" : "text-text-muted"}>
      Due {formatDue(dataset.due_date)}
      {left && ` · ${left}`}
    </span>
  );
}
