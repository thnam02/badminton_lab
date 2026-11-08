import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RuleCheck, RuleMatch } from "@/lib/coach";
import { RuleMatchPanel } from "./RuleMatchPanel";

const AGREEMENT = {
  separates_well: "Separates well",
  overlaps: "Overlaps",
  not_enough_data: "Not enough data",
};

function match(overrides: Partial<RuleMatch> = {}): RuleMatch {
  return {
    reviewed_clips: 23,
    answered_clips: 23,
    unanswered_clips: 0,
    fault_clips: 9,
    fine_clips: 14,
    unmeasured: [],
    caught: 9,
    missed: 0,
    false_flags: 4,
    fine_not_flagged: 10,
    balanced_accuracy: 0.86,
    agreement_status: "separates_well",
    suggested: {
      picture_id: "bent",
      label: "Bent",
      value: 120,
      steps_from_choice: -1,
      caught: 8,
      missed: 1,
      false_flags: 1,
      fine_not_flagged: 13,
      balanced_accuracy: 0.91,
    },
    disagreements: [
      { analysis_id: "abc", kind: "false_flag", value: 135.2, frame_index: 48, timestamp: 1.6 },
      { analysis_id: "def", kind: "missed", value: 152, frame_index: 30, timestamp: 1.0 },
    ],
    ...overrides,
  };
}

function check(m: RuleMatch): RuleCheck {
  return {
    supported: true,
    stroke_type: "FOREHAND_CLEAR",
    target: {
      metric_id: "contact_elbow_angle_deg",
      metric_label: "Elbow angle at the hit frame",
      boundary_set: "elbow_angle",
      direction: "flag_below",
      label_question: "bent_elbow",
      label_question_title: "Arm bent at the hit",
      prompt: "Which is the most bent arm you would still accept?",
      flag_hint: "Anything more bent than your choice will be flagged.",
      problem_noun: "bent-arm",
    },
    boundary: { id: "slightly_bent", label: "Slightly bent", value: 140 },
    match: m,
  };
}

function renderPanel(c: RuleCheck | null, onUse = vi.fn(), coach = "Linh") {
  render(
    <RuleMatchPanel
      check={c}
      coach={coach}
      strokeLabel="clear"
      unit="deg"
      agreementLabels={AGREEMENT}
      onUseSuggestion={onUse}
    />
  );
  return onUse;
}

describe("RuleMatchPanel", () => {
  it("states caught, missed and false flags in plain words", () => {
    renderPanel(check(match({ caught: 8, missed: 1 })));
    expect(
      screen.getByText(/You reviewed 23 clear clips and said .Arm bent at the hit. in 9/)
    ).toBeTruthy();
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toBe("Catches 8 of your 9 bent-arm clips and misses 1");
    expect(items[1]).toBe("Also flags 4 clips you said were fine");
    expect(screen.getByText("Separates well")).toBeTruthy();
  });

  it("suggests the best-fitting picture and can apply it", () => {
    const onUse = renderPanel(check(match()));
    expect(screen.getByText(/fits your reviews better: catches 8 of 9, flags 1 fine clip/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use suggestion" }));
    expect(onUse).toHaveBeenCalledWith("bent");
  });

  it("hides the suggestion buttons when the coach keeps their choice", () => {
    renderPanel(check(match()));
    fireEvent.click(screen.getByRole("button", { name: "Keep my choice" }));
    expect(screen.queryByRole("button", { name: "Use suggestion" })).toBeNull();
  });

  it("lists disagreeing clips with links that open at the measured frame", () => {
    renderPanel(check(match()));
    fireEvent.click(screen.getByRole("button", { name: "Show me the 2 clips that disagree" }));
    const list = screen.getByRole("list", { name: "Clips that disagree" });
    const links = within(list).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/analysis/abc?t=1.60",
      "/analysis/def?t=1.00",
    ]);
    expect(links[0].textContent).toBe("Open at 0:01.60");
    expect(list.textContent).toContain("You said fine, rule flags it · measured 135°");
    expect(list.textContent).toContain("You said yes, rule didn't flag it · measured 152°");
  });

  it("says when the rule cannot be measured instead of showing numbers", () => {
    renderPanel({ supported: false, reason: "We don't measure shoulder yet." });
    expect(screen.getByRole("status").textContent).toBe("We don't measure shoulder yet.");
  });

  it("asks for the coach's name and explains when nothing was reviewed", () => {
    renderPanel(check(match()), vi.fn(), " ");
    expect(screen.getByText(/Add your name above/)).toBeTruthy();
  });

  it("explains when no clips were reviewed for this stroke", () => {
    renderPanel(check(match({ reviewed_clips: 0, fault_clips: 0, fine_clips: 0 })));
    expect(screen.getByText(/haven't reviewed any clear clips yet/)).toBeTruthy();
  });
});
