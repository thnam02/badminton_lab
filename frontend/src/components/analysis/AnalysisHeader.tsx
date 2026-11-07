import Link from "next/link";
import { WarnIcon } from "@/components/ui/icons";
import { buttonSecondary, chip, pageTitle } from "@/components/ui/styles";
import { cameraViewLabel, confidenceLabel, formatDate } from "@/lib/format";
import type { AnalysisResult, ConfidenceLevel } from "@/lib/types";

type Props = {
  analysis: AnalysisResult;
  videoUrl?: string | null;
};

function confidenceChipClass(level: ConfidenceLevel): string {
  if (level === "HIGH") {
    return "inline-flex items-center rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-[13px] text-accent-soft";
  }
  if (level === "LOW") {
    return "inline-flex items-center rounded-full border border-warn/45 bg-warn/10 px-3 py-1 text-[13px] text-warn";
  }
  return chip;
}

export function AnalysisHeader({ analysis, videoUrl }: Props) {
  const view = cameraViewLabel(analysis.camera_view);

  return (
    <header className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <nav aria-label="Breadcrumb">
            <ol className="flex items-center gap-2 text-[13px] text-text-muted">
              <li>
                <Link
                  href="/history"
                  className="inline-flex min-h-11 items-center text-text-muted hover:text-text"
                >
                  History
                </Link>
              </li>
              <li aria-hidden="true">/</li>
              <li aria-current="page">Analysis</li>
            </ol>
          </nav>
          <h1 className={pageTitle}>{analysis.stroke_type}</h1>
          <ul aria-label="Analysis details" className="mt-1 flex flex-wrap gap-2">
            {analysis.handedness && <li className={chip}>{analysis.handedness}</li>}
            {view && <li className={chip}>{view}</li>}
            <li className={chip}>{formatDate(analysis.created_at)}</li>
            {analysis.confidence && (
              <li className={confidenceChipClass(analysis.confidence.overall)}>
                Analysis confidence: {confidenceLabel(analysis.confidence.overall)}
              </li>
            )}
          </ul>
        </div>
        <div className="flex flex-wrap gap-2">
          {videoUrl && (
            <a href={videoUrl} download className={buttonSecondary}>
              Download video
            </a>
          )}
          <Link
            href={`/compare?left=${encodeURIComponent(analysis.analysis_id)}`}
            className={buttonSecondary}
          >
            Compare with…
          </Link>
        </div>
      </div>
      {analysis.analysis_status !== "COMPLETE" && (
        <p
          className="flex items-start gap-2 rounded-xl border border-warn/45 bg-warn/10 px-4 py-3 text-sm text-warn"
          role="status"
        >
          <WarnIcon className="mt-[3px] flex-none" />
          This analysis is partial — some artifacts may be missing.
        </p>
      )}
    </header>
  );
}
