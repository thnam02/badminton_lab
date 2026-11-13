import { describe, expect, it } from "vitest";
import { describeStatValue, formatStatValue, frameAt, timeOfFrame } from "./labelling";

describe("labelling helpers", () => {
  it("formats values compactly, as on the review cards", () => {
    expect(formatStatValue(126.7, "deg")).toBe("127°");
    expect(formatStatValue(0.617, "torso_lengths_above_shoulder")).toBe("0.62 above");
    expect(formatStatValue(-0.3, "torso_lengths_above_shoulder")).toBe("0.30 below");
    expect(formatStatValue(1, "yes_no")).toBe("Yes");
    expect(formatStatValue(0, "yes_no")).toBe("No");
    expect(formatStatValue(7.87, "torso_lengths_per_s")).toBe("7.9 torso/s");
    expect(formatStatValue(0.6556, "ratio")).toBe("0.66");
    expect(formatStatValue(null, "deg")).toBe("Not measured");
  });

  it("describes values in full for screen readers and tooltips", () => {
    expect(describeStatValue(0.617, "torso_lengths_above_shoulder")).toBe(
      "0.62 torso lengths above the shoulder"
    );
    expect(describeStatValue(7.87, "torso_lengths_per_s")).toBe("7.9 torso lengths per second");
    expect(describeStatValue(126.7, "deg")).toBe("127°");
  });

  it("seeks to the middle of a frame and reads the same frame back", () => {
    for (const frame of [0, 1, 48, 135, 183]) {
      expect(frameAt(timeOfFrame(frame, 30), 30)).toBe(frame);
    }
    expect(frameAt(4.5, 30)).toBe(135);
  });
});
