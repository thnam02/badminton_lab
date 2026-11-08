"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { PageContainer } from "@/components/shell/PageContainer";
import { Card } from "@/components/ui/Card";
import { ArrowRightIcon } from "@/components/ui/icons";
import { buttonPrimary, pageTitle } from "@/components/ui/styles";
import { startAnalyze, type CameraView, type Handedness } from "@/lib/api";

const ACCEPTED = ".mp4,.mov,video/mp4,video/quicktime";

const STAGES = [
  { id: "prepare", label: "Preparing video" },
  { id: "pose", label: "Detecting body pose" },
  { id: "motion", label: "Analysing movement" },
  { id: "phases", label: "Finding stroke phases" },
  { id: "technique", label: "Evaluating technique" },
  { id: "coaching", label: "Generating coaching" },
] as const;

type StrokeOption = {
  id: string;
  label: string;
  available: boolean;
  apiValue?: string;
};

const STROKES: StrokeOption[] = [
  {
    id: "forehand_smash",
    label: "Forehand smash",
    available: true,
    apiValue: "FOREHAND_SMASH",
  },
  {
    id: "forehand_clear",
    label: "Forehand clear",
    available: true,
    apiValue: "FOREHAND_CLEAR",
  },
  { id: "drop", label: "Drop", available: false },
  { id: "serve", label: "Serve", available: false },
  { id: "net", label: "Net shot", available: false },
  { id: "lift", label: "Lift", available: false },
];

const HANDEDNESS_OPTIONS: { value: Handedness; label: string }[] = [
  { value: "RIGHT", label: "Right-handed" },
  { value: "LEFT", label: "Left-handed" },
  { value: "UNKNOWN", label: "Not sure" },
];

const CAMERA_VIEW_OPTIONS: { value: CameraView; label: string; note: string }[] = [
  { value: "SIDE", label: "Side", note: "Recommended" },
  { value: "FRONT", label: "Front", note: "Limited analysis" },
  { value: "REAR", label: "Behind", note: "Limited analysis" },
  { value: "UNKNOWN", label: "Not sure", note: "Limited analysis" },
];

const CAMERA_VIEW_GUIDANCE =
  "Film from the side, at hip height, with your whole body in view. Front, behind or \"Not sure\" allow only limited analysis.";

const FILMING_TIPS = [
  "Keep your full body visible",
  "Use a static camera",
  "Side view at hip height (recommended)",
  "60 FPS recommended",
  "Good lighting",
];

const radioCard =
  "flex cursor-pointer border-2 transition has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent";
const radioCardOn = "border-accent bg-accent/10";
const radioCardOff = "border-border bg-surface-2 hover:border-text-muted/50";
const radioInput = "h-[18px] w-[18px] flex-none accent-accent focus-visible:outline-none";

