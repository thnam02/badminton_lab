import { render, screen, within } from "@testing-library/react";
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

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/coach",
}));
vi.mock("@/lib/auth", () => ({
  fetchMe: async () => ({ role: "coach", name: "Jeff" }),
}));

beforeEach(() => {
  fetchBatches.mockReset();
  fetchBatches.mockResolvedValue(BATCHES);
});

describe("CoachHome", () => {
  it("greets the signed-in coach and lists batches with their progress", async () => {
    render(<CoachHome />);
    const list = await screen.findByRole("list", { name: "Labelling batches" });
    expect(screen.getByRole("heading", { name: "Hi Jeff" })).toBeTruthy();
    expect(screen.queryByLabelText("Your name")).toBeNull();
    expect(fetchBatches).toHaveBeenCalledWith("Jeff");

    const links = within(list).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/coach/side-set-1-ab12cd",
      "/coach/smash-3f9a00",
      "/coach/new-000000",
    ]);
    expect(links[0].textContent).toContain("20 clips · 7 reviewed by you");
    expect(links[1].textContent).toContain("1 clip · All reviewed");
    const bar = within(links[0]).getByRole("progressbar");
    expect([bar.getAttribute("aria-valuenow"), bar.getAttribute("aria-valuemax")]).toEqual(["7", "20"]);
  });

  it("says when there is nothing to review", async () => {
    fetchBatches.mockResolvedValue([]);
    render(<CoachHome />);
    expect(await screen.findByText(/No clips to review yet/)).toBeTruthy();
  });
});
