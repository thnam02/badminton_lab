import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DatasetDetail, LabellingClip, SavedLabel } from "@/lib/labelling";
import { summary } from "@/test/fixtures";
import { LabelView } from "./LabelView";

const CLIP: LabellingClip = {
  analysis_id: "a1",
  video_url: "/outputs/a1_pose.mp4",
  raw_video_url: null,
  overlay_video_url: null,
  stroke_type: "FOREHAND_CLEAR",
  stroke_label: "Forehand clear",
  handedness: "RIGHT",
  camera_view: "SIDE",
  system_contact_frame: 20,
  system_contact_timestamp: 0.66,
  fps: 30,
  frame_count: 40,
  moments: [
    { id: "preparation", title: "Preparation", frame: 5 },
    { id: "contact", title: "Contact", frame: 20 },
  ],
  questions: [
    {
      id: "sideon",
      title: "Side-on to the net",
      hint: "",
      moment: "preparation",
      moment_title: "Preparation",
      kind: "coach_only",
      unit: null,
      value: null,
      available: true,
      measured_at: null,
      joints: [],
      rating_options: [
        { id: "good", label: "Good" },
        { id: "needs_work", label: "Needs work" },
      ],
    },
    {
      id: "elbow",
      title: "Arm straight at the hit",
      hint: "",
      moment: "contact",
      moment_title: "Contact",
      kind: "measured",
      unit: "deg",
      value: 151.4,
      available: true,
      measured_at: { label: "Hit", frame: 20 },
      joints: [],
      rating_options: [
        { id: "good", label: "Good" },
        { id: "needs_work", label: "Needs work" },
      ],
    },
  ],
  fix_options: [{ id: "elbow", title: "Arm straight at the hit" }],
  overall_ratings: [{ value: 3, label: "OK" }],
};

const LABEL: SavedLabel = {
  label_format_version: "2.0.0",
  analysis_id: "a1",
  batch_id: "clear-2",
  coach: "Jeff",
  system_contact_frame: 20,
  corrected_hit_frame: 22,
  stats: { elbow: { rating: "needs_work", comment: "Bent at the hit" } },
  overall_rating: 3,
  most_important_fix: "elbow",
  feedback: "Reach higher.",
  general_comment: "",
  created_at: "2026-11-09T10:00:00+00:00",
  updated_at: "2026-11-09T10:05:00+00:00",
};

const DATASET = {
  ...summary({ number: 2, dataset_id: "clear-2" }),
  coach: "Jeff",
  total: 8,
  clips: [{ position: 3, analysis_id: "a1", source_file: "", missing: false, status: "done", labelled: true }],
  uploads: [],
} as DatasetDetail;

const fetchClipLabel = vi.fn<
  (id: string, coach?: string) => Promise<{ label: SavedLabel | null; status: "done" }>
>(async () => ({ label: LABEL, status: "done" }));

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchDataset: async () => DATASET,
  fetchClip: async () => CLIP,
  fetchClipLabel: (id: string, coach?: string) => fetchClipLabel(id, coach),
}));

describe("LabelView", () => {
  it("shows the coach's answers without anything to edit", async () => {
    render(<LabelView datasetId="clear-2" analysisId="a1" />);
    expect(await screen.findByRole("heading", { name: "Video 3 of 8" })).toBeTruthy();
    expect(fetchClipLabel).toHaveBeenCalledWith("a1", undefined);
    expect(screen.getByText(/Labelled by Jeff/)).toBeTruthy();
    expect(screen.getByText("Hit frame: 22 (moved from 20)")).toBeTruthy();

    const contact = screen.getByRole("region", { name: "Contact" });
    expect(within(contact).getByRole("listitem").textContent).toBe(
      "Arm straight at the hit151°Needs work“Bent at the hit”"
    );
    const prep = screen.getByRole("region", { name: "Preparation" });
    expect(within(prep).getByRole("listitem").textContent).toBe("Side-on to the netJudged by eyeNo answer");
    expect(screen.getByText("Reach higher.")).toBeTruthy();
    expect(screen.getAllByText("Arm straight at the hit")).toHaveLength(2);

    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByRole("link", { name: /Dataset 2/ }).getAttribute("href")).toBe("/admin/datasets/clear-2");
  });

  it("says when the video isn't labelled yet", async () => {
    fetchClipLabel.mockResolvedValueOnce({ label: null, status: "done" });
    render(<LabelView datasetId="clear-2" analysisId="a1" />);
    expect(await screen.findByText("Not labelled yet.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Contact" })).toBeNull();
  });
});
