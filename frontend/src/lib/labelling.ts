import { API_BASE } from "./api";

export const COACH_NAME_KEY = "badminton-lab.coach-name";

export type StatRating = "good" | "needs_work" | "looks_wrong";

export type ClipStat = {
  id: string;
  name: string;
  description: string;
  when: string;
  unit: string;
  value: number | null;
  available: boolean;
};

export type LabellingClip = {
  analysis_id: string;
  video_url: string | null;
  raw_video_url: string | null;
  overlay_video_url: string | null;
  stroke_type: string;
  stroke_label: string;
  handedness: string | null;
  camera_view: string | null;
  system_contact_frame: number | null;
  system_contact_timestamp: number | null;
  fps: number | null;
  frame_count: number | null;
  stats: ClipStat[];
  rating_options: { id: StatRating; label: string; hint?: string }[];
  overall_ratings: { value: number; label: string }[];
};

export type ClipStatus = "not_started" | "in_progress" | "done";

export type BatchClipSummary = {
  position: number;
  analysis_id: string;
  source_file: string;
  stroke_type?: string;
  missing: boolean;
  status: ClipStatus;
  labelled: boolean;
  coach_count: number;
};

export type LabellingBatch = {
  batch_id: string;
  name: string;
  created_at: string;
  coach: string | null;
  total: number;
  labelled_count: number;
  clips: BatchClipSummary[];
};

export type StatLabel = { rating: StatRating | null; comment: string };

export type LabelDraft = {
  corrected_hit_frame: number | null;
  stats: Record<string, StatLabel>;
  overall_rating: number | null;
  feedback: string;
};

export type SavedLabel = LabelDraft & {
  label_format_version: string;
  analysis_id: string;
  batch_id: string | null;
  coach: string;
  system_contact_frame: number | null;
  created_at: string;
  updated_at: string;
};

export const EMPTY_DRAFT: LabelDraft = {
  corrected_hit_frame: null,
  stats: {},
  overall_rating: null,
  feedback: "",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export function fetchBatch(batchId: string, coach: string): Promise<LabellingBatch> {
  const qs = new URLSearchParams({ coach });
  return request(`/labelling/batches/${encodeURIComponent(batchId)}?${qs}`);
}

export function fetchClip(analysisId: string): Promise<LabellingClip> {
  return request(`/labelling/clips/${encodeURIComponent(analysisId)}`);
}

export function fetchClipLabel(
  analysisId: string,
  coach: string
): Promise<{ label: SavedLabel | null; status: ClipStatus }> {
  const qs = new URLSearchParams({ coach });
  return request(`/labelling/clips/${encodeURIComponent(analysisId)}/label?${qs}`);
}

export function saveClipLabel(
  analysisId: string,
  body: LabelDraft & { coach: string; batch_id: string }
): Promise<{ label: SavedLabel; status: ClipStatus }> {
  return request(`/labelling/clips/${encodeURIComponent(analysisId)}/label`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function exportUrl(batchId: string, format: "csv" | "json"): string {
  return `${API_BASE}/labelling/batches/${encodeURIComponent(batchId)}/export?format=${format}`;
}

export function formatStatValue(value: number | null, unit: string): string {
  if (value == null || Number.isNaN(value)) return "Not measured";
  if (unit === "deg") return `${Math.round(value)}°`;
  if (unit === "torso_lengths_above_shoulder") {
    const v = Math.abs(value).toFixed(2);
    return `${v} torso lengths ${value < 0 ? "below" : "above"} the shoulder`;
  }
  if (unit === "torso_lengths_per_s") return `${value.toFixed(1)} torso lengths per second`;
  if (unit === "ratio") return value.toFixed(2);
  return `${value.toFixed(2)} ${unit}`.trim();
}

/** Frame shown at a playback time, with frame i spanning [i/fps, (i+1)/fps). */
export function frameAt(seconds: number, fps: number): number {
  return Math.max(0, Math.floor(seconds * fps + 1e-6));
}

/** Seek target for a frame: its middle, so the browser shows that frame. */
export function timeOfFrame(frame: number, fps: number): number {
  return (frame + 0.5) / fps;
}
