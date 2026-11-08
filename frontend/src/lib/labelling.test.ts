import { describe, expect, it } from "vitest";
import { formatStatValue, frameAt, timeOfFrame } from "./labelling";

describe("labelling helpers", () => {
  it("formats stat values in plain units", () => {
    expect(formatStatValue(126.7, "deg")).toBe("127°");
    expect(formatStatValue(0.617, "torso_lengths_above_shoulder")).toBe(
      "0.62 torso lengths above the shoulder"
    );
    expect(formatStatValue(7.87, "torso_lengths_per_s")).toBe("7.9 torso lengths per second");
    expect(formatStatValue(0.6556, "ratio")).toBe("0.66");
    expect(formatStatValue(-0.3, "torso_lengths_above_shoulder")).toBe(
      "0.30 torso lengths below the shoulder"
    );
    expect(formatStatValue(null, "deg")).toBe("Not measured");
  });

  it("seeks to the middle of a frame and reads the same frame back", () => {
    for (const frame of [0, 1, 48, 135, 183]) {
      expect(frameAt(timeOfFrame(frame, 30), 30)).toBe(frame);
    }
    expect(frameAt(4.5, 30)).toBe(135);
  });
});
