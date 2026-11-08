"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircleIcon } from "@/components/ui/icons";
import { formatTimestamp } from "@/lib/format";
import { frameAt, timeOfFrame } from "@/lib/labelling";

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
};

const SLOW_RATE = 0.25;
const bigButton =
  "inline-flex min-h-16 items-center justify-center gap-2 rounded-2xl px-4 text-lg font-semibold transition disabled:cursor-not-allowed disabled:opacity-40";

export function HitFinder({
  videoUrl,
  overlayUrl,
  fps,
  frameCount,
  systemFrame,
  hitFrame,
  onMarkHit,
  onUseSystemHit,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const startFrame = hitFrame ?? systemFrame ?? 0;
  const [frame, setFrame] = useState(startFrame);
  const [playing, setPlaying] = useState(false);
  const [showSkeleton, setShowSkeleton] = useState(!videoUrl || videoUrl === overlayUrl);
  const [rawFailed, setRawFailed] = useState(false);
  const lastFrame = Math.max(frameCount - 1, 0);
  const src = showSkeleton || rawFailed || !videoUrl ? overlayUrl ?? videoUrl : videoUrl;
  const canToggleSkeleton = Boolean(videoUrl && overlayUrl && videoUrl !== overlayUrl && !rawFailed);

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
    <div className="flex flex-col overflow-hidden rounded-card border border-border bg-surface">
      <div className="relative bg-black">
        {src ? (
          <video
            ref={videoRef}
            key={src}
            src={src}
            playsInline
            muted
            preload="auto"
            className="aspect-video w-full"
            onLoadedMetadata={(e) => {
              e.currentTarget.currentTime = timeOfFrame(frame, fps);
            }}
            onTimeUpdate={(e) => {
              if (playing) setFrame(Math.min(frameAt(e.currentTarget.currentTime, fps), lastFrame));
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
        <span className="absolute left-3 top-3 rounded-lg bg-bg/85 px-3 py-1.5 text-base font-semibold tabular-nums">
          Frame {frame} · {formatTimestamp(frame / fps)}
        </span>
      </div>

      <div className="flex flex-col gap-4 p-5">
        <div className="grid grid-cols-3 gap-2.5">
          <button
            type="button"
            className={`${bigButton} border-2 border-border bg-surface-2 text-text`}
            onClick={() => seek(frame - 1)}
            disabled={frame <= 0}
          >
            ◀ Back a little
          </button>
          <button
            type="button"
            className={`${bigButton} bg-text text-bg hover:bg-text-soft`}
            onClick={togglePlay}
            aria-pressed={playing}
          >
            {playing ? "❚❚ Pause" : "▶ Play slowly"}
          </button>
          <button
            type="button"
            className={`${bigButton} border-2 border-border bg-surface-2 text-text`}
            onClick={() => seek(frame + 1)}
            disabled={frame >= lastFrame}
          >
            Forward a little ▶
          </button>
        </div>

        <label className="flex flex-col gap-1.5 text-base text-text-muted">
          Or drag to move through the clip
          <input
            type="range"
            min={0}
            max={lastFrame}
            value={frame}
            onChange={(e) => seek(Number(e.target.value))}
            className="h-12 w-full accent-accent"
          />
        </label>

        <button
          type="button"
          className={`${bigButton} min-h-[72px] bg-accent text-xl font-bold text-bg hover:bg-accent-soft`}
          onClick={() => onMarkHit(frame)}
        >
          This is the hit
        </button>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2.5 text-base text-accent-soft" role="status">
            <CheckCircleIcon className="flex-none text-accent" />
            {marked
              ? `Hit marked at ${atFrame(hitFrame)}.`
              : systemFrame != null
                ? `Using the app's hit at ${atFrame(systemFrame)}. Mark another frame if it's wrong.`
                : "The app didn't find a hit. Find it and press “This is the hit”."}
          </p>
          <div className="flex flex-wrap gap-2">
            {systemFrame != null && (
              <button
                type="button"
                className={`${bigButton} min-h-12 border-2 border-border bg-surface-2 text-base text-text`}
                onClick={() => seek(systemFrame)}
              >
                Go to the app&apos;s hit
              </button>
            )}
            {marked && (
              <button
                type="button"
                className={`${bigButton} min-h-12 border-2 border-border bg-surface-2 text-base text-text`}
                onClick={onUseSystemHit}
              >
                Use the app&apos;s hit instead
              </button>
            )}
          </div>
        </div>

        {canToggleSkeleton && (
          <label className="flex min-h-12 cursor-pointer items-center gap-3 text-base text-text-soft">
            <input
              type="checkbox"
              checked={showSkeleton}
              onChange={(e) => setShowSkeleton(e.target.checked)}
              className="h-6 w-6 accent-accent"
            />
            Show the app&apos;s skeleton on the video
          </label>
        )}
      </div>
    </div>
  );
}
