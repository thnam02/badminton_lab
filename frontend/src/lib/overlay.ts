import { API_BASE } from "./api";

/** Saved smoothed pose per frame; right_* is the racket arm (handedness already swapped). */
export type PoseFeed = {
  fps: number | null;
  frame_count: number | null;
  keypoint_names: string[];
  confidence_threshold: number;
  frames: {
    frame_index: number;
    /** [x, y, confidence] in 0–1 image coordinates, or null when not detected. */
    points: ([number, number, number] | null)[];
    angles: { right_elbow?: number; right_knee?: number };
  }[];
};

export async function fetchPose(analysisId: string): Promise<PoseFeed> {
  const res = await fetch(
    `${API_BASE}/labelling/clips/${encodeURIComponent(analysisId)}/pose`,
    { cache: "no-store", credentials: "include" }
  );
  if (!res.ok) throw new Error(`Could not load the pose (${res.status})`);
  return (await res.json()) as PoseFeed;
}

export type Rect = { x: number; y: number; w: number; h: number };

/** Where the picture sits inside a box with object-fit: contain (portrait or landscape). */
export function contentRect(boxW: number, boxH: number, videoW: number, videoH: number): Rect {
  if (!videoW || !videoH || !boxW || !boxH) return { x: 0, y: 0, w: boxW, h: boxH };
  const scale = Math.min(boxW / videoW, boxH / videoH);
  const w = videoW * scale;
  const h = videoH * scale;
  return { x: (boxW - w) / 2, y: (boxH - h) / 2, w, h };
}

