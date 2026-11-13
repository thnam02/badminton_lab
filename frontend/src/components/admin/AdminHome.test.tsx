import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DatasetSummary } from "@/lib/labelling";
import { summary } from "@/test/fixtures";
import { AdminHome } from "./AdminHome";

const fetchDatasets = vi.fn<() => Promise<DatasetSummary[]>>();

vi.mock("@/lib/labelling", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/labelling")>()),
  fetchDatasets: () => fetchDatasets(),
}));

beforeEach(() => {
  fetchDatasets.mockReset();
});

describe("AdminHome", () => {
  it("lists datasets per technique with videos, progress, due date and status", async () => {
    fetchDatasets.mockResolvedValue([
      summary({ number: 1, status: "overdue", due_date: "2026-11-05", days_left: -5, labelled_count: 3 }),
      summary({ number: 2, status: "in_progress", labelled_count: 2, processing_count: 3 }),
    ]);
    render(<AdminHome />);
    const clears = await screen.findByRole("region", { name: "Forehand clear" });
    const rows = within(clears).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getByRole("link").textContent)).toEqual(["Dataset 1", "Dataset 2"]);
    expect(within(rows[0]).getByRole("link").getAttribute("href")).toBe("/admin/datasets/clear-1");

    expect(rows[0].getAttribute("data-status")).toBe("overdue");
    expect(rows[0].textContent).toContain("3/8");
    expect(rows[0].textContent).toContain("Due 5 Nov · Overdue");
    expect(rows[1].textContent).toContain("3 processing");
    expect(rows[1].textContent).toContain("In progress");
    const bar = within(rows[1]).getByRole("progressbar");
    expect([bar.getAttribute("aria-valuenow"), bar.getAttribute("aria-valuemax")]).toEqual(["2", "8"]);

    const smashes = screen.getByRole("region", { name: "Forehand smash" });
    expect(within(smashes).getByText("No datasets yet.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Create dataset" }).getAttribute("href")).toBe(
      "/admin/datasets/new"
    );
  });
});
