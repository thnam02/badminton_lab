import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LabelDraft, LabellingBatch, LabellingClip, ReviewQuestion } from "@/lib/labelling";
import { LabellingWorkspace } from "./LabellingWorkspace";

const MEASURED = [
  { id: "good" as const, label: "Good" },
  { id: "needs_work" as const, label: "Needs work" },
  { id: "looks_wrong" as const, label: "Looks wrong" },
];
const COACH_ONLY = [
  { id: "good" as const, label: "Good" },
  { id: "needs_work" as const, label: "Needs work" },
  { id: "cant_see" as const, label: "Can't see" },
];

function question(
  id: string,
  title: string,
  moment: ReviewQuestion["moment"],
  measured: { value: number | null; unit: string } | null
): ReviewQuestion {
  return {
    id,
    title,
    hint: `${title} hint`,
    moment,
    moment_title: moment,
    kind: measured ? "measured" : "coach_only",
    unit: measured?.unit ?? null,
    value: measured?.value ?? null,
    available: measured ? measured.value != null : true,
    measured_at: measured ? { label: "At the hit", frame: 48 } : null,
    joints: [],
    rating_options: measured ? MEASURED : COACH_ONLY,
  };
}

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
    moments: [
      { id: "preparation", title: "Getting ready", frame: 9 },
      { id: "contact", title: "The hit", frame: 48 },
      { id: "follow_through", title: "After the hit", frame: 61 },
    ],
    questions: [
      question("sideon", "Side-on to the net", "preparation", null),
      question("knee", "Weight on back leg, knees bent", "preparation", { value: 152, unit: "deg" }),
      question("elbow", "Arm straight at the hit", "contact", { value: 126.4, unit: "deg" }),
      question("height", "Hitting high", "contact", { value: 0.62, unit: "torso_lengths_above_shoulder" }),
      question("follow", "Follow-through across the body", "follow_through", null),
      question("legs", "Weight moves forward", "follow_through", { value: null, unit: "deg" }),
    ],
    fix_options: [
      { id: "elbow", title: "Arm straight at the hit" },
      { id: "height", title: "Hitting high" },
      { id: "not_listed", title: "Something not listed" },
    ],
    overall_ratings: ["Poor", "Weak", "OK", "Good", "Excellent"].map((label, i) => ({
      value: i + 1,
      label,
    })),
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

type SaveBody = LabelDraft & { coach: string; batch_id: string };

const saveClipLabel = vi.fn(async (id: string, body: SaveBody) => {
  if (body.overall_rating != null) labelled.add(id);
  return { label: { ...body } as never, status: "in_progress" as const };
});

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchBatch: async () => batch(),
  fetchClip: async (id: string) => clip(id),
  fetchClipLabel: async () => ({ label: null, status: "not_started" }),
  saveClipLabel: (id: string, body: SaveBody) => saveClipLabel(id, body),
}));

vi.mock("@/lib/overlay", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/overlay")>()),
  fetchPose: async () => ({
    fps: 30,
    frame_count: 97,
    keypoint_names: [],
    confidence_threshold: 0.5,
    frames: [],
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/coach",
}));
vi.mock("@/lib/auth", () => ({
  fetchMe: async () => ({ role: "coach", name: "Jeff" }),
}));

beforeEach(() => {
  labelled.clear();
  saveClipLabel.mockClear();
  window.scrollTo = vi.fn();
});

function frameLabel() {
  return screen.getByText(/^Frame \d+ · /).textContent;
}

function card(title: string) {
  return screen.getByRole("group", { name: title });
}

