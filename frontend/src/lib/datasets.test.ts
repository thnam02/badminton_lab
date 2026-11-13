// @vitest-environment node
import { describe, expect, it } from "vitest";
import { formatDue, groupByTechnique, sortForCoach, timeLeft } from "./datasets";
import type { DatasetStatus } from "./labelling";
import { summary } from "@/test/fixtures";

function d(number: number, status: DatasetStatus, due_date: string | null) {
  return summary({ number, status, due_date });
}

describe("sortForCoach", () => {
  it("puts overdue first, then the nearest due date, finished datasets last", () => {
    const sorted = sortForCoach([
      d(1, "done", "2026-11-01"),
      d(2, "in_progress", "2026-11-25"),
      d(3, "not_started", null),
      d(4, "overdue", "2026-11-05"),
      d(5, "not_started", "2026-11-12"),
      d(6, "overdue", "2026-11-08"),
    ]);
    expect(sorted.map((s) => s.number)).toEqual([4, 6, 5, 2, 3, 1]);
  });
});

describe("groupByTechnique", () => {
  it("always lists both techniques, keeping the order inside each", () => {
    const groups = groupByTechnique([
      summary({ number: 2 }),
      summary({ number: 1, technique: "FOREHAND_SMASH", dataset_id: "smash-1" }),
      summary({ number: 1 }),
    ]);
    expect(groups.map((g) => [g.label, g.datasets.map((x) => x.dataset_id)])).toEqual([
      ["Forehand clear", ["clear-2", "clear-1"]],
      ["Forehand smash", ["smash-1"]],
    ]);
    expect(groupByTechnique([]).map((g) => g.datasets.length)).toEqual([0, 0]);
  });
});

describe("due dates", () => {
  const today = new Date(2026, 10, 10);
  it("formats as day and short month, with the year only when it differs", () => {
    expect(formatDue("2026-11-20", today)).toBe("20 Nov");
    expect(formatDue("2027-01-05", today)).toBe("5 Jan 2027");
  });

  it("says how long is left, or that it is overdue", () => {
    expect(timeLeft({ status: "in_progress", days_left: 3, due_date: "x" })).toBe("3 days left");
    expect(timeLeft({ status: "not_started", days_left: 1, due_date: "x" })).toBe("1 day left");
    expect(timeLeft({ status: "not_started", days_left: 0, due_date: "x" })).toBe("Due today");
    expect(timeLeft({ status: "overdue", days_left: -2, due_date: "x" })).toBe("Overdue");
    expect(timeLeft({ status: "done", days_left: -2, due_date: "x" })).toBe("");
    expect(timeLeft({ status: "not_started", days_left: null, due_date: null })).toBe("");
  });
});
