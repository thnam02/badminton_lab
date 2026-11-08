import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BatchUploadInput, UploadJob } from "@/lib/labelling";
import { BatchUpload } from "./BatchUpload";

const uploadBatch = vi.fn<(input: BatchUploadInput, onProgress?: (f: number) => void) => Promise<UploadJob>>();
const fetchUploadJob = vi.fn<(jobId: string) => Promise<UploadJob>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  uploadBatch: (input: BatchUploadInput, onProgress?: (f: number) => void) =>
    uploadBatch(input, onProgress),
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
      { source_file: "a.mp4", status: "done", analysis_id: "id1", error: null },
      { source_file: "b.mov", status: "processing", analysis_id: null, error: null },
      { source_file: "c.mp4", status: "failed", analysis_id: null, error: "No pose detected" },
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

beforeEach(() => {
  uploadBatch.mockReset();
  fetchUploadJob.mockReset();
});

describe("BatchUpload", () => {
  it("needs a name and at least one clip before uploading", () => {
    render(<BatchUpload />);
    const submit = screen.getByRole("button", { name: "Upload and start processing" });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Give the batch a name.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Batch name"), { target: { value: "Set 2" } });
    expect(screen.getByText("Choose at least one clip.")).toBeTruthy();
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
    uploadBatch.mockResolvedValue(job());
    render(<BatchUpload />);
    fireEvent.change(screen.getByLabelText("Batch name"), { target: { value: "Set 2" } });
    fireEvent.change(screen.getByLabelText(/Drop clips here/), {
      target: { files: [clipFile("a.mp4"), clipFile("b.mov"), clipFile("c.mp4")] },
    });
    fireEvent.click(screen.getByLabelText("Forehand smash"));
    fireEvent.click(screen.getByLabelText("Left-handed"));
    fireEvent.click(screen.getByRole("button", { name: "Upload and start processing" }));

    const progress = await screen.findByRole("list", { name: "Clip progress" });
    const input = uploadBatch.mock.calls[0][0];
    expect(input).toMatchObject({
      name: "Set 2",
      strokeType: "FOREHAND_SMASH",
      handedness: "LEFT",
      cameraView: "SIDE",
    });
    expect(input.files.map((f) => f.name)).toEqual(["a.mp4", "b.mov", "c.mp4"]);
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
    uploadBatch.mockResolvedValue(job());
    fetchUploadJob.mockResolvedValue(
      job({
        status: "done",
        clips: job().clips.map((c) => (c.status === "processing" ? { ...c, status: "done" } : c)),
        done_count: 2,
        remaining_count: 0,
      })
    );
    render(<BatchUpload />);
    fireEvent.change(screen.getByLabelText("Batch name"), { target: { value: "Set 2" } });
    fireEvent.change(screen.getByLabelText(/Drop clips here/), {
      target: { files: [clipFile("a.mp4")] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload and start processing" }));
    expect(
      await screen.findByText("Finished: 2 of 3 clips ready, 1 failed.", {}, { timeout: 4000 })
    ).toBeTruthy();
    expect(fetchUploadJob).toHaveBeenCalledWith("job1");
  });

  it("shows the server's reason when the upload is refused", async () => {
    uploadBatch.mockRejectedValue(new Error("'clip.avi' is not an .mp4 or .mov video."));
    render(<BatchUpload />);
    fireEvent.change(screen.getByLabelText("Batch name"), { target: { value: "Set 2" } });
    fireEvent.change(screen.getByLabelText(/Drop clips here/), {
      target: { files: [clipFile("a.mp4")] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload and start processing" }));
    expect((await screen.findByRole("alert")).textContent).toContain("not an .mp4 or .mov");
  });
});
