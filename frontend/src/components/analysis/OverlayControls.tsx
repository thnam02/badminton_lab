"use client";

type OverlayMode = {
  id: string;
  label: string;
  available: boolean;
  toggleable?: boolean;
  note?: string;
};

type Props = {
  modes: OverlayMode[];
};

/** Minimal overlay listing — kept under Technical details on the result page. */
export function OverlayControls({ modes }: Props) {
  if (!modes.length) {
    return (
      <p className="text-sm text-text-muted">
        No overlay metadata for this analysis.
      </p>
    );
  }

  return (
    <ul className="space-y-2 text-sm">
      {modes.map((mode) => (
        <li key={mode.id} className="text-text-muted">
          <span className="font-medium text-text">{mode.label}</span>
          {mode.note ? ` — ${mode.note}` : ""}
          {!mode.toggleable ? " (baked into analysis video)" : ""}
        </li>
      ))}
      <li className="text-xs text-text-muted">
        3D mesh (WHAM) stays experimental and is hidden from the product path.
      </li>
    </ul>
  );
}