const SKELETON: [string, string][] = [
  ["left_shoulder", "right_shoulder"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  ["left_shoulder", "left_hip"],
  ["right_shoulder", "right_hip"],
  ["left_hip", "right_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
];

const ANGLES: { joint: string; from: string; to: string; key: "right_elbow" | "right_knee" }[] = [
  { joint: "right_elbow", from: "right_shoulder", to: "right_wrist", key: "right_elbow" },
  { joint: "right_knee", from: "right_hip", to: "right_ankle", key: "right_knee" },
];

type Point = { x: number; y: number };

export type OverlayShapes = {
  frameIndex: number | null;
  segments: { a: Point; b: Point; highlight: boolean }[];
  joints: { name: string; at: Point; highlight: boolean }[];
  head: { at: Point; r: number } | null;
  arcs: { center: Point; r: number; start: number; end: number; highlight: boolean }[];
  /** align: which side of the text sits at "at". */
  labels: {
    at: Point;
    text: string;
    highlight: boolean;
    tone: "angle" | "shoulders";
    align: "center" | "end";
  }[];
  shoulderLine: { a: Point; b: Point } | null;
};

export type OverlayOptions = {
  showSkeleton: boolean;
  showAngles: boolean;
  /** Keypoint names used by the selected moment's questions. */
  highlight: ReadonlySet<string>;
};

function angleBetween(j: Point, a: Point, b: Point): number {
  const v1 = { x: a.x - j.x, y: a.y - j.y };
  const v2 = { x: b.x - j.x, y: b.y - j.y };
  const dot = v1.x * v2.x + v1.y * v2.y;
  const n = Math.hypot(v1.x, v1.y) * Math.hypot(v2.x, v2.y);
  return n ? (Math.acos(Math.max(-1, Math.min(1, dot / n))) * 180) / Math.PI : 0;
}

/** Shapes to draw for one frame; positions are in canvas pixels inside rect. */
export function buildOverlay(
  pose: PoseFeed,
  frameIndex: number,
  rect: Rect,
  options: OverlayOptions
): OverlayShapes {
  const empty: OverlayShapes = {
    frameIndex: null,
    segments: [],
    joints: [],
    head: null,
    arcs: [],
    labels: [],
    shoulderLine: null,
  };
  const frame = pose.frames.find((f) => f.frame_index === frameIndex);
  if (!frame) return empty;

  const pts = new Map<string, Point>();
  pose.keypoint_names.forEach((name, i) => {
    const p = frame.points[i];
    if (p && p[2] >= pose.confidence_threshold) {
      pts.set(name, { x: rect.x + p[0] * rect.w, y: rect.y + p[1] * rect.h });
    }
  });
  const hi = (...names: string[]) => names.every((n) => options.highlight.has(n));
  const shapes: OverlayShapes = { ...empty, frameIndex };
  const scale = Math.min(rect.w, rect.h);

  if (options.showSkeleton) {
    for (const [a, b] of SKELETON) {
      const pa = pts.get(a);
      const pb = pts.get(b);
      if (pa && pb) shapes.segments.push({ a: pa, b: pb, highlight: hi(a, b) });
    }
    for (const [name, at] of pts) {
      if (name.includes("eye") || name.includes("ear") || name === "nose") continue;
      shapes.joints.push({ name, at, highlight: options.highlight.has(name) });
    }
    const nose = pts.get("nose");
    if (nose) shapes.head = { at: nose, r: Math.max(8, scale * 0.035) };
  }

  if (options.showAngles) {
    const ls = pts.get("left_shoulder");
    const rs = pts.get("right_shoulder");
    if (ls && rs) {
      const dx = rs.x - ls.x;
      const dy = rs.y - ls.y;
      const ext = 0.25;
      const a = { x: ls.x - dx * ext, y: ls.y - dy * ext };
      const b = { x: rs.x + dx * ext, y: rs.y + dy * ext };
      shapes.shoulderLine = { a, b };
      // Tag the non-racket end so it doesn't cover the hitting arm's angles.
      shapes.labels.push({
        at: { x: a.x - 6, y: a.y },
        text: "Shoulders",
        highlight: false,
        tone: "shoulders",
        align: "end",
      });
    }
    for (const spec of ANGLES) {
      const j = pts.get(spec.joint);
      const a = pts.get(spec.from);
      const b = pts.get(spec.to);
      if (!j || !a || !b) continue;
      const value = frame.angles[spec.key] ?? angleBetween(j, a, b);
      const r = Math.max(14, scale * 0.045);
      let start = Math.atan2(a.y - j.y, a.x - j.x);
      let end = Math.atan2(b.y - j.y, b.x - j.x);
      // Draw the interior (short) arc between the two limbs.
      let sweep = end - start;
      while (sweep > Math.PI) sweep -= 2 * Math.PI;
      while (sweep < -Math.PI) sweep += 2 * Math.PI;
      if (sweep < 0) [start, end] = [end, start];
      else end = start + sweep;
      const highlight = hi(spec.from, spec.joint, spec.to);
      shapes.arcs.push({ center: j, r, start, end: start + Math.abs(sweep), highlight });
      // Label on the outside of the angle.
      const ua = { x: (a.x - j.x) / Math.hypot(a.x - j.x, a.y - j.y), y: (a.y - j.y) / Math.hypot(a.x - j.x, a.y - j.y) };
      const ub = { x: (b.x - j.x) / Math.hypot(b.x - j.x, b.y - j.y), y: (b.y - j.y) / Math.hypot(b.x - j.x, b.y - j.y) };
      let out = { x: -(ua.x + ub.x), y: -(ua.y + ub.y) };
      const len = Math.hypot(out.x, out.y);
      out = len > 1e-3 ? { x: out.x / len, y: out.y / len } : { x: 1, y: 0 };
      shapes.labels.push({
        at: { x: j.x + out.x * (r + 22), y: j.y + out.y * (r + 22) },
        text: `${Math.round(value)}°`,
        highlight,
        tone: "angle",
        align: "center",
      });
    }
  }
  return shapes;
}

const COLORS = {
  limb: "rgba(155, 169, 162, 0.9)",
  accent: "#3DD68C",
  dark: "#0D1210",
  shoulders: "#4CC9F0",
  label: "#C9D3CE",
  border: "#33403A",
};

export function drawOverlay(ctx: CanvasRenderingContext2D, shapes: OverlayShapes, scale: number) {
  const s = (v: number) => v * scale;
  ctx.lineCap = "round";
  for (const seg of shapes.segments) {
    ctx.strokeStyle = seg.highlight ? COLORS.accent : COLORS.limb;
    ctx.lineWidth = s(seg.highlight ? 5 : 3);
    ctx.beginPath();
    ctx.moveTo(seg.a.x, seg.a.y);
    ctx.lineTo(seg.b.x, seg.b.y);
    ctx.stroke();
  }
  if (shapes.head) {
    ctx.strokeStyle = COLORS.limb;
    ctx.lineWidth = s(3);
    ctx.beginPath();
    ctx.arc(shapes.head.at.x, shapes.head.at.y, shapes.head.r, 0, Math.PI * 2);
    ctx.stroke();
  }
  if (shapes.shoulderLine) {
    ctx.save();
    ctx.setLineDash([s(6), s(5)]);
    ctx.strokeStyle = COLORS.shoulders;
    ctx.lineWidth = s(2);
    ctx.beginPath();
    ctx.moveTo(shapes.shoulderLine.a.x, shapes.shoulderLine.a.y);
    ctx.lineTo(shapes.shoulderLine.b.x, shapes.shoulderLine.b.y);
    ctx.stroke();
    ctx.restore();
  }
  for (const arc of shapes.arcs) {
    ctx.strokeStyle = arc.highlight ? COLORS.accent : COLORS.label;
    ctx.lineWidth = s(arc.highlight ? 3 : 2.5);
    ctx.beginPath();
    ctx.arc(arc.center.x, arc.center.y, arc.r, arc.start, arc.end);
    ctx.stroke();
  }
  for (const joint of shapes.joints) {
    ctx.fillStyle = COLORS.dark;
    ctx.strokeStyle = joint.highlight ? COLORS.accent : "#E8EEEA";
    ctx.lineWidth = s(joint.highlight ? 3 : 2);
    ctx.beginPath();
    ctx.arc(joint.at.x, joint.at.y, s(joint.highlight ? 6 : 4), 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
  ctx.textBaseline = "middle";
  for (const label of shapes.labels) {
    const angle = label.tone === "angle";
    ctx.font = `${angle && label.highlight ? 700 : 500} ${s(angle ? (label.highlight ? 17 : 14) : 13)}px Inter, sans-serif`;
    const w = ctx.measureText(label.text).width + s(18);
    const h = s(angle && label.highlight ? 30 : 26);
    const x = label.align === "center" ? label.at.x - w / 2 : label.at.x - w;
    const y = label.at.y - h / 2;
    ctx.fillStyle = angle && label.highlight ? COLORS.accent : COLORS.dark;
    ctx.strokeStyle = label.tone === "shoulders" ? COLORS.shoulders : COLORS.border;
    ctx.lineWidth = s(1);
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, h / 2);
    ctx.fill();
    if (!(angle && label.highlight)) ctx.stroke();
    ctx.fillStyle =
      label.tone === "shoulders" ? COLORS.shoulders : label.highlight ? COLORS.dark : COLORS.label;
    ctx.textAlign = "center";
    ctx.fillText(label.text, x + w / 2, label.at.y);
  }
}
