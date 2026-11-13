import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DatasetDetail, DatasetSummary } from "@/lib/labelling";
import { summary } from "@/test/fixtures";
import { AdminDataset } from "./AdminDataset";

const fetchDataset = vi.fn<(id: string) => Promise<DatasetDetail>>();
const updateDataset = vi.fn<(id: string, body: { due_date?: string; note?: string }) => Promise<DatasetSummary>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchDataset: (id: string) => fetchDataset(id),
  updateDataset: (id: string, body: { due_date?: string; note?: string }) => updateDataset(id, body),
}));

function detail(overrides: Partial<DatasetDetail> = {}): DatasetDetail {
  return {
    ...summary({ number: 2, dataset_id: "clear-2", labelled_count: 1, video_count: 3, status: "in_progress" }),
    coach: "Jeff",
    total: 2,
    note: "Side view only",
    clips: [
      {
        position: 1,
        analysis_id: "a1",
        source_file: "one.mp4",
        handedness: "RIGHT",
        camera_view: "SIDE",
        missing: false,
        status: "done",
        labelled: true,
      },
      { position: 2, analysis_id: "a2", source_file: "", missing: false, status: "not_started", labelled: false },
    ],
    uploads: [
      {
        job_id: "j1",
        batch_id: "clear-2",
        batch_name: "",
        stroke_type: "FOREHAND_CLEAR",
        handedness: "RIGHT",
        camera_view: "SIDE",
        status: "running",
        clips: [
          { source_file: "one.mp4", status: "done", analysis_id: "a1", error: null, handedness: "RIGHT", camera_view: "SIDE" },
          { source_file: "three.mp4", status: "processing", analysis_id: null, error: null, handedness: "RIGHT", camera_view: "SIDE" },
        ],
        total: 2,
        done_count: 1,
        failed_count: 0,
        remaining_count: 1,
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  fetchDataset.mockReset();
  updateDataset.mockReset();
  fetchDataset.mockResolvedValue(detail());
});

describe("AdminDataset", () => {
  it("lists videos as labelled or not, with processing ones and read-only label links", async () => {
    render(<AdminDataset datasetId="clear-2" />);
    const list = await screen.findByRole("list", { name: "Videos" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      "1one.mp4Right-handed, side viewLabelledView label",
      "2Video a2Not labelledView label",
      "three.mp4Analysing…",
    ]);
    expect(screen.getByRole("link", { name: "View label for video 2" }).getAttribute("href")).toBe(
      "/admin/datasets/clear-2/videos/a2"
    );
    expect(screen.getByRole("heading", { name: "Forehand clear · Dataset 2" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download CSV" }).getAttribute("href")).toMatch(
      /\/labelling\/datasets\/clear-2\/export\?format=csv$/
    );
    expect(screen.getByRole("link", { name: "Download JSON" }).getAttribute("href")).toMatch(/format=json$/);
  });

  it("saves a new due date", async () => {
    updateDataset.mockResolvedValue(summary());
    render(<AdminDataset datasetId="clear-2" />);
    const due = (await screen.findByLabelText("Due date")) as HTMLInputElement;
    expect(due.value).toBe("2026-11-20");
    const save = screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(due, { target: { value: "2026-12-01" } });
    fetchDataset.mockResolvedValue(detail({ due_date: "2026-12-01" }));
    fireEvent.click(save);
    expect(await screen.findByText("Saved.")).toBeTruthy();
    expect(updateDataset).toHaveBeenCalledWith("clear-2", { due_date: "2026-12-01", note: "Side view only" });
  });

  it("only changes the note when the due date is untouched", async () => {
    updateDataset.mockResolvedValue(summary());
    fetchDataset.mockResolvedValue(detail({ status: "overdue", due_date: "2026-11-01" }));
    render(<AdminDataset datasetId="clear-2" />);
    fireEvent.change(await screen.findByLabelText("Note for the coach"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Saved.")).toBeTruthy();
    expect(updateDataset).toHaveBeenCalledWith("clear-2", { note: "" });
  });
});