export default function AnalyzePage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [stroke, setStroke] = useState("forehand_smash");
  const [handedness, setHandedness] = useState<Handedness | "">("");
  const [cameraView, setCameraView] = useState<CameraView>("UNKNOWN");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [meta, setMeta] = useState<{
    duration?: number;
    width?: number;
    height?: number;
  }>({});
  const [loading, setLoading] = useState(false);
  const [stageIndex, setStageIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [analysisReadyId, setAnalysisReadyId] = useState<string | null>(null);
  const [coachingPending, setCoachingPending] = useState(false);
  const [dragging, setDragging] = useState(false);

  const canUpload = Boolean(file) && handedness !== "";
  const fileSizeLabel = useMemo(() => {
    if (!file) return "";
    const mb = file.size / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  }, [file]);

  function onFileChange(selected: File | null) {
    setError(null);
    setAnalysisReadyId(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (!selected) {
      setFile(null);
      setPreviewUrl(null);
      setMeta({});
      return;
    }
    const lower = selected.name.toLowerCase();
    if (!lower.endsWith(".mp4") && !lower.endsWith(".mov")) {
      setError("Please choose an .mp4 or .mov video.");
      return;
    }
    setFile(selected);
    const url = URL.createObjectURL(selected);
    setPreviewUrl(url);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.src = url;
    video.onloadedmetadata = () => {
      setMeta({
        duration: video.duration,
        width: video.videoWidth,
        height: video.videoHeight,
      });
    };
  }

  async function runAnalyze() {
    if (!file || handedness === "") return;
    setLoading(true);
    setError(null);
    setStageIndex(0);
    setAnalysisReadyId(null);
    setCoachingPending(false);

    const timer = window.setInterval(() => {
      setStageIndex((i) => Math.min(i + 1, STAGES.length - 2));
    }, 1800);

    try {
      const selected = STROKES.find((s) => s.id === stroke);
      const data = await startAnalyze(file, {
        meshOverlay: false,
        strokeType: selected?.apiValue || "FOREHAND_SMASH",
        handedness,
        cameraView,
      });
      window.clearInterval(timer);
      setStageIndex(STAGES.length - 1);
      const id = data.analysis_id;
      setAnalysisReadyId(id);
      const coachingDone =
        !data.coaching_status ||
        data.coaching_status === "COMPLETE" ||
        data.coaching_status === "ok";
      setCoachingPending(!coachingDone);
      // Deterministic analysis is ready — navigate even if coaching is soft-unavailable.
      router.push(`/analysis/${id}`);
    } catch (err) {
      window.clearInterval(timer);
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  const disabledReason = !file
    ? "Choose a video in Step 1 to start."
    : handedness === ""
      ? "Select the player's handedness in Step 2 to start."
      : null;

  return (
    <PageContainer className="gap-8">
      <header className="flex max-w-[720px] flex-col gap-2.5">
        <h1 className={pageTitle}>Analyze a stroke</h1>
        <p className="text-[17px] text-text-muted">
          Choose forehand smash or forehand clear, then upload a clip for
          technique analysis.
        </p>
      </header>

      <div className="flex flex-wrap items-start gap-6">
        <form
          className="flex min-w-0 flex-[999_1_600px] flex-col gap-5"
          onSubmit={(e) => {
            e.preventDefault();
            void runAnalyze();
          }}
        >
          <Card className="flex flex-col gap-4 p-6 sm:p-7">
            <StepHeading n={1} id="step-video">
              Your video
            </StepHeading>
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                onFileChange(e.dataTransfer.files?.[0] ?? null);
              }}
              className={`flex cursor-pointer flex-col items-center gap-2.5 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${
                dragging
                  ? "border-accent bg-accent/10"
                  : "border-text-muted/40 bg-bg hover:border-accent"
              }`}
            >
              <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true" className="text-accent">
                <rect x="6" y="10" width="22" height="20" rx="4" stroke="currentColor" strokeWidth="2" />
                <path d="M28 17l7-4v14l-7-4" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
              </svg>
              <span className="font-semibold">
                {file ? "Choose a different video" : "Drop a video here or choose a file"}
              </span>
              <span className="text-[13px] text-text-muted">
                MP4 or MOV. 60 fps works best.
              </span>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPTED}
                aria-describedby="step-video"
                className="sr-only"
                onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
              />
            </label>
            {file && (
              <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                <div className="min-w-0">
                  <dt className="text-text-muted">Filename</dt>
                  <dd className="truncate font-medium">{file.name}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">File size</dt>
                  <dd className="font-medium">{fileSizeLabel}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Duration</dt>
                  <dd className="font-medium">
                    {meta.duration ? `${meta.duration.toFixed(1)} s` : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-text-muted">Resolution</dt>
                  <dd className="font-medium">
                    {meta.width && meta.height
                      ? `${meta.width}×${meta.height}`
                      : "—"}
                  </dd>
                </div>
              </dl>
            )}
            {previewUrl && (
              <video
                src={previewUrl}
                controls
                className="aspect-video w-full rounded-xl border border-border bg-black"
              />
            )}
          </Card>

          <Card className="flex flex-col gap-6 p-6 sm:p-7">
            <StepHeading n={2}>About the clip</StepHeading>

            <fieldset className="flex flex-col gap-2.5">
              <legend className="mb-2.5 font-semibold">
                Which hand holds the racket?{" "}
                <span className="text-[13px] font-medium text-warn">Required</span>
              </legend>
              <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(160px,1fr))]">
                {HANDEDNESS_OPTIONS.map((o) => (
                  <label
                    key={o.value}
                    className={`${radioCard} items-center gap-2.5 rounded-xl px-4 py-3.5 ${
                      handedness === o.value ? radioCardOn : radioCardOff
                    }`}
                  >
                    <input
                      type="radio"
                      name="handedness"
                      value={o.value}
                      required
                      checked={handedness === o.value}
                      onChange={() => setHandedness(o.value)}
                      className={radioInput}
                    />
                    {o.label}
                  </label>
                ))}
              </div>
            </fieldset>

            <fieldset
              className="flex flex-col gap-2.5"
              aria-describedby="camera-view-guidance"
            >
              <legend className="mb-2.5 font-semibold">Where was the camera?</legend>
              <p id="camera-view-guidance" className="-mt-1 text-[13px] text-text-muted">
                {CAMERA_VIEW_GUIDANCE}
              </p>
              <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(130px,1fr))]">
                {CAMERA_VIEW_OPTIONS.map((o) => (
                  <label
                    key={o.value}
                    className={`${radioCard} flex-col gap-1 rounded-xl px-4 py-3.5 ${
                      cameraView === o.value ? radioCardOn : radioCardOff
                    }`}
                  >
                    <span className="flex items-center gap-2.5">
                      <input
                        type="radio"
                        name="camera_view"
                        value={o.value}
                        checked={cameraView === o.value}
                        onChange={() => setCameraView(o.value)}
                        className={radioInput}
                      />
                      {o.label}
                    </span>
                    <span
                      className={`text-xs ${
                        o.value === "SIDE" ? "text-accent-soft" : "text-text-muted"
                      }`}
                    >
                      {o.note}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </Card>

          <Card className="flex flex-col gap-5 p-6 sm:p-7">
            <StepHeading n={3}>Stroke</StepHeading>
            <fieldset>
              <legend className="sr-only">Stroke</legend>
              <div className="flex flex-wrap gap-2.5">
                {STROKES.filter((s) => s.available).map((s) => (
                  <label
                    key={s.id}
                    className={`${radioCard} items-center gap-2.5 rounded-full px-[18px] py-3 ${
                      stroke === s.id ? radioCardOn : radioCardOff
                    }`}
                  >
                    <input
                      type="radio"
                      name="stroke"
                      value={s.id}
                      checked={stroke === s.id}
                      onChange={() => setStroke(s.id)}
                      className={radioInput}
                    />
                    {s.label}
                  </label>
                ))}
                {STROKES.filter((s) => !s.available).map((s) => (
                  <span
                    key={s.id}
                    className="flex items-center rounded-full border-2 border-dashed border-border px-[18px] py-3 text-text-muted"
                  >
                    {s.label} · coming soon
                  </span>
                ))}
              </div>
            </fieldset>
          </Card>

          <div className="flex flex-wrap items-center justify-between gap-4">
            <p id="start-hint" className="max-w-[460px] text-[13px] text-text-muted">
              {loading ? "Analyzing your clip…" : disabledReason}
            </p>
            <button
              type="submit"
              disabled={!canUpload || loading}
              aria-describedby={disabledReason ? "start-hint" : undefined}
              className={`${buttonPrimary} px-7 py-3 text-base`}
            >
              {loading ? "Analyzing…" : "Start analysis"}
              {!loading && <ArrowRightIcon />}
            </button>
          </div>

          {loading && (
            <Card as="div" className="p-5">
              <ol className="flex flex-col gap-2" aria-live="polite">
                {STAGES.map((stage, idx) => {
                  const done = idx < stageIndex;
                  const current = idx === stageIndex;
                  return (
                    <li key={stage.id} className="flex items-center gap-3 text-sm">
                      <span
                        aria-hidden
                        className={`w-4 text-center ${done || current ? "text-accent" : "text-text-muted"}`}
                      >
                        {done ? "✓" : current ? "●" : "○"}
                      </span>
                      <span
                        className={
                          current ? "font-semibold text-text" : "text-text-muted"
                        }
                      >
                        {stage.label}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </Card>
          )}

          {analysisReadyId && coachingPending && (
            <p className="text-sm text-text-muted" role="status">
              Your movement analysis is ready.{" "}
              <Link href={`/analysis/${analysisReadyId}`} className="font-medium">
                View results
              </Link>{" "}
              while coaching finishes.
            </p>
          )}

          {error && (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          )}
        </form>

        <Card
          as="aside"
          aria-labelledby="filming-guide"
          className="flex min-w-0 flex-[1_1_340px] flex-col gap-[18px] p-6 sm:p-7"
        >
          <h2 id="filming-guide" className="font-display text-xl font-semibold">
            How to film for the best result
          </h2>
          <FilmingDiagram />
          <ul className="flex flex-col gap-3 text-text-soft">
            {FILMING_TIPS.map((tip, i) => (
              <li key={tip} className="flex gap-2.5">
                <span className="font-bold text-accent" aria-hidden>
                  {i + 1}
                </span>
                {tip}
              </li>
            ))}
          </ul>
          <p className="border-t border-border pt-3.5 text-[13px] text-text-muted">
            Front and behind views still work, but some checks can&apos;t be
            measured from those angles.
          </p>
        </Card>
      </div>
    </PageContainer>
  );
}

function StepHeading({
  n,
  id,
  children,
}: {
  n: number;
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <span
        aria-hidden
        className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-sm font-bold text-bg"
      >
        {n}
      </span>
      <h2 id={id} className="font-display text-xl font-semibold">
        <span className="sr-only">Step {n}: </span>
        {children}
      </h2>
    </div>
  );
}

function FilmingDiagram() {
  return (
    <svg
      viewBox="0 0 320 170"
      className="w-full"
      role="img"
      aria-label="Top-down view of a court half: the camera sits to the side of the player, level with them"
    >
      <rect x="1" y="1" width="318" height="168" rx="14" className="fill-bg stroke-border" />
      <path d="M30 130H290M30 40H290M30 40V130M290 40V130M160 40V130" className="stroke-border" strokeWidth="2" />
      <circle cx="210" cy="85" r="12" fill="none" strokeWidth="3" className="stroke-accent" />
      <path d="M210 73V58" strokeWidth="3" strokeLinecap="round" className="stroke-accent" />
      <rect x="196" y="146" width="28" height="18" rx="4" fill="none" strokeWidth="2.5" className="stroke-warn" />
      <path d="M210 146 210 104" strokeWidth="2" strokeDasharray="4 4" className="stroke-warn" />
    </svg>
  );
}
