import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DatasetClip, DatasetDetail } from "@/lib/labelling";
import { summary } from "@/test/fixtures";
import { CoachDataset } from "./CoachDataset";

function clip(position: number, status: DatasetClip["status"], missing = false): DatasetClip {
  return {
    position,
    analysis_id: `a${position}`,
    source_file: `clip${position}.mp4`,
    missing,
    status,
    labelled: status === "done",
  };
}

function detail(clips: DatasetClip[], overrides: Partial<DatasetDetail> = {}): DatasetDetail {
  return {
    ...summary({
      number: 2,
      dataset_id: "clear-2",
      video_count: clips.length,
      labelled_count: clips.filter((c) => c.labelled).length,
      status: "in_progress",
      note: "Watch the elbow at the hit.",
    }),
    coach: "Jeff",
    total: clips.length,
    clips,
    uploads: [],
    ...overrides,
  };
}

const fetchDataset = vi.fn<(id: string) => Promise<DatasetDetail>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchDataset: (id: string) => fetchDataset(id),
}));

describe("CoachDataset", () => {
  it("lists videos as done or not and continues at the next unlabelled one", async () => {
    fetchDataset.mockResolvedValue(
      detail([clip(1, "done"), clip(2, "not_started", true), clip(3, "in_progress"), clip(4, "not_started")])
    );
    render(<CoachDataset datasetId="clear-2" />);
    const list = await screen.findByRole("list", { name: "Videos" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Video 1Done",
      "Video 2Unavailable",
      "Video 3Not done · started",
      "Video 4Not done",
    ]);
    expect(within(list).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "/coach/datasets/clear-2/label?video=1",
      "/coach/datasets/clear-2/label?video=3",
      "/coach/datasets/clear-2/label?video=4",
    ]);
    expect(screen.getByRole("link", { name: "Continue" }).getAttribute("href")).toBe(
      "/coach/datasets/clear-2/label?video=3"
    );
    expect(screen.getByRole("heading", { name: "Forehand clear · Dataset 2", level: 1 })).toBeTruthy();
    expect(screen.getByText("Watch the elbow at the hit.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "← All datasets" }).getAttribute("href")).toBe("/coach");
  });

  it("has nothing to continue once every video is done", async () => {
    fetchDataset.mockResolvedValue(detail([clip(1, "done"), clip(2, "done")], { status: "done", note: "" }));
    render(<CoachDataset datasetId="clear-2" />);
    expect(await screen.findByText("All videos labelled. Thank you!")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Continue" })).toBeNull();
    expect(screen.queryByText("Note from the admin")).toBeNull();
  });
});
