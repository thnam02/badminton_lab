import { describe, expect, it } from "vitest";
import { buildOverlay, contentRect, type PoseFeed } from "./overlay";

const NAMES = [
  "nose", "left_eye", "right_eye", "left_ear", "right_ear",
  "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
  "left_wrist", "right_wrist", "left_hip", "right_hip",
  "left_knee", "right_knee", "left_ankle", "right_ankle",
];

type Pt = [number, number, number];

function frame(index: number, elbow: number, overrides: Partial<Record<string, Pt | null>> = {}) {
  const base: Record<string, Pt> = {
    nose: [0.5, 0.2, 0.9],
    left_shoulder: [0.45, 0.3, 0.9],
    right_shoulder: [0.55, 0.3, 0.9],
    left_elbow: [0.42, 0.4, 0.9],
    right_elbow: [0.6, 0.22, 0.9],
    left_wrist: [0.4, 0.5, 0.9],
    right_wrist: [0.58, 0.1, 0.9],
    left_hip: [0.46, 0.55, 0.9],
    right_hip: [0.54, 0.55, 0.9],
    left_knee: [0.45, 0.7, 0.9],
    right_knee: [0.56, 0.7, 0.9],
    left_ankle: [0.45, 0.9, 0.9],
    right_ankle: [0.58, 0.9, 0.9],
  };
  const all = { ...base, ...overrides };
  return {
    frame_index: index,
    points: NAMES.map((n) => (n in all ? (all[n] as Pt | null) : null)),
    angles: { right_elbow: elbow, right_knee: 158 },
  };
}

const POSE: PoseFeed = {
  fps: 30,
  frame_count: 3,
  keypoint_names: NAMES,
  confidence_threshold: 0.5,
  frames: [frame(47, 120.4), frame(48, 126.2), frame(49, 130.0, { right_wrist: [0.7, 0.15, 0.9] })],
};

const ALL = { showSkeleton: true, showAngles: true, highlight: new Set<string>() };

describe("contentRect", () => {
  it("fits a portrait video inside a landscape box with side bars", () => {
    expect(contentRect(800, 450, 1080, 1920)).toEqual({
      x: (800 - 253.125) / 2,
      y: 0,
      w: 253.125,
      h: 450,
    });
  });

  it("fits a landscape video inside a portrait box with top and bottom bars", () => {
    const r = contentRect(400, 700, 1920, 1080);
    expect(r.w).toBe(400);
    expect(r.h).toBeCloseTo(225);
    expect(r.y).toBeCloseTo((700 - 225) / 2);
  });
});

describe("buildOverlay", () => {
  const rect = { x: 100, y: 0, w: 200, h: 400 };

  it("uses the requested frame's points and saved angles", () => {
    const at48 = buildOverlay(POSE, 48, rect, ALL);
    expect(at48.frameIndex).toBe(48);
    expect(at48.labels.filter((l) => l.tone === "angle").map((l) => l.text)).toEqual(["126°", "158°"]);
    const elbow = at48.joints.find((j) => j.name === "right_elbow")!;
    expect(elbow.at).toEqual({ x: 100 + 0.6 * 200, y: 0.22 * 400 });

    const at49 = buildOverlay(POSE, 49, rect, ALL);
    expect(at49.labels.find((l) => l.tone === "angle")!.text).toBe("130°");
    expect(at49.joints.find((j) => j.name === "right_wrist")!.at.x).toBe(100 + 0.7 * 200);
  });

  it("draws nothing for a frame without pose", () => {
    const none = buildOverlay(POSE, 99, rect, ALL);
    expect(none.frameIndex).toBeNull();
    expect(none.segments).toEqual([]);
  });

  it("draws the shoulder line and an arc per angle", () => {
    const shapes = buildOverlay(POSE, 48, rect, ALL);
    expect(shapes.shoulderLine).not.toBeNull();
    const tag = shapes.labels.find((l) => l.text === "Shoulders")!;
    // On the non-racket (left_shoulder) side, ending just before the line.
    expect(tag.align).toBe("end");
    expect(tag.at.x).toBeLessThan(shapes.joints.find((j) => j.name === "left_shoulder")!.at.x);
    expect(shapes.arcs).toHaveLength(2);
    for (const arc of shapes.arcs) expect(arc.end).toBeGreaterThan(arc.start);
  });

  it("highlights only the joints of the selected moment's questions", () => {
    const shapes = buildOverlay(POSE, 48, rect, {
      ...ALL,
      highlight: new Set(["right_shoulder", "right_elbow", "right_wrist"]),
    });
    const lit = shapes.segments.filter((s) => s.highlight);
    expect(lit).toHaveLength(2);
    expect(shapes.arcs.map((a) => a.highlight)).toEqual([true, false]);
    expect(shapes.labels.filter((l) => l.highlight).map((l) => l.text)).toEqual(["126°"]);
    expect(shapes.joints.filter((j) => j.highlight).map((j) => j.name).sort()).toEqual([
      "right_elbow",
      "right_shoulder",
      "right_wrist",
    ]);
  });

  it("respects the angle and skeleton toggles", () => {
    const anglesOnly = buildOverlay(POSE, 48, rect, { ...ALL, showSkeleton: false });
    expect(anglesOnly.segments).toEqual([]);
    expect(anglesOnly.labels.length).toBeGreaterThan(0);
    const skeletonOnly = buildOverlay(POSE, 48, rect, { ...ALL, showAngles: false });
    expect(skeletonOnly.labels).toEqual([]);
    expect(skeletonOnly.shoulderLine).toBeNull();
    expect(skeletonOnly.segments.length).toBeGreaterThan(0);
  });

  it("skips joints the pose model was unsure about", () => {
    const pose: PoseFeed = {
      ...POSE,
      frames: [frame(48, 126, { right_wrist: [0.58, 0.1, 0.2] })],
    };
    const shapes = buildOverlay(pose, 48, rect, ALL);
    expect(shapes.joints.some((j) => j.name === "right_wrist")).toBe(false);
    expect(shapes.labels.filter((l) => l.tone === "angle").map((l) => l.text)).toEqual(["158°"]);
  });
});
