import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HitFinder } from "./HitFinder";

function renderFinder(hitFrame: number | null = null) {
  const onMarkHit = vi.fn();
  const onUseSystemHit = vi.fn();
  render(
    <HitFinder
      videoUrl="/raw.mp4"
      overlayUrl="/overlay.mp4"
      fps={30}
      frameCount={184}
      systemFrame={135}
      hitFrame={hitFrame}
      onMarkHit={onMarkHit}
      onUseSystemHit={onUseSystemHit}
    />
  );
  return { onMarkHit, onUseSystemHit };
}

describe("HitFinder", () => {
  it("starts at the app's hit and says it is being used", () => {
    renderFinder();
    expect(screen.getByText("Frame 135 · 0:04.50")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain(
      "Using the app's hit at frame 135 (0:04.50)"
    );
    expect(screen.queryByRole("button", { name: "Use the app's hit instead" })).toBeNull();
  });

  it("steps one frame at a time and marks the frame on screen", () => {
    const { onMarkHit } = renderFinder();
    fireEvent.click(screen.getByRole("button", { name: "Forward a little ▶" }));
    fireEvent.click(screen.getByRole("button", { name: "Forward a little ▶" }));
    fireEvent.click(screen.getByRole("button", { name: "◀ Back a little" }));
    expect(screen.getByText("Frame 136 · 0:04.53")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "This is the hit" }));
    expect(onMarkHit).toHaveBeenCalledWith(136);
  });

  it("can move with the slider and return to the app's hit", () => {
    renderFinder();
    fireEvent.change(screen.getByLabelText("Or drag to move through the clip"), {
      target: { value: "40" },
    });
    expect(screen.getByText("Frame 40 · 0:01.33")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to the app's hit" }));
    expect(screen.getByText("Frame 135 · 0:04.50")).toBeTruthy();
  });

  it("shows a corrected hit and lets the coach go back to the app's", () => {
    const { onUseSystemHit } = renderFinder(140);
    expect(screen.getByRole("status").textContent).toContain("Hit marked at frame 140");
    fireEvent.click(screen.getByRole("button", { name: "Use the app's hit instead" }));
    expect(onUseSystemHit).toHaveBeenCalled();
  });

  it("offers the skeleton overlay when a raw video is kept", () => {
    renderFinder();
    const video = document.querySelector("video");
    expect(video?.getAttribute("src")).toBe("/raw.mp4");
    fireEvent.click(screen.getByLabelText("Show the app's skeleton on the video"));
    expect(document.querySelector("video")?.getAttribute("src")).toBe("/overlay.mp4");
  });
});
