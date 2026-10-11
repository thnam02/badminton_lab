import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CompositeScoresPanel } from "./CompositeScoresPanel";

describe("CompositeScoresPanel", () => {
  it("shows n/a for a null score instead of 0", () => {
    render(
      <CompositeScoresPanel
        scores={{ available: true, chain_score: 0.82, power_score: null, base_score: 0.5 }}
      />
    );
    const power = screen.getByText("Power").closest("article");
    expect(power?.textContent).toContain("n/a");
    expect(power?.textContent).toContain("Not enough signal for this score");
    expect(power?.textContent).not.toContain("/ 100");
    const chain = screen.getByText("Chain").closest("article");
    expect(chain?.textContent).toContain("82");
    expect(chain?.textContent).toContain("/ 100");
  });

  it("shows the unavailable message when scores are missing", () => {
    render(<CompositeScoresPanel scores={null} />);
    expect(screen.getByRole("status").textContent).toBe(
      "Scores not available for this analysis."
    );
  });
});
