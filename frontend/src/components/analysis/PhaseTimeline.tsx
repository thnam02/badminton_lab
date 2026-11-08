"use client";

import type { PhaseSegment } from "@/lib/types";
import { formatTimestamp } from "@/lib/format";
import { cardTitle } from "@/components/ui/styles";

type Props = {
  phases: PhaseSegment[];
  currentTime: number;
  onSeek: (seconds: number) => void;
  contactTimestamp?: number | null;
  contactShuttleVerified?: boolean;
};

export function PhaseTimeline({
  phases,
  currentTime,
  onSeek,
  contactTimestamp,
  contactShuttleVerified = false,
}: Props) {
  if (!phases.length) {
    return (
      <p className="text-sm text-text-muted" role="status">
        Stroke phase timeline is not available for this analysis.
      </p>
    );
  }

  const start = Math.min(...phases.map((p) => p.start_timestamp));
  const end = Math.max(...phases.map((p) => p.end_timestamp));
  const span = Math.max(end - start, 0.001);
  const pct = (t: number) => Math.max(0, Math.min(100, ((t - start) / span) * 100));

  const active = phases.find(
    (p) => currentTime >= p.start_timestamp && currentTime <= p.end_timestamp + 0.02
  );

  // The contact moment gets its own marker; its zero-length segment only
  // needs a button when there is no marker to seek with.
  const buttons = phases.filter(
    (p) => !(p.is_contact_event && contactTimestamp != null)
  );
  const minShare = span * 0.06;

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className={cardTitle}>Stroke timeline</h2>
        <p className="text-[13px] text-text-muted" aria-live="polite">
          {active ? active.label : "Tap a phase to jump there"} ·{" "}
          {formatTimestamp(currentTime)}
        </p>
      </div>

      <div className="relative h-11">
        <div
          className="absolute inset-x-0 top-1/2 flex h-2 -translate-y-1/2 gap-0.5 overflow-hidden rounded-full"
          aria-hidden
        >
          {phases
            .filter((p) => !p.is_contact_event)
            .map((p) => (
              <div
                key={`bar-${p.id}-${p.start_timestamp}`}
                className={active?.id === p.id ? "bg-accent" : "bg-border"}
                style={{
                  flexGrow: Math.max(p.end_timestamp - p.start_timestamp, 0.0001),
                  flexBasis: 0,
                }}
              />
            ))}
        </div>
        <div
          className="pointer-events-none absolute top-1/2 z-10 h-5 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-text"
          style={{ left: `${pct(currentTime)}%` }}
          aria-hidden
        />
        {contactTimestamp != null && (
          <button
            type="button"
            aria-label={`Seek to ${contactShuttleVerified ? "" : "estimated "}contact at ${formatTimestamp(contactTimestamp)}`}
            className="absolute top-0 z-20 flex h-11 w-11 -translate-x-1/2 items-center justify-center rounded-full"
            style={{ left: `${pct(contactTimestamp)}%` }}
            onClick={() => onSeek(contactTimestamp)}
          >
            <span
              className={`block h-3.5 w-3.5 rounded-full ring-2 ring-surface ${
                contactShuttleVerified ? "bg-accent" : "bg-warn"
              }`}
            />
          </button>
        )}
      </div>

      <ul aria-label="Stroke phases" className="grid grid-cols-2 gap-1 sm:flex">
        {buttons.map((phase) => {
          const isActive = active?.id === phase.id;
          return (
            <li
              key={`${phase.id}-${phase.start_timestamp}`}
              className="min-w-0 sm:basis-0"
              style={{
                flexGrow: Math.max(phase.end_timestamp - phase.start_timestamp, minShare),
              }}
            >
              <button
                type="button"
                aria-label={`${phase.label}, ${formatTimestamp(phase.start_timestamp)} to ${formatTimestamp(phase.end_timestamp)}, confidence ${Math.round(phase.confidence * 100)} percent`}
                aria-current={isActive ? "true" : undefined}
                className={`flex min-h-11 w-full flex-col justify-center rounded-lg border px-2 py-2 text-left text-xs transition ${
                  isActive
                    ? "border-accent bg-accent font-semibold text-bg"
                    : "border-border bg-surface-2 text-text hover:border-accent"
                }`}
                onClick={() => onSeek(phase.seek_timestamp)}
              >
                <span className="truncate">{phase.label}</span>
                <span
                  className={`text-[11px] tabular-nums ${isActive ? "text-bg" : "text-text-muted"}`}
                >
                  {formatTimestamp(phase.start_timestamp)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
