import { API_BASE } from "./api";

export type StatRating = "good" | "needs_work" | "looks_wrong" | "cant_see";

export type MomentId = "preparation" | "contact" | "follow_through";

export type ReviewQuestion = {
  id: string;
  title: string;
  hint: string;
  moment: MomentId;
  moment_title: string;
  /** "measured" questions show the app's value; "coach_only" ones are judged by eye. */
  kind: "measured" | "coach_only";
  unit: string | null;
  value: number | null;
  available: boolean;
  measured_at: { label: string; frame: number | null } | null;
  /** Keypoints this question looks at; highlighted on the overlay. */
  joints: string[];
  rating_options: { id: StatRating; label: string; hint?: string }[];
};

export type ReviewMoment = { id: MomentId; title: string; frame: number | null };

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
  moments: ReviewMoment[];
  questions: ReviewQuestion[];
  fix_options: { id: string; title: string }[];
  overall_ratings: { value: number; label: string }[];
};

export type ClipStatus = "not_started" | "in_progress" | "done";

export type Technique = "FOREHAND_CLEAR" | "FOREHAND_SMASH";

export type DatasetStatus = "not_started" | "in_progress" | "done" | "overdue";

/** A numbered set of 5–10 videos of one technique, with the coach's progress. */
export type DatasetSummary = {
  dataset_id: string;
  /** Null only for batches made before datasets existed and not yet migrated. */
  technique: Technique | null;
  technique_label: string;
  number: number | null;
  title: string;
  note: string;
  created_at: string;
  /** ISO date (YYYY-MM-DD), or null for older batches. */
  due_date: string | null;
  /** Negative once overdue. */
  days_left: number | null;
  /** Includes uploaded videos still being analysed. */
  video_count: number;
  processing_count: number;
  labelled_count: number;
  status: DatasetStatus;
  /** Same as dataset_id; older screens and labels call it batch_id. */
  batch_id: string;
  name: string;
  clip_count: number;
};

export type DatasetClip = {
  position: number;
  analysis_id: string;
  source_file: string;
  stroke_type?: string;
  handedness?: string | null;
  camera_view?: string | null;
  missing: boolean;
  status: ClipStatus;
  labelled: boolean;
};

export type DatasetDetail = DatasetSummary & {
  coach: string;
  /** Videos ready to label (excludes ones still processing). */
  total: number;
  clips: DatasetClip[];
  uploads: UploadJob[];
};

export type StatLabel = { rating: StatRating | null; comment: string };

export type LabelDraft = {
  corrected_hit_frame: number | null;
  stats: Record<string, StatLabel>;
  overall_rating: number | null;
  /** A question id, or "not_listed". */
  most_important_fix: string | null;
  /** What the coach would tell the player. */
  feedback: string;
  /** Anything else, e.g. about the video or the measurements. */
  general_comment: string;
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
  most_important_fix: null,
  feedback: "",
  general_comment: "",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    credentials: "include",
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

/** Every dataset with Jeff's progress: overdue first, then nearest due date. */
export async function fetchDatasets(): Promise<DatasetSummary[]> {
  const data = await request<{ datasets: DatasetSummary[] }>("/labelling/datasets");
  return data.datasets || [];
}

export type UploadClipStatus = "queued" | "processing" | "done" | "failed";

export type UploadJob = {
  job_id: string;
  batch_id: string;
  batch_name: string;
  stroke_type: string;
  handedness: string;
  camera_view: string;
  status: "running" | "done" | "interrupted";
  clips: {
    source_file: string;
    status: UploadClipStatus;
    analysis_id: string | null;
    error: string | null;
    handedness: string | null;
    camera_view: string | null;
  }[];
  total: number;
  done_count: number;
  failed_count: number;
  remaining_count: number;
};

export type DatasetVideoInput = { file: File; handedness: string; cameraView: string };

export type DatasetInput = {
  technique: Technique;
  /** YYYY-MM-DD */
  dueDate: string;
  note: string;
  videos: DatasetVideoInput[];
  /** Analyses that already exist, added without processing. */
  existingIds: string[];
};

export type CreatedDataset = { dataset: DatasetSummary; job: UploadJob | null };

/** Create a dataset; XHR so upload progress (0–1) can be shown. */
export function createDataset(
  input: DatasetInput,
  onProgress?: (fraction: number) => void
): Promise<CreatedDataset> {
  const form = new FormData();
  form.append("technique", input.technique);
  form.append("due_date", input.dueDate);
  form.append("note", input.note);
  for (const v of input.videos) {
    form.append("files", v.file);
    form.append("handedness", v.handedness);
    form.append("camera_view", v.cameraView);
  }
  for (const id of input.existingIds) form.append("existing_ids", id);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/labelling/datasets`);
    xhr.withCredentials = true;
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as CreatedDataset);
      } else {
        const detail = xhr.response?.detail;
        reject(new Error(typeof detail === "string" ? detail : `Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed: could not reach the server."));
    xhr.send(form);
  });
}

export function fetchUploadJob(jobId: string): Promise<UploadJob> {
  return request(`/labelling/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchDataset(datasetId: string): Promise<DatasetDetail> {
  return request(`/labelling/datasets/${encodeURIComponent(datasetId)}`);
}

export function updateDataset(
  datasetId: string,
  body: { due_date?: string; note?: string }
): Promise<DatasetSummary> {
  return request(`/labelling/datasets/${encodeURIComponent(datasetId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
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

export function exportUrl(datasetId: string, format: "csv" | "json"): string {
  return `${API_BASE}/labelling/datasets/${encodeURIComponent(datasetId)}/export?format=${format}`;
}

export function formatStatValue(value: number | null, unit: string | null): string {
  if (value == null || Number.isNaN(value)) return "Not measured";
  switch (unit) {
    case "deg":
      return `${Math.round(value)}°`;
    case "yes_no":
      return value >= 0.5 ? "Yes" : "No";
    case "torso_lengths_above_shoulder":
      return `${Math.abs(value).toFixed(2)} ${value < 0 ? "below" : "above"}`;
    case "torso_lengths_per_s":
      return `${value.toFixed(1)} torso/s`;
    case "ratio":
      return value.toFixed(2);
    default:
      return `${value.toFixed(2)}${unit ? ` ${unit}` : ""}`;
  }
}

/** Longer wording for screen readers and tooltips. */
export function describeStatValue(value: number | null, unit: string | null): string {
  if (value == null || Number.isNaN(value)) return "Not measured";
  if (unit === "torso_lengths_above_shoulder") {
    return `${Math.abs(value).toFixed(2)} torso lengths ${value < 0 ? "below" : "above"} the shoulder`;
  }
  if (unit === "torso_lengths_per_s") return `${value.toFixed(1)} torso lengths per second`;
  return formatStatValue(value, unit);
}

/** Frame shown at a playback time, with frame i spanning [i/fps, (i+1)/fps). */
export function frameAt(seconds: number, fps: number): number {
  return Math.max(0, Math.floor(seconds * fps + 1e-6));
}

/** Seek target for a frame: its middle, so the browser shows that frame. */
export function timeOfFrame(frame: number, fps: number): number {
  return (frame + 0.5) / fps;
}
