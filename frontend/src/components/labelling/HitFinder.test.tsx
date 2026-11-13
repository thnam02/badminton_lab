import { act, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { HitFinder, type HitFinderHandle } from "./HitFinder";

function renderFinder(hitFrame: number | null = null) {
  const onMarkHit = vi.fn();
  const onUseSystemHit = vi.fn();
  const onFrameChange = vi.fn();
  const ref = createRef<HitFinderHandle>();
  render(
    <HitFinder
      ref={ref}
      videoUrl="/raw.mp4"
      overlayUrl="/overlay.mp4"
      fps={30}
      frameCount={184}
      systemFrame={135}
      hitFrame={hitFrame}
      onMarkHit={onMarkHit}
      onUseSystemHit={onUseSystemHit}
      onFrameChange={onFrameChange}
    />
  );
  return { onMarkHit, onUseSystemHit, onFrameChange, ref };
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
    const { onMarkHit, onFrameChange } = renderFinder();
    fireEvent.click(screen.getByRole("button", { name: "Forward ▶" }));
    fireEvent.click(screen.getByRole("button", { name: "Forward ▶" }));
    fireEvent.click(screen.getByRole("button", { name: "◀ Back" }));
    expect(screen.getByText("Frame 136 · 0:04.53")).toBeTruthy();
    expect(onFrameChange).toHaveBeenLastCalledWith(136);
    fireEvent.click(screen.getByRole("button", { name: "The real hit is at this frame" }));
    expect(onMarkHit).toHaveBeenCalledWith(136);
  });

  it("seeks when asked from outside (moment tabs)", () => {
    const { ref, onFrameChange } = renderFinder();
    act(() => ref.current?.seekTo(30));
    expect(screen.getByText("Frame 30 · 0:01.00")).toBeTruthy();
    expect(onFrameChange).toHaveBeenLastCalledWith(30);
    act(() => ref.current?.seekTo(500));
    expect(screen.getByText("Frame 183 · 0:06.10")).toBeTruthy();
  });

  it("can move with the slider and return to the app's hit", () => {
    renderFinder();
    fireEvent.change(screen.getByLabelText("Move through the clip"), {
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
});
