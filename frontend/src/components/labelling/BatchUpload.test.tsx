import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CreatedDataset, DatasetInput, UploadJob } from "@/lib/labelling";
import { BatchUpload } from "./BatchUpload";

const createDataset = vi.fn<(input: DatasetInput, onProgress?: (f: number) => void) => Promise<CreatedDataset>>();
const fetchUploadJob = vi.fn<(jobId: string) => Promise<UploadJob>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  createDataset: (input: DatasetInput, onProgress?: (f: number) => void) =>
    createDataset(input, onProgress),
  fetchUploadJob: (jobId: string) => fetchUploadJob(jobId),
}));

function job(overrides: Partial<UploadJob> = {}): UploadJob {
  return {
    job_id: "job1",
    batch_id: "set-2-abc123",
    batch_name: "Set 2",
    stroke_type: "FOREHAND_SMASH",
    handedness: "LEFT",
    camera_view: "SIDE",
    status: "running",
    clips: [
      { source_file: "a.mp4", status: "done", analysis_id: "id1", error: null, handedness: "LEFT", camera_view: "SIDE" },
      { source_file: "b.mov", status: "processing", analysis_id: null, error: null, handedness: "LEFT", camera_view: "SIDE" },
      { source_file: "c.mp4", status: "failed", analysis_id: null, error: "No pose detected", handedness: "LEFT", camera_view: "SIDE" },
    ],
    total: 3,
    done_count: 1,
    failed_count: 1,
    remaining_count: 1,
    ...overrides,
  };
}

function clipFile(name: string) {
  return new File(["x"], name, { type: "video/mp4" });
}

const FIVE = ["a.mp4", "b.mov", "c.mp4", "d.mp4", "e.mp4"].map(clipFile);

function created(j: UploadJob = job()): CreatedDataset {
  return { dataset: {} as CreatedDataset["dataset"], job: j };
}

function fillIn() {
  fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-20" } });
  fireEvent.change(screen.getByLabelText(/Drop clips here/), { target: { files: FIVE } });
}

beforeEach(() => {
  createDataset.mockReset();
  fetchUploadJob.mockReset();
});

describe("BatchUpload", () => {
  it("needs a due date and 5 to 10 clips before uploading", () => {
    render(<BatchUpload />);
    const submit = screen.getByRole("button", { name: "Upload and start processing" });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Choose a due date.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-20" } });
    expect(screen.getByText("Choose 5 to 10 clips (0 chosen).")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Drop clips here/), { target: { files: FIVE } });
    expect((submit as HTMLButtonElement).disabled).toBe(false);
  });

  it("keeps only videos and lets clips be removed", () => {
    render(<BatchUpload />);
    const input = screen.getByLabelText(/Drop clips here/);
    fireEvent.change(input, {
      target: { files: [clipFile("a.mp4"), clipFile("b.MOV"), clipFile("notes.txt")] },
    });
    const list = screen.getByRole("list", { name: "Chosen clips" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent?.split("0.0")[0])).toEqual([
      "a.mp4",
      "b.MOV",
    ]);
    expect(screen.getByRole("alert").textContent).toContain("Skipped 1 file");
    fireEvent.click(screen.getByRole("button", { name: "Remove a.mp4" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });

  it("uploads with the chosen settings and shows per-clip progress", async () => {
    createDataset.mockResolvedValue(created());
    render(<BatchUpload />);
    fillIn();
    fireEvent.click(screen.getByLabelText("Forehand smash"));
    fireEvent.click(screen.getByLabelText("Left-handed"));
    fireEvent.click(screen.getByRole("button", { name: "Upload and start processing" }));

    const progress = await screen.findByRole("list", { name: "Clip progress" });
    const input = createDataset.mock.calls[0][0];
    expect(input).toMatchObject({ technique: "FOREHAND_SMASH", dueDate: "2026-11-20", existingIds: [] });
    expect(input.videos.map((v) => [v.file.name, v.handedness, v.cameraView])).toEqual(
      FIVE.map((f) => [f.name, "LEFT", "SIDE"])
    );
    expect(within(progress).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "a.mp4Ready",
      "b.movAnalysing…",
      "c.mp4Failed: No pose detected",
    ]);
    expect(screen.getByText(/2 of 3 finished/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open batch" }).getAttribute("href")).toBe(
      "/coach/set-2-abc123"
    );
  });

  it("polls until processing finishes", async () => {
    createDataset.mockResolvedValue(created());
    fetchUploadJob.mockResolvedValue(
      job({
        status: "done",
        clips: job().clips.map((c) => (c.status === "processing" ? { ...c, status: "done" } : c)),
        done_count: 2,
        remaining_count: 0,
      })
    );
    render(<BatchUpload />);
    fillIn();
    fireEvent.click(screen.getByRole("button", { name: "Upload and start processing" }));
    expect(
      await screen.findByText("Finished: 2 of 3 clips ready, 1 failed.", {}, { timeout: 4000 })
    ).toBeTruthy();
    expect(fetchUploadJob).toHaveBeenCalledWith("job1");
  });

  it("shows the server's reason when the upload is refused", async () => {
    createDataset.mockRejectedValue(new Error("'clip.avi' is not an .mp4 or .mov video."));
    render(<BatchUpload />);
    fillIn();
    fireEvent.click(screen.getByRole("button", { name: "Upload and start processing" }));
    expect((await screen.findByRole("alert")).textContent).toContain("not an .mp4 or .mov");
  });
});
