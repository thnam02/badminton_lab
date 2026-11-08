import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import AnalyzePage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  startAnalyze: vi.fn(),
}));

beforeAll(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

function chooseVideo() {
  const input = screen.getByLabelText(/Drop a video here or choose a file/);
  const file = new File(["x"], "clip.mp4", { type: "video/mp4" });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("AnalyzePage", () => {
  it("has no handedness preselected and keeps submit disabled until one is chosen", () => {
    render(<AnalyzePage />);
    const hand = screen.getByRole("group", { name: /Which hand holds the racket/ });
    for (const radio of within(hand).getAllByRole("radio")) {
      expect((radio as HTMLInputElement).checked).toBe(false);
    }
    const submit = screen.getByRole("button", { name: /Start analysis/ });
    expect((submit as HTMLButtonElement).disabled).toBe(true);

    chooseVideo();
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Select the player's handedness in Step 2 to start.")).toBeTruthy();

    fireEvent.click(within(hand).getByLabelText("Left-handed"));
    expect((submit as HTMLButtonElement).disabled).toBe(false);
  });

  it("marks Side as recommended and other camera views as limited", () => {
    render(<AnalyzePage />);
    const view = screen.getByRole("group", { name: "Where was the camera?" });
    expect(within(view).getByLabelText(/Side/).closest("label")?.textContent).toContain(
      "Recommended"
    );
    for (const name of ["Front", "Behind", "Not sure"]) {
      expect(within(view).getByLabelText(new RegExp(name)).closest("label")?.textContent).toContain(
        "Limited analysis"
      );
    }
  });

  it("explains how to film next to the camera question", () => {
    render(<AnalyzePage />);
    const view = screen.getByRole("group", { name: "Where was the camera?" });
    const guidanceId = view.getAttribute("aria-describedby");
    expect(guidanceId).toBe("camera-view-guidance");
    expect(document.getElementById(guidanceId!)?.textContent).toContain(
      "Film from the side, at hip height, with your whole body in view."
    );
    expect(screen.getByText("Side view at hip height (recommended)")).toBeTruthy();
  });

  it("lists unavailable strokes as coming soon, not as choices", () => {
    render(<AnalyzePage />);
    expect(screen.getByText("Drop · coming soon")).toBeTruthy();
    expect(screen.queryByRole("radio", { name: /Drop/ })).toBeNull();
  });
});
