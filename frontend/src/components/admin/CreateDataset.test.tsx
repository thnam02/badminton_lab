import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CreatedDataset,
  DatasetInput,
  PickableAnalysis,
  Technique,
  UploadJob,
} from "@/lib/labelling";
import { summary } from "@/test/fixtures";
import { blockedReason, CreateDataset } from "./CreateDataset";

const createDataset = vi.fn<(input: DatasetInput, onProgress?: (f: number) => void) => Promise<CreatedDataset>>();
const fetchUploadJob = vi.fn<(jobId: string) => Promise<UploadJob>>();
const fetchPickableAnalyses = vi.fn<(technique: Technique) => Promise<PickableAnalysis[]>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  createDataset: (input: DatasetInput, onProgress?: (f: number) => void) => createDataset(input, onProgress),
  fetchUploadJob: (jobId: string) => fetchUploadJob(jobId),
  fetchPickableAnalyses: (technique: Technique) => fetchPickableAnalyses(technique),
}));

const ANALYSED: PickableAnalysis[] = ["aaaa1111", "bbbb2222"].map((id) => ({
  analysis_id: id,
  created_at: "2026-11-08T11:02:54+00:00",
  handedness: "RIGHT",
  camera_view: "SIDE",
  datasets: id === "aaaa1111" ? ["Dataset 1"] : [],
}));

function job(overrides: Partial<UploadJob> = {}): UploadJob {
  const clip = (source_file: string, status: UploadJob["clips"][number]["status"], error: string | null = null) => ({
    source_file,
    status,
    analysis_id: status === "done" ? `id-${source_file}` : null,
    error,
    handedness: "RIGHT",
    camera_view: "SIDE",
  });
  return {
    job_id: "job1",
    batch_id: "clear-3",
    batch_name: "Forehand clear · Dataset 3",
    stroke_type: "FOREHAND_CLEAR",
    handedness: "MIXED",
    camera_view: "SIDE",
    status: "running",
    clips: [clip("a.mp4", "done"), clip("b.mov", "processing"), clip("c.mp4", "failed", "No pose detected")],
    total: 3,
    done_count: 1,
    failed_count: 1,
    remaining_count: 1,
    ...overrides,
  };
}

function files(...names: string[]) {
  return names.map((n) => new File(["x"], n, { type: "video/mp4" }));
}

function chooseFiles(...names: string[]) {
  fireEvent.change(screen.getByLabelText(/Choose video files/), { target: { files: files(...names) } });
}

beforeEach(() => {
  createDataset.mockReset();
  fetchUploadJob.mockReset();
  fetchPickableAnalyses.mockReset();
  fetchPickableAnalyses.mockResolvedValue(ANALYSED);
});

describe("blockedReason", () => {
  it("allows 5 to 10 videos with a due date", () => {
    expect(blockedReason(0, "2026-11-20")).toBe("Add 5 more videos (a dataset has 5 to 10).");
    expect(blockedReason(4, "2026-11-20")).toBe("Add 1 more video (a dataset has 5 to 10).");
    expect(blockedReason(5, "2026-11-20")).toBeNull();
    expect(blockedReason(10, "2026-11-20")).toBeNull();
    expect(blockedReason(11, "2026-11-20")).toBe("Remove 1 video (a dataset has at most 10).");
    expect(blockedReason(7, "")).toBe("Choose a due date.");
  });
});

describe("CreateDataset", () => {
  it("won't send fewer than 5 or more than 10 videos", () => {
    render(<CreateDataset />);
    const submit = screen.getByRole("button", { name: "Create dataset" }) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-20" } });
    chooseFiles("1.mp4", "2.mp4", "3.mp4", "4.mp4");
    expect(submit.disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("Add 1 more video");
    chooseFiles("5.mp4");
    expect(submit.disabled).toBe(false);
    chooseFiles("6.mp4", "7.mp4", "8.mp4", "9.mp4", "10.mp4", "11.mp4");
    expect(submit.disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("Remove 1 video");
  });

  it("sends each upload's handedness and camera view, picked analyses, due date and note", async () => {
    createDataset.mockResolvedValue({
      dataset: summary({ number: 3, dataset_id: "clear-3" }),
      job: job(),
    });
    render(<CreateDataset />);
    chooseFiles("a.mp4", "b.mov", "c.mp4");
    fireEvent.change(screen.getByLabelText("Handedness for b.mov"), { target: { value: "LEFT" } });
    fireEvent.change(screen.getByLabelText("Camera view for c.mp4"), { target: { value: "FRONT" } });
    const picker = await screen.findByRole("list", { name: "Analysed videos" });
    expect(picker.textContent).toContain("already in Dataset 1");
    for (const box of within(picker).getAllByRole("checkbox")) fireEvent.click(box);
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-20" } });
    fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "Elbow please" } });
    fireEvent.click(screen.getByRole("button", { name: "Create dataset" }));

    const progress = await screen.findByRole("list", { name: "Video processing" });
    const input = createDataset.mock.calls[0][0];
    expect(input).toMatchObject({
      technique: "FOREHAND_CLEAR",
      dueDate: "2026-11-20",
      note: "Elbow please",
      existingIds: ["aaaa1111", "bbbb2222"],
    });
    expect(input.videos.map((v) => [v.file.name, v.handedness, v.cameraView])).toEqual([
      ["a.mp4", "RIGHT", "SIDE"],
      ["b.mov", "LEFT", "SIDE"],
      ["c.mp4", "RIGHT", "FRONT"],
    ]);
    expect(within(progress).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Analysed video aaaa1111Ready",
      "Analysed video bbbb2222Ready",
      "a.mp4Ready",
      "b.movAnalysing…",
      "c.mp4Failed: No pose detected",
    ]);
    expect(screen.getByRole("heading", { name: "Forehand clear · Dataset 3" })).toBeTruthy();
    expect(screen.getByText(/4 of 5 finished/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open dataset" }).getAttribute("href")).toBe(
      "/admin/datasets/clear-3"
    );
  });

  it("lists analyses of the chosen technique and drops picks when it changes", async () => {
    render(<CreateDataset />);
    await screen.findByRole("list", { name: "Analysed videos" });
    expect(fetchPickableAnalyses).toHaveBeenLastCalledWith("FOREHAND_CLEAR");
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.getByText("1 picked")).toBeTruthy();
    fetchPickableAnalyses.mockResolvedValue([]);
    fireEvent.click(screen.getByLabelText("Forehand smash"));
    expect(await screen.findByText("No forehand smash analyses yet.")).toBeTruthy();
    expect(fetchPickableAnalyses).toHaveBeenLastCalledWith("FOREHAND_SMASH");
    expect(screen.getByText("0 picked")).toBeTruthy();
  });

  it("shows the server's reason when the dataset is refused", async () => {
    createDataset.mockRejectedValue(new Error("The due date can't be in the past."));
    render(<CreateDataset />);
    chooseFiles("1.mp4", "2.mp4", "3.mp4", "4.mp4", "5.mp4");
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Create dataset" }));
    expect((await screen.findByRole("alert")).textContent).toContain("can't be in the past");
  });
});
