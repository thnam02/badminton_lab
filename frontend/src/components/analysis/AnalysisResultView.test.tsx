import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalysisResult } from "@/lib/types";
import { AnalysisResultView } from "./AnalysisResultView";

const fetchAnalysis = vi.fn<(id: string) => Promise<AnalysisResult>>();

vi.mock("@/lib/api", () => ({
  fetchAnalysis: (id: string) => fetchAnalysis(id),
  mediaUrl: (path: string | null | undefined) => path ?? null,
}));

const ESTIMATED_NOTE =
  "Contact time is estimated from your arm speed. The shuttle wasn't tracked at that moment, so it may be a few frames off.";

function analysis(shuttleVerified: boolean): AnalysisResult {
  return {
    analysis_id: "abc123",
    stroke_type: "Forehand clear",
    analysis_status: "COMPLETE",
    coaching_status: "NONE",
    mesh_status: "NONE",
    video: { pose_video_url: null, available: false },
    confidence: { overall: "HIGH", overall_score: 0.9, components: [], message: null },
    phases: [
      {
        id: "PREPARATION",
        label: "Preparation",
        start_timestamp: 0,
        end_timestamp: 4,
        confidence: 0.9,
        is_contact_event: false,
        seek_timestamp: 0,
      },
      {
        id: "ESTIMATED_CONTACT",
        label: "Estimated contact",
        start_timestamp: 4.5,
        end_timestamp: 4.5,
        confidence: 0.9,
        is_contact_event: true,
        seek_timestamp: 4.5,
      },
    ],
    contact: {
      timestamp: 4.5,
      frame_index: 135,
      confidence: 0.9,
      contact_type: shuttleVerified ? "TRACKED_CONTACT" : "KINEMATIC_ESTIMATE",
      label: "",
      shuttle_verified: shuttleVerified,
      available: true,
    },
    issues: [],
    findings: [],
    insufficient_evidence: [],
    metrics: [],
    composite_scores: null,
    reference_comparisons: [],
    coaching: {
      available: false,
      status: "NONE",
      secondary: [],
      strengths: [],
      drills: [],
      caveats: [],
    },
    keyframes: [],
    limitations: [],
    artifacts: {},
  };
}

describe("AnalysisResultView contact wording", () => {
  beforeEach(() => {
    fetchAnalysis.mockReset();
  });

  it("labels an unverified contact as estimated", async () => {
    fetchAnalysis.mockResolvedValue(analysis(false));
    render(<AnalysisResultView analysisId="abc123" />);
    expect(await screen.findByText(ESTIMATED_NOTE)).toBeTruthy();
    expect(screen.getByText("Estimated contact (not verified by shuttle)")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Seek to estimated contact at 0:04.50" })
    ).toBeTruthy();
  });

  it("labels a shuttle-verified contact as detected", async () => {
    fetchAnalysis.mockResolvedValue(analysis(true));
    render(<AnalysisResultView analysisId="abc123" />);
    expect(await screen.findByText("Detected contact (shuttle-verified)")).toBeTruthy();
    expect(screen.queryByText(ESTIMATED_NOTE)).toBeNull();
    expect(screen.getByRole("button", { name: "Seek to contact at 0:04.50" })).toBeTruthy();
  });
});
