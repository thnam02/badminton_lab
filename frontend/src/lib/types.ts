/** Product-facing analysis contracts (normalized by GET /analyses/{id}). */

export type ConfidenceLevel = "HIGH" | "MODERATE" | "LOW";

export type PhaseSegment = {
  id: string;
  label: string;
  start_timestamp: number;
  end_timestamp: number;
  confidence: number;
  is_contact_event: boolean;
  seek_timestamp: number;
  start_frame_index?: number | null;
  end_frame_index?: number | null;
};

export type ContactEvent = {
  timestamp: number | null;
  frame_index: number | null;
  confidence: number;
  contact_type: string;
  label: string;
  notes?: string | null;
  /** True only when shuttle detections confirm the contact moment. */
  shuttle_verified: boolean;
  swing_count?: number | null;
  chosen_swing_timestamp?: number | null;
  warnings?: string[];
  available: boolean;
};

export type TechniqueIssueView = {
  code: string;
  title: string;
  phase: string;
  phase_label: string;
  severity?: string | null;
  status: string;
  confidence: number;
  confidence_label: ConfidenceLevel;
  measured_value?: number | null;
  unit: string;
  reference_low?: number | null;
  reference_high?: number | null;
  reference_median?: number | null;
  reference_percentile?: number | null;
  reference_profile_id: string;
  explanation: string;
  status_reason?: string;
  seek_timestamp?: number | null;
  is_finding: boolean;
  is_insufficient_evidence: boolean;
  measurement_confidence?: number | null;
  phase_confidence?: number | null;
  video_quality_confidence?: number | null;
  reference_confidence?: number | null;
  combined_confidence?: number | null;
  /** 1 = principle rule, 2 = side-view angle hint; null for retired rules. */
  tier?: number | null;
  reference_validated?: boolean | null;
  /** Tier 2 hint or judged against an unvalidated reference. */
  tentative?: boolean;
};

export type DisplayMetric = {
  id: string;
  label: string;
  value: number;
  unit: string;
  /** e.g. "Low reliability in 2D video." */
  note?: string | null;
};

/** Which checks ran: side-view-only (Tier 2) checks are skipped for other views. */
export type AssessmentScope = {
  camera_view: string;
  limited_view: boolean;
  limited_view_message?: string | null;
  tier2_skipped: boolean;
  not_assessed: { code: string; title: string }[];
  /** False for analyses recorded before rule coverage existed. */
  coverage_known?: boolean;
  checked_count?: number;
  applicable_count?: number;
  /** Applicable rules that could not run, with a short user-facing reason. */
  unchecked?: { code: string; label: string; reason: string }[];
  /** True only when every applicable rule ran. */
  complete?: boolean;
};

export type ReferenceComparisonData = {
  metric_id?: string;
  title?: string;
  unit: string;
  player_value: number;
  reference_median?: number | null;
  reference_low?: number | null;
  reference_high?: number | null;
  percentile?: number | null;
  reference_profile_id?: string | null;
  group_label?: string;
};

export type Drill = {
  title: string;
  goal: string;
  instructions: string;
  repetitions?: string | null;
  related_issue?: string | null;
  related_issues?: string[];
};

export type CoachingFocusCard = {
  issue_code: string;
  title: string;
  explanation: string;
  priority?: number;
  related_metric_hints?: string[];
  evidence?: {
    measured?: number | null;
    unit?: string;
    reference_median?: number | null;
    reference_percentile?: number | null;
    reference_profile_id?: string;
    phase?: string;
  } | null;
  seek_timestamp?: number | null;
};

export type CoachingReportView = {
  available: boolean;
  status: string;
  summary?: string | null;
  main_focus?: CoachingFocusCard | null;
  secondary: CoachingFocusCard[];
  strengths: { description: string; evidence_refs: string[] }[];
  drills: Drill[];
  caveats: string[];
  notes?: string | null;
};

export type ConfidenceSummary = {
  overall: ConfidenceLevel;
  overall_score: number;
  components: {
    id: string;
    label: string;
    level: ConfidenceLevel;
    score: number;
  }[];
  message?: string | null;
};

export type CompositeScoresView = {
  available: boolean;
  /** Always null: chain timing is not assessable from 2D video. */
  chain_score?: number | null;
  chain_unavailable_reason?: string | null;
  /** Always null: wrist speed has no calibrated scale yet. */
  power_score?: number | null;
  power_unavailable_reason?: string | null;
  base_score?: number | null;
  notes?: string | null;
};

export type AnalysisResult = {
  analysis_id: string;
  created_at?: string;
  stroke_type: string;
  stroke_type_raw?: string;
  handedness?: string | null;
  handedness_raw?: string | null;
  camera_view?: string | null;
  reference_profile_id?: string;
  snapshot_id?: string;
  analysis_status: string;
  coaching_status: string;
  mesh_status: string;
  video: {
    pose_video_url?: string | null;
    available: boolean;
    overlay_modes?: {
      id: string;
      label: string;
      available: boolean;
      default?: boolean;
      toggleable?: boolean;
      note?: string;
      url?: string;
    }[];
  };
  confidence: ConfidenceSummary;
  phases: PhaseSegment[];
  contact: ContactEvent;
  issues: TechniqueIssueView[];
  findings: TechniqueIssueView[];
  insufficient_evidence: TechniqueIssueView[];
  metrics: { id: string; label: string; value: number; unit: string }[];
  /** Tier 3: shown for context only, never a technique issue. */
  display_metrics?: DisplayMetric[];
  assessment_scope?: AssessmentScope | null;
  composite_scores?: CompositeScoresView | null;
  reference_comparisons: ReferenceComparisonData[];
  coaching: CoachingReportView;
  keyframes: { label: string; timestamp?: number; url?: string | null }[];
  limitations: string[];
  artifacts: Record<string, boolean>;
  main_issue?: string | null;
  analysis_confidence?: number;
};

export type AnalysisSummary = {
  analysis_id: string;
  created_at?: string | null;
  stroke_type?: string | null;
  stroke_type_raw?: string | null;
  handedness?: string | null;
  handedness_raw?: string | null;
  /** Present only for indexed analyses with a declared (non-UNKNOWN) view. */
  camera_view?: string | null;
  analysis_confidence?: number | null;
  main_issue?: string | null;
  pose_video_url?: string | null;
  snapshot_id?: string | null;
  reference_profile_id?: string | null;
  analysis_status?: string | null;
  coaching_status?: string | null;
  mesh_status?: string | null;
  composite_scores?: CompositeScoresView | null;
};

export type CompareResponse = {
  compatible: boolean;
  compatibility_reason: string;
  left: AnalysisSummary;
  right: AnalysisSummary;
  rows: {
    label: string;
    unit: string;
    left: number | null;
    right: number | null;
    change: string;
    /** Shown instead of values when the metric cannot be assessed. */
    unavailable_note?: string | null;
  }[];
};

export type AnalyzeStartResponse = {
  analysis_id: string;
  stroke_type?: string;
  analysis_status?: string;
  coaching_status?: string;
  video_url: string;
  mesh_status?: string;
  mesh_job_id?: string;
  mesh_status_url?: string;
  mesh_video_url?: string;
};
