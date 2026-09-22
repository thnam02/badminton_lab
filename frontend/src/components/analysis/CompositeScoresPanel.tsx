import { formatNumber } from "@/lib/format";
import type { CompositeScoresView } from "@/lib/types";

type Props = {
  scores: CompositeScoresView | null | undefined;
};

const CARDS: {
  key: "chain_score" | "power_score" | "base_score";
  label: string;
  hint: string;
}[] = [
  {
    key: "chain_score",
    label: "Chain",
    hint: "Sequence & timing from legs through the arm",
  },
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
        {CARDS.map((card) => {
          const raw = scores[card.key];
          const missing = raw == null || Number.isNaN(raw);
          return (
            <article
              key={card.key}
              className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4"
            >
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                {card.label}
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
