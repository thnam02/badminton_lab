import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CoachRuleInput, RuleCheck, RuleOptions } from "@/lib/coach";
import { CoachRuleBuilder } from "./CoachRuleBuilder";

const OPTIONS: RuleOptions = {
  moments: [
    { id: "preparation", label: "Getting ready" },
    { id: "backswing_end", label: "Racket back" },
    { id: "contact", label: "The hit" },
    { id: "follow_through", label: "Follow-through" },
  ],
  body_parts: [
    { id: "elbow", label: "Hitting arm (elbow)" },
    { id: "shoulder", label: "Shoulder" },
  ],
  boundary_sets: {
    elbow_angle: {
      unit: "deg",
      pictures: [
        { id: "very_bent", label: "Very bent", value: 100 },
        { id: "bent", label: "Bent", value: 120 },
        { id: "slightly_bent", label: "Slightly bent", value: 140 },
        { id: "nearly_straight", label: "Nearly straight", value: 160 },
        { id: "straight", label: "Straight", value: 180 },
      ],
    },
  },
  targets: [
    {
      body_part: "elbow",
      moment: "contact",
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
  ],
  importance: [
    { id: "tip", label: "A small tip", severity_cap: "MINOR" },
    { id: "worth_fixing", label: "Worth fixing", severity_cap: "MODERATE" },
    { id: "must_fix_first", label: "Must fix first", severity_cap: "MAJOR" },
  ],
  agreement_labels: {
    separates_well: "Separates well",
    overlaps: "Overlaps",
    not_enough_data: "Not enough data",
  },
};

const checkCoachRule = vi.fn<(rule: CoachRuleInput) => Promise<RuleCheck>>();
const saveCoachRule = vi.fn();

vi.mock("@/lib/coach", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/coach")>()),
  fetchRuleOptions: () => Promise.resolve(OPTIONS),
  checkCoachRule: (rule: CoachRuleInput) => checkCoachRule(rule),
  saveCoachRule: (rule: CoachRuleInput) => saveCoachRule(rule),
}));

function supported(status: "separates_well" | "not_enough_data"): RuleCheck {
  return {
    supported: true,
    stroke_type: "FOREHAND_CLEAR",
    target: OPTIONS.targets[0],
    boundary: OPTIONS.boundary_sets.elbow_angle.pictures[2],
    match: {
      reviewed_clips: 12,
      answered_clips: 12,
      unanswered_clips: 0,
      fault_clips: 6,
      fine_clips: 6,
      unmeasured: [],
      caught: 6,
      missed: 0,
      false_flags: 1,
      fine_not_flagged: 5,
      balanced_accuracy: 0.92,
      agreement_status: status,
      suggested: null,
      disagreements: [],
    },
  };
}

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("badminton-lab.coach-name", "Linh");
  checkCoachRule.mockReset();
  saveCoachRule.mockReset();
});

describe("CoachRuleBuilder", () => {
  it("draws one picture per configured boundary and checks the chosen one", async () => {
    checkCoachRule.mockResolvedValue(supported("not_enough_data"));
    render(<CoachRuleBuilder />);
    const group = await screen.findByRole("group", {
      name: "Which is the most bent arm you would still accept?",
    });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(5);
    expect((within(group).getByLabelText("Slightly bent") as HTMLInputElement).checked).toBe(true);
    await screen.findByText(/Catches 6 of your 6/);
    expect(checkCoachRule).toHaveBeenLastCalledWith(
      expect.objectContaining({ coach: "Linh", body_part: "elbow", boundary_id: "slightly_bent" })
    );
  });

  it("only allows 'Must fix first' when the rule separates well", async () => {
    checkCoachRule.mockResolvedValue(supported("not_enough_data"));
    render(<CoachRuleBuilder />);
    await screen.findByText(/Catches 6 of your 6/);
    expect((screen.getByLabelText("Must fix first") as HTMLInputElement).disabled).toBe(true);
  });

  it("enables 'Must fix first' once the rule separates well", async () => {
    checkCoachRule.mockResolvedValue(supported("separates_well"));
    render(<CoachRuleBuilder />);
    await screen.findByText(/Catches 6 of your 6/);
    expect((screen.getByLabelText("Must fix first") as HTMLInputElement).disabled).toBe(false);
  });

  it("says so and blocks saving when no metric matches", async () => {
    checkCoachRule.mockResolvedValue({
      supported: false,
      reason: "We don't measure shoulder yet, so this rule can't be checked or saved.",
    });
    render(<CoachRuleBuilder />);
    fireEvent.click(await screen.findByLabelText("Shoulder"));
    expect(
      (await screen.findAllByText(/We don't measure shoulder yet/)).length
    ).toBeGreaterThan(0);
    const save = screen.getByRole("button", { name: "Send to the team as a draft" });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/can't be saved because we have no measurement/)).toBeTruthy();
    expect(saveCoachRule).not.toHaveBeenCalled();
  });
});
