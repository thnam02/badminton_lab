import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PoseFeed } from "@/lib/overlay";
import { PoseOverlay } from "./PoseOverlay";

const NAMES = [
  "nose", "left_eye", "right_eye", "left_ear", "right_ear",
  "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
  "left_wrist", "right_wrist", "left_hip", "right_hip",
  "left_knee", "right_knee", "left_ankle", "right_ankle",
];

function points(): ([number, number, number] | null)[] {
  const at: Record<string, [number, number, number]> = {
    left_shoulder: [0.45, 0.3, 0.9],
    right_shoulder: [0.55, 0.3, 0.9],
    right_elbow: [0.6, 0.22, 0.9],
    right_wrist: [0.58, 0.1, 0.9],
    right_hip: [0.54, 0.55, 0.9],
    right_knee: [0.56, 0.7, 0.9],
    right_ankle: [0.58, 0.9, 0.9],
  };
  return NAMES.map((n) => at[n] ?? null);
}

const POSE: PoseFeed = {
  fps: 30,
  frame_count: 2,
  keypoint_names: NAMES,
  confidence_threshold: 0.5,
  frames: [
    { frame_index: 48, points: points(), angles: { right_elbow: 126.2, right_knee: 158 } },
    { frame_index: 49, points: points(), angles: { right_elbow: 131.0, right_knee: 159 } },
  ],
};

function recorder() {
  const texts: string[] = [];
  const ctx = new Proxy(
    { fillText: (t: string) => texts.push(t), measureText: () => ({ width: 30 }) } as Record<string, unknown>,
    { get: (target, key) => (key in target ? target[key as string] : () => undefined), set: () => true }
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    ctx as unknown as CanvasRenderingContext2D
  );
  return texts;
}

afterEach(() => {
  vi.restoreAllMocks();
});

const props = {
  pose: POSE,
  videoSize: { width: 1080, height: 1920 },
  showSkeleton: true,
  showAngles: true,
  highlight: new Set(["right_shoulder", "right_elbow", "right_wrist"]),
};

describe("PoseOverlay", () => {
  it("draws the angles of the current frame and redraws when the frame changes", () => {
    const texts = recorder();
    const { container, rerender } = render(<PoseOverlay {...props} frame={48} />);
    expect(container.querySelector("canvas")?.getAttribute("data-frame")).toBe("48");
    expect(texts).toContain("126°");
    expect(texts).not.toContain("131°");

    texts.length = 0;
    rerender(<PoseOverlay {...props} frame={49} />);
    expect(container.querySelector("canvas")?.getAttribute("data-frame")).toBe("49");
    expect(texts).toEqual(expect.arrayContaining(["131°", "159°", "Shoulders"]));
  });

  it("draws no text with angles switched off", () => {
    const texts = recorder();
    render(<PoseOverlay {...props} frame={48} showAngles={false} />);
    expect(texts).toEqual([]);
  });
});
