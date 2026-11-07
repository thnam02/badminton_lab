import { Card } from "@/components/ui/Card";
import { eyebrow } from "@/components/ui/styles";
import type { Drill } from "@/lib/types";
import { issueTitleFromCode } from "@/lib/format";

type Props = {
  drill: Drill;
};

export function DrillCard({ drill }: Props) {
  return (
    <Card aria-labelledby="drill-title" className="flex flex-col gap-3.5">
      <p className={eyebrow}>Drill for your next session</p>
      <h2 id="drill-title" className="font-display text-[22px] font-semibold">
        {drill.title}
      </h2>
      {drill.repetitions && (
        <p className="text-sm font-medium text-accent-soft">{drill.repetitions}</p>
      )}
      <p className="leading-relaxed text-text-soft">{drill.goal || drill.instructions}</p>
      {drill.related_issue && (
        <p className="text-[13px] text-text-muted">
          Targets: {issueTitleFromCode(drill.related_issue)}
        </p>
      )}
    </Card>
  );
}
