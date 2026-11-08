import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CompositeScoresPanel } from "./CompositeScoresPanel";

describe("CompositeScoresPanel", () => {
  it("shows n/a for a null score instead of 0", () => {
    render(
      <CompositeScoresPanel
        scores={{ available: true, chain_score: null, power_score: null, base_score: null }}
      />
    );
    const base = screen.getByText("Base").closest("article");
    expect(base?.textContent).toContain("n/a");
    expect(base?.textContent).toContain("Not enough signal for this score");
    expect(base?.textContent).not.toContain("/ 100");
  });

  it("never shows a chain score, even if one is supplied", () => {
    render(
      <CompositeScoresPanel
        scores={{ available: true, chain_score: 0.82, power_score: 0.4, base_score: 0.5 }}
      />
    );
    const chain = screen.getByText("Chain").closest("article");
    expect(chain?.textContent).toContain("Not assessable from 2D video");
    expect(chain?.textContent).not.toContain("82");
    expect(chain?.textContent).not.toContain("Beta");
  });

  it("never shows a power score, even if one is supplied", () => {
    render(
      <CompositeScoresPanel
        scores={{ available: true, chain_score: null, power_score: 0.47, base_score: 0.5 }}
      />
    );
    const power = screen.getByText("Power").closest("article");
    expect(power?.textContent).toContain("Speed scale not yet calibrated");
    expect(power?.textContent).not.toContain("47");
    expect(power?.textContent).not.toContain("/ 100");
    expect(power?.textContent).not.toContain("Beta");
  });

  it("labels Base as Beta with the provisional-targets tooltip", () => {
    render(
      <CompositeScoresPanel
        scores={{ available: true, chain_score: null, power_score: null, base_score: 0.5 }}
      />
    );
    const badges = screen.getAllByText("Beta");
    expect(badges).toHaveLength(1);
    expect(badges[0].getAttribute("title")).toBe(
      "Based on provisional targets, not yet validated by coaches."
    );
    const base = screen.getByText("Base").closest("article");
    expect(base?.textContent).toContain("Beta");
    expect(base?.textContent).toContain("50");
    expect(base?.textContent).toContain("/ 100");
  });

  it("shows the unavailable message when scores are missing", () => {
    render(<CompositeScoresPanel scores={null} />);
    expect(screen.getByRole("status").textContent).toBe(
      "Scores not available for this analysis."
    );
  });
});
