import { API_BASE } from "./api";

export type Option = { id: string; label: string };

export type BoundaryPictureData = { id: string; label: string; value: number };

export type BoundarySetData = { unit: string; pictures: BoundaryPictureData[] };

export type RuleTargetData = {
  body_part: string;
  moment: string;
  metric_id: string;
  metric_label: string;
  boundary_set: string;
  direction: "flag_below" | "flag_above";
  label_question: string;
  label_question_title: string;
  prompt: string;
  flag_hint: string;
  problem_noun: string;
};

export type AgreementStatus = "separates_well" | "overlaps" | "not_enough_data";

export type RuleOptions = {
  moments: Option[];
  body_parts: Option[];
  boundary_sets: Record<string, BoundarySetData>;
  targets: RuleTargetData[];
  importance: (Option & { severity_cap: string })[];
  agreement_labels: Record<AgreementStatus, string>;
};

export type MatchCounts = {
  caught: number;
  missed: number;
  false_flags: number;
  fine_not_flagged: number;
  balanced_accuracy: number | null;
};

export type Disagreement = {
  analysis_id: string;
  kind: "missed" | "false_flag";
  value: number;
  frame_index: number | null;
  timestamp: number | null;
};

export type RuleMatch = MatchCounts & {
  reviewed_clips: number;
  answered_clips: number;
  unanswered_clips: number;
  fault_clips: number;
  fine_clips: number;
  unmeasured: { analysis_id: string; reason: string | null }[];
  agreement_status: AgreementStatus;
  suggested:
    | (MatchCounts & {
        picture_id: string;
        label: string;
        value: number;
        steps_from_choice: number;
      })
    | null;
  disagreements: Disagreement[];
};

export type RuleCheck =
  | { supported: false; reason: string }
  | {
      supported: true;
      stroke_type: string;
      target: Omit<RuleTargetData, "body_part" | "moment">;
      boundary: BoundaryPictureData;
      match: RuleMatch;
    };

export type CoachRuleInput = {
  coach: string;
  stroke_type: string;
  moment: string;
  body_part: string;
  boundary_id: string;
  importance?: string | null;
  message?: string;
};

export type RuleDraft = {
  id: string;
  coach: string;
  title: string;
  stroke_type: string;
  stroke_label: string;
  moment: string;
  body_part: string;
  metric_id: string;
  metric_label: string;
  direction: string;
  boundary: BoundaryPictureData & { unit: string };
  importance: string;
  severity_cap: string;
  message: string;
  agreement: MatchCounts & {
    status: AgreementStatus;
    fault_clips: number;
    fine_clips: number;
  };
  status: string;
  promoted_rule_version: string | null;
  created_at: string;
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

export function fetchRuleOptions(): Promise<RuleOptions> {
  return request("/coach/rule-options");
}

export function checkCoachRule(rule: CoachRuleInput): Promise<RuleCheck> {
  return request("/coach/rules/check", { method: "POST", body: JSON.stringify(rule) });
}

export function saveCoachRule(rule: CoachRuleInput): Promise<RuleDraft> {
  return request("/coach/rules/drafts", { method: "POST", body: JSON.stringify(rule) });
}

export async function fetchRuleDrafts(): Promise<RuleDraft[]> {
  const data = await request<{ drafts: RuleDraft[] }>("/coach/rules/drafts");
  return data.drafts || [];
}

export const COACH_NAME_KEY = "badminton-lab.coach-name";

export const SEVERITY_LABELS: Record<string, string> = {
  MINOR: "Minor",
  MODERATE: "Moderate",
  MAJOR: "Major",
};

/** Measured value in plain units, e.g. "135°" or "0.35 torso lengths above the shoulder". */
export function formatBoundaryValue(value: number, unit: string): string {
  if (unit === "deg") return `${Math.round(value)}°`;
  if (unit === "torso_lengths_above_shoulder") {
    const v = Math.abs(value).toFixed(2);
    return value < 0 ? `${v} torso lengths below the shoulder` : `${v} torso lengths above the shoulder`;
  }
  return value.toFixed(2);
}

// Picture geometry. Every picture is drawn from the same value the rule uses,
// in a 100 × 120 viewBox.

type Point = { x: number; y: number };

function bendEnd(origin: Point, length: number, angleDeg: number): Point {
  // Interior angle 180° points straight up; smaller angles fold toward the left.
  const fold = ((180 - angleDeg) * Math.PI) / 180;
  return {
    x: origin.x - length * Math.sin(fold),
    y: origin.y - length * Math.cos(fold),
  };
}

export const ELBOW = { shoulder: { x: 50, y: 112 }, elbow: { x: 50, y: 70 }, forearm: 35 };

/** Hand position for an elbow drawn at this interior angle (upper arm vertical). */
export function elbowHand(angleDeg: number): Point {
  return bendEnd(ELBOW.elbow, ELBOW.forearm, angleDeg);
}

export const KNEE = { ankle: { x: 55, y: 108 }, knee: { x: 55, y: 64 }, thigh: 42 };

/** Hip position for a knee drawn at this interior angle (shin vertical). */
export function kneeHip(angleDeg: number): Point {
  return bendEnd(KNEE.knee, KNEE.thigh, angleDeg);
}

export const FIGURE = { shoulder: { x: 46, y: 62 }, torso: 30, arm: 38 };

/** Wrist position for a hand this many torso lengths above the shoulder. */
export function heightWrist(torsoLengthsAboveShoulder: number): Point {
  const dy = Math.max(
    -FIGURE.arm,
    Math.min(FIGURE.arm, torsoLengthsAboveShoulder * FIGURE.torso)
  );
  const dx = Math.sqrt(Math.max(FIGURE.arm ** 2 - dy ** 2, 0));
  return { x: FIGURE.shoulder.x + dx, y: FIGURE.shoulder.y - dy };
}
