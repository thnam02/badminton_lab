import type { DatasetSummary } from "@/lib/labelling";

/** A forehand clear dataset summary as the API returns it. */
export function summary(overrides: Partial<DatasetSummary> = {}): DatasetSummary {
  const number = overrides.number ?? 1;
  const id = overrides.dataset_id ?? `clear-${number}`;
  return {
    dataset_id: id,
    batch_id: id,
    technique: "FOREHAND_CLEAR",
    technique_label: "Forehand clear",
    number,
    title: `Dataset ${number}`,
    name: `Forehand clear · Dataset ${number}`,
    note: "",
    created_at: "2026-11-01T10:00:00+00:00",
    due_date: "2026-11-20",
    days_left: 10,
    video_count: 8,
    processing_count: 0,
    labelled_count: 0,
    clip_count: 8,
    status: "not_started",
    ...overrides,
  };
}
