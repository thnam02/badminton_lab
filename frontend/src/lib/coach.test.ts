import { describe, expect, it } from "vitest";
import { FIGURE, elbowHand, formatBoundaryValue, heightWrist, kneeHip } from "./coach";

describe("picture geometry is drawn from the boundary values", () => {
  it("matches the design's elbow pictures", () => {
    // Design forearm end points for 100° and 180°.
    expect(elbowHand(100).x).toBeCloseTo(15.5, 1);
    expect(elbowHand(100).y).toBeCloseTo(63.9, 1);
    expect(elbowHand(180)).toEqual({ x: 50, y: 35 });
  });

  it("bends further as the angle drops", () => {
    const xs = [100, 120, 140, 160, 180].map((a) => elbowHand(a).x);
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
    expect(kneeHip(180).x).toBeCloseTo(55, 6);
    expect(kneeHip(100).x).toBeLessThan(kneeHip(140).x);
  });

  it("places the hand by torso lengths above the shoulder", () => {
    expect(heightWrist(0).y).toBeCloseTo(FIGURE.shoulder.y, 6);
    expect(heightWrist(0.35).y).toBeCloseTo(FIGURE.shoulder.y - 0.35 * FIGURE.torso, 6);
    expect(heightWrist(-0.3).y).toBeGreaterThan(FIGURE.shoulder.y);
  });

  it("formats values in plain units", () => {
    expect(formatBoundaryValue(135.4, "deg")).toBe("135°");
    expect(formatBoundaryValue(0.35, "torso_lengths_above_shoulder")).toBe(
      "0.35 torso lengths above the shoulder"
    );
    expect(formatBoundaryValue(-0.3, "torso_lengths_above_shoulder")).toBe(
      "0.30 torso lengths below the shoulder"
    );
  });
});
