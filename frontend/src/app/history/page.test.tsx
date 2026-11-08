import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalysisSummary } from "@/lib/types";
import HistoryPage from "./page";

const fetchAnalyses = vi.fn<(limit?: number) => Promise<AnalysisSummary[]>>();

vi.mock("@/lib/api", () => ({
  fetchAnalyses: (limit?: number) => fetchAnalyses(limit),
  mediaUrl: () => null,
}));

function item(
  id: string,
  created_at: string,
  overrides: Partial<AnalysisSummary> = {}
): AnalysisSummary {
  return {
    analysis_id: id,
    created_at,
    stroke_type: "Forehand clear",
    stroke_type_raw: "forehand_clear",
    composite_scores: { available: false },
    ...overrides,
  };
}

const sideWithBase = (id: string, date: string, base: number) =>
  item(id, date, {
    camera_view: "SIDE",
    composite_scores: { available: true, base_score: base, power_score: null, chain_score: null },
  });

describe("HistoryPage", () => {
  beforeEach(() => {
    fetchAnalyses.mockReset();
  });

  it("hides the BASE trend with fewer than two side-view BASE scores", async () => {
    fetchAnalyses.mockResolvedValue([
      sideWithBase("a", "2026-11-01T00:00:00Z", 0.5),
      item("b", "2026-11-02T00:00:00Z", {
        camera_view: "FRONT",
        composite_scores: { available: true, base_score: 0.6 },
      }),
      item("c", "2026-11-03T00:00:00Z", { camera_view: "SIDE" }),
    ]);
    render(<HistoryPage />);
    await screen.findByText("Analyses");
    expect(screen.queryByText("Base score over time")).toBeNull();
  });

  it("shows the BASE trend oldest first once two side-view BASE scores exist", async () => {
    fetchAnalyses.mockResolvedValue([
      sideWithBase("new", "2026-11-05T00:00:00Z", 0.71),
      sideWithBase("old", "2026-11-01T00:00:00Z", 0.42),
    ]);
    render(<HistoryPage />);
    expect(
      await screen.findByRole("img", {
        name: "Base score trend across 2 side-view analyses: 42, 71",
      })
    ).toBeTruthy();
  });

  it("shows n/a for a missing BASE score instead of a number", async () => {
    fetchAnalyses.mockResolvedValue([item("a", "2026-11-01T00:00:00Z")]);
    render(<HistoryPage />);
    const row = (await screen.findAllByRole("listitem"))[0];
    expect(within(row).getByText("n/a")).toBeTruthy();
  });

  it("filters by stroke and links two selected analyses to compare, oldest first", async () => {
    fetchAnalyses.mockResolvedValue([
      item("clear-new", "2026-11-05T00:00:00Z"),
      item("smash", "2026-11-03T00:00:00Z", {
        stroke_type: "Forehand smash",
        stroke_type_raw: "forehand_smash",
      }),
      item("clear-old", "2026-11-01T00:00:00Z"),
    ]);
    render(<HistoryPage />);
    await screen.findByText("Analyses");

    fireEvent.click(screen.getByRole("button", { name: "Smash" }));
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);

    expect(
      (screen.getByRole("button", { name: "Compare selected (0)" }) as HTMLButtonElement).disabled
    ).toBe(true);
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    const link = screen.getByRole("link", { name: "Compare selected (2)" });
    expect(link.getAttribute("href")).toBe("/compare?left=clear-old&right=clear-new");
  });
});
