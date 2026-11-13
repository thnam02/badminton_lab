"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type ReactNode } from "react";
import { CheckCircleIcon } from "@/components/ui/icons";
import { formatTimestamp } from "@/lib/format";
import { frameAt, timeOfFrame } from "@/lib/labelling";

export type HitFinderHandle = {
  /** Pause and show this frame. */
  seekTo: (frame: number) => void;
};

type Props = {
  videoUrl: string | null;
  overlayUrl: string | null;
  fps: number;
  frameCount: number;
  systemFrame: number | null;
  /** Coach-corrected hit frame; null means the app's hit is used. */
  hitFrame: number | null;
  onMarkHit: (frame: number) => void;
  onUseSystemHit: () => void;
  onFrameChange?: (frame: number) => void;
  /** Drawn over the video, e.g. the pose overlay canvas. */
  renderOverlay?: (frame: number, videoSize: { width: number; height: number } | null) => ReactNode;
  /** Extra controls shown above the slider, e.g. overlay toggles. */
  controls?: ReactNode;
};

type FrameCallbackVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number, meta: { mediaTime: number }) => void) => number;
  cancelVideoFrameCallback?: (handle: number) => void;
};

const SLOW_RATE = 0.25;
const bigButton =
  "inline-flex min-h-[52px] items-center justify-center gap-2 rounded-[14px] px-3 text-base font-semibold transition disabled:cursor-not-allowed disabled:opacity-40";

export const HitFinder = forwardRef<HitFinderHandle, Props>(function HitFinder(
  {
    videoUrl,
    overlayUrl,
    fps,
    frameCount,
    systemFrame,
    hitFrame,
    onMarkHit,
    onUseSystemHit,
    onFrameChange,
    renderOverlay,
    controls,
  },
  ref
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const startFrame = hitFrame ?? systemFrame ?? 0;
  const [frame, setFrameState] = useState(startFrame);
  const [playing, setPlaying] = useState(false);
  const [rawFailed, setRawFailed] = useState(false);
  const [videoSize, setVideoSize] = useState<{ width: number; height: number } | null>(null);
  const lastFrame = Math.max(frameCount - 1, 0);
  const src = rawFailed || !videoUrl ? overlayUrl ?? videoUrl : videoUrl;

  function setFrame(f: number) {
    setFrameState(f);
    onFrameChange?.(f);
  }

  useEffect(() => {
    setFrame(startFrame);
    // Only when a new clip loads; later marks must not move the playhead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoUrl, overlayUrl]);

  function seek(target: number) {
    const f = Math.min(Math.max(Math.round(target), 0), lastFrame);
    const video = videoRef.current;
    if (video) {
      video.pause();
      video.currentTime = timeOfFrame(f, fps);
    }
    setPlaying(false);
    setFrame(f);
  }

  useImperativeHandle(ref, () => ({ seekTo: seek }));

  // Follow every decoded frame while playing so the overlay stays in step.
  useEffect(() => {
    const video = videoRef.current as FrameCallbackVideo | null;
    if (!playing || !video?.requestVideoFrameCallback) return;
    let handle = 0;
    const tick = (_now: number, meta: { mediaTime: number }) => {
      setFrame(Math.min(frameAt(meta.mediaTime, fps), lastFrame));
      handle = video.requestVideoFrameCallback!(tick);
    };
    handle = video.requestVideoFrameCallback(tick);
    return () => video.cancelVideoFrameCallback?.(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, fps, lastFrame]);

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (playing) {
      video.pause();
      setPlaying(false);
      return;
    }
    video.playbackRate = SLOW_RATE;
    void video.play();
    setPlaying(true);
  }

  const marked = hitFrame != null;
  const atFrame = (f: number) => `frame ${f} (${formatTimestamp(f / fps)})`;

  return (
    <div className="flex flex-col overflow-hidden rounded-[22px] border border-border bg-surface">
      <div className="relative bg-black">
        {src ? (
          <video
            ref={videoRef}
            key={src}
            src={src}
            playsInline
            muted
            preload="auto"
            className="block max-h-[70vh] w-full object-contain"
            onLoadedMetadata={(e) => {
              const v = e.currentTarget;
              setVideoSize({ width: v.videoWidth, height: v.videoHeight });
              v.currentTime = timeOfFrame(frame, fps);
            }}
            onTimeUpdate={(e) => {
              const v = e.currentTarget as FrameCallbackVideo;
              if (playing && !v.requestVideoFrameCallback) {
                setFrame(Math.min(frameAt(v.currentTime, fps), lastFrame));
              }
            }}
            onPause={() => setPlaying(false)}
            onError={() => {
              if (src === videoUrl && overlayUrl && overlayUrl !== videoUrl) setRawFailed(true);
            }}
          />
        ) : (
          <p className="flex aspect-video items-center justify-center text-text-muted" role="status">
            Video not available for this clip.
          </p>
        )}
        {src && renderOverlay?.(frame, videoSize)}
        <span className="absolute left-3 top-3 rounded-lg bg-bg/85 px-3 py-1.5 text-sm font-semibold tabular-nums">
          Frame {frame} · {formatTimestamp(frame / fps)}
        </span>
      </div>

      <div className="flex flex-col gap-3 px-[18px] pb-[18px] pt-4">
        {controls}
        <input
          type="range"
          min={0}
          max={lastFrame}
          value={frame}
          aria-label="Move through the clip"
          onChange={(e) => seek(Number(e.target.value))}
          className="h-12 w-full accent-accent"
        />
        <div className="grid grid-cols-3 gap-2">
          <button
            type="button"
            className={`${bigButton} border-2 border-border bg-surface-2 text-text`}
            onClick={() => seek(frame - 1)}
            disabled={frame <= 0}
          >
            ◀ Back
          </button>
          <button
            type="button"
            className={`${bigButton} bg-text text-bg hover:bg-text-soft`}
            onClick={togglePlay}
            aria-pressed={playing}
          >
            {playing ? "❚❚ Pause" : "▶ Slow"}
          </button>
          <button
            type="button"
            className={`${bigButton} border-2 border-border bg-surface-2 text-text`}
            onClick={() => seek(frame + 1)}
            disabled={frame >= lastFrame}
          >
            Forward ▶
          </button>
        </div>

        <button
          type="button"
          className={`${bigButton} min-h-14 bg-accent font-bold text-bg hover:bg-accent-soft`}
          onClick={() => onMarkHit(frame)}
        >
          The real hit is at this frame
        </button>

        <div className="flex flex-col gap-2">
          <p className="flex items-start gap-2 text-sm text-accent-soft" role="status">
            <CheckCircleIcon className="mt-0.5 flex-none text-accent" size={18} />
            {marked
              ? `Hit marked at ${atFrame(hitFrame)}.`
              : systemFrame != null
                ? `Using the app's hit at ${atFrame(systemFrame)}. Mark another frame if it's wrong.`
                : "The app didn't find a hit. Find it and mark it."}
          </p>
          <div className="flex flex-wrap gap-2">
            {systemFrame != null && (
              <button
                type="button"
                className={`${bigButton} min-h-12 border-2 border-border bg-surface-2 text-sm text-text`}
                onClick={() => seek(systemFrame)}
              >
                Go to the app&apos;s hit
              </button>
            )}
            {marked && (
              <button
                type="button"
                className={`${bigButton} min-h-12 border-2 border-border bg-surface-2 text-sm text-text`}
                onClick={onUseSystemHit}
              >
                Use the app&apos;s hit instead
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});
