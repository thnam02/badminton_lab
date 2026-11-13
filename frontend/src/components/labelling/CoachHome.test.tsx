import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DatasetSummary } from "@/lib/labelling";
import { summary } from "@/test/fixtures";
import { CoachHome } from "./CoachHome";

const fetchDatasets = vi.fn<() => Promise<DatasetSummary[]>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchDatasets: () => fetchDatasets(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/coach",
}));
vi.mock("@/lib/auth", () => ({
  fetchMe: async () => ({ role: "coach", name: "Jeff" }),
}));

beforeEach(() => {
  fetchDatasets.mockReset();
});

describe("CoachHome", () => {
  it("greets Jeff and shows a section per technique", async () => {
    fetchDatasets.mockResolvedValue([
      summary({ number: 1, technique: "FOREHAND_SMASH", dataset_id: "smash-1" }),
    ]);
    render(<CoachHome />);
    expect(await screen.findByRole("heading", { name: "Hi Jeff", level: 1 })).toBeTruthy();
    expect(screen.queryByLabelText("Your name")).toBeNull();
    await screen.findByRole("region", { name: "Forehand smash" });
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Forehand clear", "Forehand smash"]);
    const clears = screen.getByRole("region", { name: "Forehand clear" });
    expect(within(clears).getByText("Nothing to label yet.")).toBeTruthy();
    const smashes = within(screen.getByRole("region", { name: "Forehand smash" })).getAllByRole("link");
    expect(smashes.map((a) => a.getAttribute("href"))).toEqual(["/coach/datasets/smash-1"]);
  });

  it("sorts overdue datasets first, then the nearest due date", async () => {
    fetchDatasets.mockResolvedValue([
      summary({ number: 1, status: "done", due_date: "2026-11-01", days_left: -9, labelled_count: 8 }),
      summary({ number: 2, status: "in_progress", due_date: "2026-11-25", days_left: 15, labelled_count: 3 }),
      summary({ number: 3, status: "overdue", due_date: "2026-11-05", days_left: -5, labelled_count: 2 }),
      summary({ number: 4, status: "not_started", due_date: "2026-11-12", days_left: 2 }),
      summary({ number: 5, status: "not_started", due_date: null, days_left: null }),
    ]);
    render(<CoachHome />);
    const list = await screen.findByRole("list", { name: "Forehand clear datasets" });
    const cards = within(list).getAllByRole("link");
    expect(cards.map((c) => c.getAttribute("href"))).toEqual([
      "/coach/datasets/clear-3",
      "/coach/datasets/clear-4",
      "/coach/datasets/clear-2",
      "/coach/datasets/clear-5",
      "/coach/datasets/clear-1",
    ]);

    const [overdue, soon, , undated, done] = cards;
    expect(overdue.textContent).toContain("Dataset 3");
    expect(overdue.textContent).toContain("8 videos · 2 labelled");
    expect(overdue.textContent).toContain("Due 5 Nov · Overdue");
    expect(soon.textContent).toContain("Due 12 Nov · 2 days left");
    expect(soon.textContent).toContain("Not started");
    expect(undated.textContent).toContain("No due date");
    expect(done.textContent).toContain("Done");
    const bar = within(overdue).getByRole("progressbar");
    expect([bar.getAttribute("aria-valuenow"), bar.getAttribute("aria-valuemax")]).toEqual(["2", "8"]);
  });
});