describe("LabellingWorkspace", () => {
  it("groups questions by moment and shows measured values or 'You judge'", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    const ready = await screen.findByRole("region", { name: "1 · Getting ready" });
    expect(within(ready).getAllByRole("group").map((g) => g.getAttribute("aria-label") ?? g.querySelector("legend")?.textContent)).toEqual([
      "Side-on to the net",
      "Weight on back leg, knees bent",
    ]);
    expect(within(card("Side-on to the net")).getByText("You judge")).toBeTruthy();
    expect(within(card("Arm straight at the hit")).getByText("126°")).toBeTruthy();
    expect(within(card("Hitting high")).getByText("0.62 above")).toBeTruthy();
    expect(within(card("Weight moves forward")).getByText(/Not measured in this clip/)).toBeTruthy();
    expect(within(card("Side-on to the net")).getByLabelText("Can't see")).toBeTruthy();
    expect(within(card("Arm straight at the hit")).queryByLabelText("Can't see")).toBeNull();
  });

  it("moment tabs seek the video and highlight that moment's questions", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    await screen.findByRole("tab", { name: "The hit" });
    expect(frameLabel()).toBe("Frame 48 · 0:01.60");
    expect(card("Arm straight at the hit").hasAttribute("data-active")).toBe(true);
    expect(card("Side-on to the net").hasAttribute("data-active")).toBe(false);

    fireEvent.click(screen.getByRole("tab", { name: "Getting ready" }));
    expect(frameLabel()).toBe("Frame 9 · 0:00.30");
    expect(screen.getByRole("tab", { name: "Getting ready" }).getAttribute("aria-selected")).toBe("true");
    expect(card("Side-on to the net").hasAttribute("data-active")).toBe(true);
    expect(card("Arm straight at the hit").hasAttribute("data-active")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Show this moment: After the hit" }));
    expect(frameLabel()).toBe("Frame 61 · 0:02.03");
    expect(card("Follow-through across the body").hasAttribute("data-active")).toBe(true);
  });

  it("draws the overlay at the frame each moment tab seeks to", async () => {
    const { container } = render(<LabellingWorkspace batchId="set-1" />);
    await screen.findByRole("tab", { name: "The hit" });
    const canvas = () => container.querySelector("canvas");
    await waitFor(() => expect(canvas()?.getAttribute("data-frame")).toBe("48"));
    fireEvent.click(screen.getByRole("tab", { name: "Getting ready" }));
    expect(canvas()?.getAttribute("data-frame")).toBe("9");
    fireEvent.click(screen.getByRole("button", { name: "Forward ▶" }));
    expect(canvas()?.getAttribute("data-frame")).toBe("10");
    expect((screen.getByLabelText("Show angles") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Show skeleton") as HTMLInputElement).checked).toBe(true);
  });

  it("saves 'can't see' for coach-only questions without pressing save", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    await screen.findByRole("tab", { name: "The hit" });
    fireEvent.click(within(card("Side-on to the net")).getByLabelText("Can't see"));
    fireEvent.change(within(card("Side-on to the net")).getByLabelText("Comment on Side-on to the net"), {
      target: { value: "camera is behind" },
    });
    await waitFor(() => expect(saveClipLabel).toHaveBeenCalled(), { timeout: 2000 });
    const body = saveClipLabel.mock.calls.at(-1)![1];
    expect(body.stats.sideon).toEqual({ rating: "cant_see", comment: "camera is behind" });
  });

  it("saves the overall section and moves to the next clip", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    await screen.findByRole("tab", { name: "The hit" });
    fireEvent.click(screen.getByRole("button", { name: "Forward ▶" }));
    fireEvent.click(screen.getByRole("button", { name: "The real hit is at this frame" }));
    fireEvent.click(within(card("Arm straight at the hit")).getByLabelText("Needs work"));
    fireEvent.click(screen.getByLabelText("OK"));
    fireEvent.change(screen.getByLabelText("Most important thing to fix"), {
      target: { value: "elbow" },
    });
    fireEvent.change(screen.getByLabelText("What would you tell this player?"), {
      target: { value: "Reach up at the hit." },
    });
    fireEvent.change(screen.getByLabelText(/General comment/), {
      target: { value: "Camera a bit far." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save and next clip →" }));
    expect(await screen.findByText("Clip 2 of 2")).toBeTruthy();
    const [id, body] = saveClipLabel.mock.calls.at(-1)!;
    expect(id).toBe("a1");
    expect(body).toMatchObject({
      coach: "Jeff",
      batch_id: "set-1",
      corrected_hit_frame: 49,
      overall_rating: 3,
      most_important_fix: "elbow",
      feedback: "Reach up at the hit.",
      general_comment: "Camera a bit far.",
      stats: { elbow: { rating: "needs_work", comment: "" } },
    });
  });

  it("offers this stroke's questions plus 'Something not listed' as the main fix", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    const select = await screen.findByLabelText("Most important thing to fix");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Choose…",
      "Arm straight at the hit",
      "Hitting high",
      "Something not listed",
    ]);
  });

  it("keeps every control at least 48px tall for tablets", async () => {
    render(<LabellingWorkspace batchId="set-1" />);
    await screen.findByRole("tab", { name: "The hit" });
    const tall = /(?:^|\s)(min-h-(1[2-9]|[2-9]\d)|min-h-\[(4[89]|[5-9]\d)px\]|h-12)(?=\s|$)/;
    const controls = [
      ...screen.getAllByRole("button"),
      ...screen.getAllByRole("tab"),
      ...screen.getAllByRole("radio").map((r) => r.closest("label")!),
      ...screen.getAllByRole("slider"),
      ...screen.getAllByRole("combobox"),
      ...screen.getAllByRole("textbox").filter((t) => t.tagName === "INPUT"),
      ...screen.getAllByRole("checkbox").map((c) => c.closest("label")!),
    ];
    const short = controls
      .filter((el) => !tall.test(el.className))
      .map((el) => el.textContent || el.getAttribute("aria-label"));
    expect(short).toEqual([]);
  });
});
