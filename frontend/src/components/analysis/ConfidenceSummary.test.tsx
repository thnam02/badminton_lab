import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfidenceSummaryPanel, MAX_LIMITATIONS } from "./ConfidenceSummary";
import type { ConfidenceSummary } from "@/lib/types";

const confidence: ConfidenceSummary = {
  overall: "MODERATE",
  overall_score: 0.6,
  components: [],
  message: null,
};

describe("ConfidenceSummaryPanel limitations", () => {
  it("shows at most 3 limitations, keeping the first (highest priority) ones", () => {
    const limitations = ["First", "Second", "Third", "Fourth", "Fifth"];
    render(<ConfidenceSummaryPanel confidence={confidence} limitations={limitations} />);
    const items = within(screen.getByRole("list", { name: "Limitations" }))
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(MAX_LIMITATIONS).toBe(3);
    expect(items).toEqual(["First", "Second", "Third"]);
  });

  it("renders no list when there are no limitations", () => {
    render(<ConfidenceSummaryPanel confidence={confidence} limitations={[]} />);
    expect(screen.queryByRole("list", { name: "Limitations" })).toBeNull();
  });
});
