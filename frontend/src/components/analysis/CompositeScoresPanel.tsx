import { formatNumber } from "@/lib/format";
import { BETA_SCORE_TOOLTIP, CHAIN_NOT_ASSESSABLE } from "@/lib/scores";
import type { CompositeScoresView } from "@/lib/types";

type Props = {
  scores: CompositeScoresView | null | undefined;
};

const BETA_CARDS: {
  key: "power_score" | "base_score";
  label: string;
  hint: string;
}[] = [
  {
    key: "power_score",
    label: "Power",
    hint: "Speed, finish, and acceleration window",
  },
  {
    key: "base_score",
    label: "Base",
    hint: "Preparation load and contact height",
  },
];

function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "n/a";
  return formatNumber(value * 100, 0);
}

export function BetaBadge() {
  return (
    <span
      title={BETA_SCORE_TOOLTIP}
      aria-label={`Beta: ${BETA_SCORE_TOOLTIP}`}
      className="ml-2 rounded-full border border-[var(--border)] px-1.5 py-0.5 text-[0.65rem] font-semibold normal-case tracking-normal text-[var(--muted)]"
    >
      Beta
    </span>
  );
}

export function CompositeScoresPanel({ scores }: Props) {
  if (!scores?.available) {
    return (
      <section className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          Technique scores
        </h2>
        <p className="mt-2 text-sm text-[var(--muted)]" role="status">
          Scores not available for this analysis.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
        Technique scores
      </h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <article className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg)] p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Chain
          </p>
          <p className="mt-2 text-base font-semibold text-[var(--fg)]">
            {CHAIN_NOT_ASSESSABLE}
          </p>
          <p className="mt-2 text-xs leading-snug text-[var(--muted)]">
            Sequence timing from legs through the arm needs 3D body landmarks.
          </p>
        </article>
        {BETA_CARDS.map((card) => {
          const raw = scores[card.key];
          const missing = raw == null || Number.isNaN(raw);
          return (
            <article
              key={card.key}
              className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4"
            >
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                {card.label}
                <BetaBadge />
              </p>
              <p className="font-display mt-2 text-3xl font-semibold tabular-nums">
                {formatScore(raw)}
                {!missing && (
                  <span className="ml-1 text-base font-medium text-[var(--muted)]">
                    / 100
                  </span>
                )}
              </p>
              <p className="mt-2 text-xs leading-snug text-[var(--muted)]">
                {missing ? "Not enough signal for this score" : card.hint}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
