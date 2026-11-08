import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BatchSummary } from "@/lib/labelling";
import { CoachHome } from "./CoachHome";

const fetchBatches = vi.fn<(coach: string) => Promise<BatchSummary[]>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchBatches: (coach: string) => fetchBatches(coach),
}));

const BATCHES: BatchSummary[] = [
  { batch_id: "side-set-1-ab12cd", name: "Side-view set 1", clip_count: 20, labelled_count: 7, created_at: "" },
  { batch_id: "smash-3f9a00", name: "Smash check", clip_count: 1, labelled_count: 1, created_at: "" },
  { batch_id: "new-000000", name: "New set", clip_count: 5, labelled_count: 0, created_at: "" },
];

beforeEach(() => {
  window.localStorage.clear();
  fetchBatches.mockReset();
  fetchBatches.mockResolvedValue(BATCHES);
});

describe("CoachHome", () => {
  it("reuses the stored name and lists batches with this coach's progress", async () => {
    window.localStorage.setItem("badminton-lab.coach-name", "Linh");
    render(<CoachHome />);
    const list = await screen.findByRole("list", { name: "Labelling batches" });
    expect(screen.queryByLabelText("Your name")).toBeNull();
    expect(fetchBatches).toHaveBeenCalledWith("Linh");

    const links = within(list).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/coach/side-set-1-ab12cd",
      "/coach/smash-3f9a00",
      "/coach/new-000000",
    ]);
    expect(links[0].textContent).toContain("Side-view set 1");
    expect(links[0].textContent).toContain("20 clips · 7 reviewed by you");
    expect(links[0].textContent).toContain("Continue");
    expect(links[1].textContent).toContain("1 clip · All reviewed");
    expect(links[2].textContent).toContain("Start");
    const bar = within(links[0]).getByRole("progressbar");
    expect([bar.getAttribute("aria-valuenow"), bar.getAttribute("aria-valuemax")]).toEqual(["7", "20"]);
  });

  it("asks for the name once, remembers it and loads that coach's counts", async () => {
    render(<CoachHome />);
    fireEvent.change(await screen.findByLabelText("Your name"), { target: { value: " Minh " } });
    fireEvent.click(screen.getByRole("button", { name: "Start reviewing" }));
    await screen.findByRole("list", { name: "Labelling batches" });
    expect(fetchBatches).toHaveBeenCalledWith("Minh");
    expect(window.localStorage.getItem("badminton-lab.coach-name")).toBe("Minh");
  });

  it("lets another coach take over", async () => {
    window.localStorage.setItem("badminton-lab.coach-name", "Linh");
    render(<CoachHome />);
    fireEvent.click(await screen.findByRole("button", { name: "Not you?" }));
    expect(screen.getByLabelText("Your name")).toBeTruthy();
    expect(window.localStorage.getItem("badminton-lab.coach-name")).toBeNull();
  });

  it("says when there is nothing to review", async () => {
    window.localStorage.setItem("badminton-lab.coach-name", "Linh");
    fetchBatches.mockResolvedValue([]);
    render(<CoachHome />);
    expect(await screen.findByText(/No clips to review yet/)).toBeTruthy();
  });
});
