import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DatasetSummary } from "@/lib/labelling";
import { CoachHome } from "./CoachHome";

const fetchDatasets = vi.fn<() => Promise<DatasetSummary[]>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchDatasets: () => fetchDatasets(),
}));

function dataset(batch_id: string, name: string, clip_count: number, labelled_count: number): DatasetSummary {
  return {
    dataset_id: batch_id,
    batch_id,
    name,
    clip_count,
    labelled_count,
    video_count: clip_count,
    processing_count: 0,
    technique: "FOREHAND_CLEAR",
    technique_label: "Forehand clear",
    number: 1,
    title: "Dataset 1",
    note: "",
    created_at: "",
    due_date: null,
    days_left: null,
    status: "not_started",
  };
}

const BATCHES: DatasetSummary[] = [
  dataset("side-set-1-ab12cd", "Side-view set 1", 20, 7),
  dataset("smash-3f9a00", "Smash check", 1, 1),
  dataset("new-000000", "New set", 5, 0),
];

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/coach",
}));
vi.mock("@/lib/auth", () => ({
  fetchMe: async () => ({ role: "coach", name: "Jeff" }),
}));

beforeEach(() => {
  fetchDatasets.mockReset();
  fetchDatasets.mockResolvedValue(BATCHES);
});

describe("CoachHome", () => {
  it("greets the signed-in coach and lists batches with their progress", async () => {
    render(<CoachHome />);
    const list = await screen.findByRole("list", { name: "Labelling batches" });
    expect(screen.getByRole("heading", { name: "Hi Jeff" })).toBeTruthy();
    expect(screen.queryByLabelText("Your name")).toBeNull();
    expect(fetchDatasets).toHaveBeenCalled();

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
    fetchDatasets.mockResolvedValue([]);
    render(<CoachHome />);
    expect(await screen.findByText(/No clips to review yet/)).toBeTruthy();
  });
});
