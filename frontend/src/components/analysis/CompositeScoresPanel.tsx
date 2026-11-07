import { Card } from "@/components/ui/Card";
import { cardTitle } from "@/components/ui/styles";
import { formatNumber } from "@/lib/format";
import type { CompositeScoresView } from "@/lib/types";

type Props = {
  scores: CompositeScoresView | null | undefined;
};

type ScoreKey = "chain_score" | "power_score" | "base_score";

type ScoreCard = {
  key: ScoreKey;
  label: string;
  hint: string;
};

const BASE: ScoreCard = {
  key: "base_score",
  label: "Base",
  hint: "Preparation load and contact height",
};

const SECONDARY: ScoreCard[] = [
  {
    key: "power_score",
    label: "Power",
    hint: "Speed, finish, and acceleration window",
  },
  {
    key: "chain_score",
    label: "Chain",
    hint: "Sequence & timing from legs through the arm",
  },
];

const MISSING_REASON = "Not enough signal for this score";
const RING_RADIUS = 44;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

function isMissing(value: number | null | undefined): value is null | undefined {
  return value == null || Number.isNaN(value);
}

function formatScore(value: number | null | undefined): string {
  if (isMissing(value)) return "n/a";
  return formatNumber(value * 100, 0);
}

export function CompositeScoresPanel({ scores }: Props) {
  if (!scores?.available) {
    return (
      <Card className="flex flex-col gap-2">
        <h2 className={cardTitle}>Technique scores</h2>
        <p className="text-sm text-text-muted" role="status">
          Scores not available for this analysis.
        </p>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-[18px]">
      <h2 className={cardTitle}>Technique scores</h2>
      <HeroScore card={BASE} value={scores[BASE.key]} />
      <div className="grid grid-cols-2 gap-2.5">
        {SECONDARY.map((card) => (
          <TileScore key={card.key} card={card} value={scores[card.key]} />
        ))}
      </div>
    </Card>
  );
}

function HeroScore({ card, value }: { card: ScoreCard; value: number | null | undefined }) {
  if (isMissing(value)) {
    return <WithheldTile card={card} />;
  }
  const fraction = Math.max(0, Math.min(1, value));
  return (
    <article className="flex items-center gap-5">
      <div className="relative h-[104px] w-[104px] flex-none">
        <svg width="104" height="104" viewBox="0 0 104 104" aria-hidden="true">
          <circle
            cx="52"
            cy="52"
            r={RING_RADIUS}
            fill="none"
            strokeWidth="10"
            className="stroke-border"
          />
          <circle
            cx="52"
            cy="52"
            r={RING_RADIUS}
            fill="none"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${fraction * RING_CIRCUMFERENCE} ${RING_CIRCUMFERENCE}`}
            transform="rotate(-90 52 52)"
            className="stroke-accent"
          />
        </svg>
        <p className="absolute inset-0 flex flex-col items-center justify-center leading-none">
          <span className="font-display text-[28px] font-bold tabular-nums">
            {formatScore(value)}
          </span>
          <span className="mt-1 text-[11px] text-text-muted">/ 100</span>
        </p>
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        <h3 className="font-display text-lg font-semibold">{card.label}</h3>
        <p className="text-[13px] text-text-muted">{card.hint}</p>
      </div>
    </article>
  );
}

function TileScore({ card, value }: { card: ScoreCard; value: number | null | undefined }) {
  if (isMissing(value)) {
    return <WithheldTile card={card} />;
  }
  return (
    <article className="flex flex-col gap-1 rounded-[14px] border border-border bg-surface-2 p-3.5">
      <h3 className="font-display font-semibold">{card.label}</h3>
      <p className="font-display text-2xl font-bold tabular-nums">
        {formatScore(value)}
        <span className="ml-1 text-xs font-medium text-text-muted">/ 100</span>
      </p>
      <p className="text-xs text-text-muted">{card.hint}</p>
    </article>
  );
}

function WithheldTile({ card }: { card: ScoreCard }) {
  return (
    <article className="flex flex-col gap-1 rounded-[14px] border border-dashed border-text-muted/40 bg-surface-2 p-3.5">
      <h3 className="font-display font-semibold">{card.label}</h3>
      <p className="font-display text-lg font-semibold text-text-muted">n/a</p>
      <p className="text-xs text-text-muted">{MISSING_REASON}</p>
    </article>
  );
}
