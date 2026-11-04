import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricsPanel } from "./MetricsPanel";

describe("MetricsPanel display metrics", () => {
  it("lists Tier 3 metrics under a reference-only section", () => {
    render(
      <MetricsPanel
        metrics={[{ id: "phase_confidence", label: "Phase confidence", value: 0.9, unit: "" }]}
        displayMetrics={[
          { id: "peak_trunk_rotation_deg", label: "Trunk rotation (2D)", value: 20, unit: "deg" },
          {
            id: "peak_trunk_rotation_velocity_deg_s",
            label: "Trunk rotation speed (during the hit)",
            value: 343,
            unit: "deg/s",
            note: "Low reliability in 2D video.",
          },
        ]}
      />
    );
    const section = screen.getByRole("region", { name: "For reference only" });
    expect(within(section).getByText("Trunk rotation (2D)")).toBeTruthy();
    expect(within(section).getByText("20.0°")).toBeTruthy();
    expect(within(section).getByText("343.0 deg/s")).toBeTruthy();
    expect(within(section).getByText("Low reliability in 2D video.")).toBeTruthy();
    expect(within(section).queryByText("Phase confidence")).toBeNull();
    expect(screen.getByText("Phase confidence")).toBeTruthy();
  });

  it("omits the section when there are no display metrics", () => {
    render(
      <MetricsPanel metrics={[{ id: "phase_confidence", label: "Phase confidence", value: 0.9, unit: "" }]} />
    );
    expect(screen.queryByRole("region", { name: "For reference only" })).toBeNull();
  });
});
