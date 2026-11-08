"use client";

import { useEffect, useRef, useState } from "react";
import { buildOverlay, contentRect, drawOverlay, type PoseFeed } from "@/lib/overlay";

type Props = {
  pose: PoseFeed | null;
  frame: number;
  /** Intrinsic video size, for placing points inside the letterboxed picture. */
  videoSize: { width: number; height: number } | null;
  showSkeleton: boolean;
  showAngles: boolean;
  highlight: ReadonlySet<string>;
};

/** Canvas drawn over the video element, matching its box exactly. */
export function PoseOverlay({ pose, frame, videoSize, showSkeleton, showAngles, highlight }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [box, setBox] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const measure = () => setBox({ w: canvas.clientWidth, h: canvas.clientHeight });
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    canvas.width = Math.round(box.w * dpr);
    canvas.height = Math.round(box.h * dpr);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!pose || (!showSkeleton && !showAngles)) return;
    const rect = contentRect(
      box.w * dpr,
      box.h * dpr,
      videoSize?.width ?? 0,
      videoSize?.height ?? 0
    );
    drawOverlay(ctx, buildOverlay(pose, frame, rect, { showSkeleton, showAngles, highlight }), dpr);
  }, [pose, frame, box, videoSize, showSkeleton, showAngles, highlight]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      data-frame={frame}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}
