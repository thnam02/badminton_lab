import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AnalyzePage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", () => ({ startAnalyze: vi.fn() }));

describe("AnalyzePage camera guidance", () => {
  it("recommends a side view next to the camera-view dropdown", () => {
    render(<AnalyzePage />);
    const select = screen.getByRole("combobox", { name: /Camera view/ });
    expect(screen.getByRole("option", { name: "Side (recommended)" })).toBeTruthy();
    expect(screen.getByText("Side recommended")).toBeTruthy();
    const guidanceId = select.getAttribute("aria-describedby");
    expect(guidanceId).toBe("camera-view-guidance");
    expect(document.getElementById(guidanceId!)?.textContent).toContain(
      "Film from the side, at hip height, with your whole body in view."
    );
  });
});
