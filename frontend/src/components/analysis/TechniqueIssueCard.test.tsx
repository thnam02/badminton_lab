import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TechniqueIssueCard } from "./TechniqueIssueCard";
import { sortFindingsByPriority } from "@/lib/techniqueCopy";
import type { TechniqueIssueView } from "@/lib/types";

function issue(overrides: Partial<TechniqueIssueView> = {}): TechniqueIssueView {
  return {
    code: "LOW_CONTACT_POINT",
    title: "Low contact point",
    phase: "ESTIMATED_CONTACT",
    phase_label: "Estimated contact",
    status: "MODERATE",
    confidence: 0.8,
    confidence_label: "HIGH",
    measured_value: 0.05,
    unit: "normalized_y",
    reference_profile_id: "smash_right_side_provisional_v1",
    explanation: "",
    is_finding: true,
    is_insufficient_evidence: false,
    tier: 1,
    reference_validated: false,
    tentative: true,
    ...overrides,
  };
}

describe("TechniqueIssueCard tiered rules", () => {
  it("marks tentative issues as hints and uses tiered copy", () => {
    render(<TechniqueIssueCard issue={issue()} variant="main" />);
    expect(screen.getByText("Contact may be below head height")).toBeTruthy();
    expect(screen.getByText("Tentative hint")).toBeTruthy();
    expect(screen.getByText("hand stayed below head height around contact")).toBeTruthy();
    fireEvent.click(screen.getByText("View evidence"));
    expect(screen.getByText("Tier 1 (principle)")).toBeTruthy();
  });

  it("shows no tentative badge for untiered legacy issues", () => {
    render(
      <TechniqueIssueCard
        issue={issue({
          code: "INSUFFICIENT_ELBOW_EXTENSION",
          unit: "deg",
          measured_value: 133,
          tier: null,
          reference_validated: null,
          tentative: false,
        })}
        variant="main"
      />
    );
    expect(screen.getByText("Extend more at contact")).toBeTruthy();
    expect(screen.queryByText("Tentative hint")).toBeNull();
  });
});

describe("sortFindingsByPriority", () => {
  it("ranks Tier 2 hints after Tier 1 findings", () => {
    const sorted = sortFindingsByPriority([
      issue({ code: "BENT_ELBOW_AT_CONTACT", tier: 2, status: "MINOR", confidence: 0.99 }),
      issue({ code: "LATE_ELBOW_ACCELERATION", tier: 1, status: "MINOR", confidence: 0.5 }),
    ]);
    expect(sorted.map((i) => i.code)).toEqual(["LATE_ELBOW_ACCELERATION", "BENT_ELBOW_AT_CONTACT"]);
  });
});
