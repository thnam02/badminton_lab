import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LabelDraft, LabellingBatch, LabellingClip } from "@/lib/labelling";
import { LabellingWorkspace } from "./LabellingWorkspace";

function clip(id: string): LabellingClip {
  return {
    analysis_id: id,
    video_url: `/outputs/labelling/videos/${id}.mp4`,
    raw_video_url: `/outputs/labelling/videos/${id}.mp4`,
    overlay_video_url: `/outputs/${id}_pose.mp4`,
    stroke_type: "FOREHAND_CLEAR",
    stroke_label: "Forehand Clear",
    handedness: "RIGHT",
    camera_view: "SIDE",
    system_contact_frame: 48,
    system_contact_timestamp: 1.6,
    fps: 30,
    frame_count: 97,
    stats: [
      {
        id: "contact_elbow_angle",
        name: "Arm straightness at the hit",
        description: "Angle at the elbow when the racket meets the shuttle.",
        when: "At the hit",
        unit: "deg",
        value: 132.4,
        available: true,
      },
      {
        id: "hand_speed",
        name: "Hand speed",
        description: "Fastest hand speed.",
        when: "Fastest moment of the swing",
        unit: "torso_lengths_per_s",
        value: null,
        available: false,
      },
    ],
    rating_options: [
      { id: "good", label: "Good" },
      { id: "needs_work", label: "Needs work" },
      { id: "looks_wrong", label: "Looks wrong" },
    ],
    overall_ratings: [1, 2, 3, 4, 5].map((value) => ({ value, label: `R${value}` })),
  };
}

const labelled = new Set<string>();

function batch(): LabellingBatch {
  const clips = ["a1", "a2"].map((id, i) => ({
    position: i + 1,
    analysis_id: id,
    source_file: `${id}.mp4`,
    missing: false,
    status: labelled.has(id) ? ("done" as const) : ("not_started" as const),
    labelled: labelled.has(id),
    coach_count: 0,
  }));
  return {
    batch_id: "set-1",
    name: "Side-view set 1",
    created_at: "",
    coach: "Linh",
    total: 2,
    labelled_count: labelled.size,
    clips,
  };
}

const saveClipLabel = vi.fn(
  async (id: string, body: LabelDraft & { coach: string; batch_id: string }) => {
    if (body.overall_rating != null) labelled.add(id);
    return { label: { ...body } as never, status: "in_progress" as const };
  }
);

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchBatch: async () => batch(),
  fetchClip: async (id: string) => clip(id),
  fetchClipLabel: async () => ({ label: null, status: "not_started" }),
  saveClipLabel: (id: string, body: LabelDraft & { coach: string; batch_id: string }) =>
    saveClipLabel(id, body),
}));

beforeEach(() => {
  labelled.clear();
  saveClipLabel.mockClear();
  window.localStorage.clear();
  window.localStorage.setItem("badminton-lab.coach-name", "Linh");
  window.scrollTo = vi.fn();
});

describe("LabellingWorkspace", () => {
  it("asks for the coach's name first", async () => {
    window.localStorage.clear();
    render(<LabellingWorkspace batchId="set-1" />);
    fireEvent.change(await screen.findByLabelText("Your name"), { target: { value: "Minh" } });
    fireEvent.click(screen.getByRole("button", { name: "Start reviewing" }));
    expect(await screen.findByText("Clip 1 of 2")).toBeTruthy();
    expect(window.localStorage.getItem("badminton-lab.coach-name")).toBe("Minh");
  });

  it("shows progress, the measured stats and skips unmeasured ones", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    expect(await screen.findByText("Clip 1 of 2")).toBeTruthy();
    const bar = screen.getByRole("progressbar", { name: "Clips reviewed" });
    expect(bar.getAttribute("aria-valuenow")).toBe("0");
    expect(await screen.findByText("Arm straightness at the hit")).toBeTruthy();
    expect(screen.getByText("132°")).toBeTruthy();
    expect(screen.getByText(/Not measured in this clip/)).toBeTruthy();
  });

  it("autosaves ratings without pressing save", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    fireEvent.click(await screen.findByLabelText("Needs work"));
    await waitFor(() => expect(saveClipLabel).toHaveBeenCalled(), { timeout: 2000 });
    const [id, body] = saveClipLabel.mock.calls[0];
    expect(id).toBe("a1");
    expect(body).toMatchObject({
      coach: "Linh",
      batch_id: "set-1",
      corrected_hit_frame: null,
      stats: { contact_elbow_angle: { rating: "needs_work", comment: "" } },
    });
  });

  it("saves a corrected hit and moves to the next clip", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Forward a little ▶" }));
    fireEvent.click(screen.getByRole("button", { name: "This is the hit" }));
    fireEvent.click(screen.getByLabelText("Good"));
    fireEvent.click(screen.getByText("R4"));
    fireEvent.click(screen.getByRole("button", { name: "Save and go to next clip →" }));
    expect(await screen.findByText("Clip 2 of 2")).toBeTruthy();
    const last = saveClipLabel.mock.calls.at(-1)!;
    expect(last[0]).toBe("a1");
    expect(last[1]).toMatchObject({ corrected_hit_frame: 49, overall_rating: 4 });
    expect(
      screen.getByRole("progressbar", { name: "Clips reviewed" }).getAttribute("aria-valuenow")
    ).toBe("1");
  });

  it("keeps every control at least 48px tall for tablets", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    await screen.findByText("Arm straightness at the hit");
    const tall = /(?:^|\s)(min-h-(1[2-9]|[2-9]\d)|min-h-\[(4[89]|[5-9]\d)px\]|h-12)(?=\s|$)/;
    const controls = [
      ...screen.getAllByRole("button"),
      ...screen.getAllByRole("radio").map((r) => r.closest("label")!),
      ...screen.getAllByRole("slider"),
      ...screen.getAllByRole("checkbox").map((c) => c.closest("label")!),
    ];
    const short = controls.filter((el) => !tall.test(el.className)).map((el) => el.textContent);
    expect(short).toEqual([]);
  });
});
