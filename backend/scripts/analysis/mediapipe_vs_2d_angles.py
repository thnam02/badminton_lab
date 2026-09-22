#!/usr/bin/env python3
"""Compare MediaPipe Pose world-landmark 3D angles vs RTMPose 2D angles.

Analysis-only. Does not modify processing/schemas/services.
Depends on analysis-scoped packages in requirements-analysis.txt (mediapipe).

Reuses the same angle formula and comparison math as wham_vs_2d_angles.py.

Usage (from backend/):
  pip install -r scripts/analysis/requirements-analysis.txt
  python scripts/analysis/mediapipe_vs_2d_angles.py --outputs ../outputs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from wham_vs_2d_angles import (  # noqa: E402
    ANGLE_NAMES,
    _assert_2d_formula_parity,
    angle_at_vertex_3d,
    discover_rtmpose_clips,
    load_2d_angle_series,
    mean_abs_frame_delta,
)

# MediaPipe Pose landmark indices (BlazePose 33-landmark schema).
MP_LANDMARK_INDEX: dict[str, int] = {
    "nose": 0,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
}

# Same triplets as app.processing.angles._JOINT_TRIPLETS.
ANGLE_MP_TRIPLETS: dict[str, tuple[str, str, str]] = {
    "right_elbow": ("right_shoulder", "right_elbow", "right_wrist"),
    "right_knee": ("right_hip", "right_knee", "right_ankle"),
    "right_shoulder": ("right_hip", "right_shoulder", "right_elbow"),
    "right_hip": ("right_shoulder", "right_hip", "right_knee"),
}

def results_dir() -> Path:
    d = _SCRIPT_DIR / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_video(outputs: Path, analysis_id: str) -> Path:
    """Prefer unannotated mesh_source copy; else annotated *_pose.mp4."""
    for name in (
        f"{analysis_id}_mesh_source.mp4",
        f"{analysis_id}_mesh_source.mov",
        f"{analysis_id}_pose.mp4",
        f"{analysis_id}.mp4",
    ):
        p = outputs / name
        if p.is_file():
            return p
    raise FileNotFoundError(f"No video for {analysis_id}")


def video_meta(path: Path) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {path}")
    meta = {
        "path": str(path),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
        "fps": float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
    }
    cap.release()
    return meta


def verify_frame_correspondence(
    outputs: Path, analysis_id: str, video: Path
) -> dict[str, Any]:
    pose = json.loads((outputs / f"{analysis_id}_pose.json").read_text(encoding="utf-8"))
    frames = pose.get("frames") or []
    pose_idxs = [int(f["frame_index"]) for f in frames]
    meta = video_meta(video)
    n_pose = len(pose_idxs)
    n_vid = meta["frame_count"]
    contiguous = pose_idxs == list(range(pose_idxs[0], pose_idxs[0] + n_pose)) if pose_idxs else False
    # Allow ±1 frame OpenCV count ambiguity; reject larger gaps.
    count_ok = abs(n_vid - n_pose) <= 1
    fps_pose = None
    if n_pose >= 2 and frames[-1].get("timestamp") not in (None, 0, 0.0):
        dt = float(frames[-1]["timestamp"]) - float(frames[0]["timestamp"])
        if dt > 0:
            fps_pose = (n_pose - 1) / dt
    fps_ok = True
    fps_note = "pose timestamps missing/degenerate"
    if fps_pose and meta["fps"] > 0:
        fps_ok = abs(fps_pose - meta["fps"]) / meta["fps"] < 0.05
        fps_note = f"pose_implied_fps={fps_pose:.3f} video_fps={meta['fps']:.3f}"

    ok = count_ok and contiguous and (pose_idxs[0] == 0 if pose_idxs else False)
    return {
        "ok": ok,
        "pose_frame_count": n_pose,
        "video_frame_count": n_vid,
        "count_match": count_ok,
        "pose_index_start": pose_idxs[0] if pose_idxs else None,
        "pose_index_end": pose_idxs[-1] if pose_idxs else None,
        "contiguous_from_zero": contiguous and (pose_idxs[0] == 0 if pose_idxs else False),
        "fps_ok": fps_ok,
        "fps_note": fps_note,
        "video": meta,
        "video_is_annotated_pose_mp4": video.name.endswith("_pose.mp4"),
    }


def angles_from_mp_world(landmarks_xyz: np.ndarray) -> dict[str, float | None]:
    """landmarks_xyz: (33, 3) world landmarks (hip-origin, metric)."""
    out: dict[str, float | None] = {}
    for angle_name, (prox, vert, dist) in ANGLE_MP_TRIPLETS.items():
        try:
            out[angle_name] = angle_at_vertex_3d(
                landmarks_xyz[MP_LANDMARK_INDEX[prox]],
                landmarks_xyz[MP_LANDMARK_INDEX[vert]],
                landmarks_xyz[MP_LANDMARK_INDEX[dist]],
            )
        except (ValueError, IndexError):
            out[angle_name] = None
    return out


def run_mediapipe_world_landmarks(
    video_path: Path,
    *,
    max_frames: int | None = None,
    model_complexity: int = 2,
) -> dict[str, Any]:
    """Run MediaPipe Pose (solutions API) with full/heavy model_complexity=2.

    Uses pose_world_landmarks (hip-origin, metric). The tasks PoseLandmarker
    path fatals on this Mac (Metal); solutions.pose is the working full model.
    """
    import mediapipe as mp

    frame_index: list[int] = []
    world: list[np.ndarray] = []
    detected: list[bool] = []

    with mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=model_complexity,
        smooth_landmarks=False,  # keep raw 3D noise for equal-footing jitter compare
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        cap = cv2.VideoCapture(str(video_path))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps <= 1e-3:
            fps = 30.0
        i = 0
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            if max_frames is not None and i >= max_frames:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)
            frame_index.append(i)
            if result.pose_world_landmarks is not None:
                lm = result.pose_world_landmarks.landmark
                xyz = np.array([[p.x, p.y, p.z] for p in lm], dtype=np.float64)
                world.append(xyz)
                detected.append(True)
            else:
                world.append(np.full((33, 3), np.nan, dtype=np.float64))
                detected.append(False)
            i += 1
        cap.release()

    return {
        "frame_index": np.asarray(frame_index, dtype=np.int64),
        "world_landmarks": np.stack(world, axis=0) if world else np.zeros((0, 33, 3)),
        "detected": np.asarray(detected, dtype=bool),
        "fps_used": fps,
        "model_complexity": model_complexity,
    }


def cache_path(analysis_id: str) -> Path:
    return results_dir() / f"{analysis_id}_mediapipe_world.npz"


def load_or_run_mp(
    outputs: Path,
    analysis_id: str,
    *,
    force: bool = False,
    model_complexity: int = 2,
) -> tuple[dict[str, Any], dict[str, Any]]:
    video = resolve_video(outputs, analysis_id)
    align = verify_frame_correspondence(outputs, analysis_id, video)
    cache = cache_path(analysis_id)
    if cache.is_file() and not force:
        data = np.load(cache)
        art = {
            "source": str(cache),
            "frame_index": data["frame_index"].astype(np.int64),
            "world_landmarks": data["world_landmarks"].astype(np.float64),
            "detected": data["detected"].astype(bool),
            "video": str(data["video"]) if "video" in data.files else str(video),
        }
        return art, align

    raw = run_mediapipe_world_landmarks(
        video, model_complexity=model_complexity
    )
    np.savez_compressed(
        cache,
        frame_index=raw["frame_index"],
        world_landmarks=raw["world_landmarks"],
        detected=raw["detected"],
        video=np.asarray(str(video)),
        fps_used=np.asarray(raw["fps_used"]),
        model_complexity=np.asarray(raw["model_complexity"]),
    )
    art = {
        "source": str(cache),
        "frame_index": raw["frame_index"],
        "world_landmarks": raw["world_landmarks"],
        "detected": raw["detected"],
        "video": str(video),
    }
    return art, align


def filming_angle_proxy(outputs: Path, analysis_id: str) -> dict[str, Any]:
    """Rough front-on vs side-on proxy from mid-clip 2D pose + saved keyframe."""
    pose = json.loads((outputs / f"{analysis_id}_pose.json").read_text(encoding="utf-8"))
    frames = pose.get("frames") or []
    if not frames:
        return {"label": "unknown", "reason": "no pose frames"}
    mid = frames[len(frames) // 2]
    kps = mid.get("keypoints") or {}

    def xy(name: str) -> tuple[float, float] | None:
        kp = kps.get(name)
        if not kp or float(kp.get("confidence", 0)) < 0.3:
            return None
        return float(kp["x"]), float(kp["y"])

    ls, rs = xy("left_shoulder"), xy("right_shoulder")
    lh, rh = xy("left_hip"), xy("right_hip")
    if not (ls and rs and lh and rh):
        label, reason = "unknown", "missing shoulder/hip keypoints"
        shoulder_over_torso = None
    else:
        shoulder_w = abs(rs[0] - ls[0])
        mid_sh_y = 0.5 * (ls[1] + rs[1])
        mid_hip_y = 0.5 * (lh[1] + rh[1])
        torso_h = abs(mid_hip_y - mid_sh_y)
        shoulder_over_torso = shoulder_w / torso_h if torso_h > 1e-6 else None
        # Calibrated loosely on normalized image coords: front-on shoulders wide.
        if shoulder_over_torso is None:
            label, reason = "unknown", "degenerate torso"
        elif shoulder_over_torso >= 0.55:
            label, reason = "front-on-ish", f"shoulder/torso={shoulder_over_torso:.2f}"
        elif shoulder_over_torso <= 0.30:
            label, reason = "side-on-ish", f"shoulder/torso={shoulder_over_torso:.2f}"
        else:
            label, reason = "oblique-ish", f"shoulder/torso={shoulder_over_torso:.2f}"

    # Save a mid-frame JPEG for manual eyeballing.
    video = resolve_video(outputs, analysis_id)
    cap = cv2.VideoCapture(str(video))
    fi = int(mid["frame_index"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ok, frame = cap.read()
    cap.release()
    keyframe_path = None
    if ok:
        keyframe_path = str(results_dir() / f"{analysis_id}_midframe_f{fi:04d}.jpg")
        cv2.imwrite(keyframe_path, frame)

    return {
        "label": label,
        "reason": reason,
        "shoulder_over_torso": shoulder_over_torso,
        "pose_frame_index": fi,
        "keyframe_path": keyframe_path,
    }


def compare_clip(
    outputs: Path,
    analysis_id: str,
    art: dict[str, Any],
    *,
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    two_d = load_2d_angle_series(
        outputs, analysis_id, confidence_threshold=confidence_threshold
    )
    per_joint: dict[str, dict[str, Any]] = {}
    for angle_name in ANGLE_NAMES:
        abs_diffs_raw: list[float] = []
        abs_diffs_sm: list[float] = []
        series_3d: list[float] = []
        series_2d_raw: list[float] = []
        series_2d_sm: list[float] = []

        for i, fi in enumerate(art["frame_index"].tolist()):
            fi = int(fi)
            if not bool(art["detected"][i]):
                continue
            if fi not in two_d["raw_by_frame"]:
                continue
            xyz = art["world_landmarks"][i]
            if np.isnan(xyz).any():
                continue
            a3 = angles_from_mp_world(xyz)
            v3 = a3.get(angle_name)
            v2r = two_d["raw_by_frame"][fi].get(angle_name)
            v2s = two_d["smoothed_by_frame"][fi].get(angle_name)
            if v3 is None:
                continue
            series_3d.append(v3)
            if v2r is not None:
                abs_diffs_raw.append(abs(v3 - v2r))
                series_2d_raw.append(v2r)
            if v2s is not None:
                abs_diffs_sm.append(abs(v3 - v2s))
                series_2d_sm.append(v2s)

        per_joint[angle_name] = {
            "n_frames_compared_raw": len(abs_diffs_raw),
            "n_frames_compared_smoothed": len(abs_diffs_sm),
            "mad_vs_2d_raw_deg": (
                float(sum(abs_diffs_raw) / len(abs_diffs_raw)) if abs_diffs_raw else None
            ),
            "max_abs_diff_vs_2d_raw_deg": (
                float(max(abs_diffs_raw)) if abs_diffs_raw else None
            ),
            "mad_vs_2d_smoothed_deg": (
                float(sum(abs_diffs_sm) / len(abs_diffs_sm)) if abs_diffs_sm else None
            ),
            "max_abs_diff_vs_2d_smoothed_deg": (
                float(max(abs_diffs_sm)) if abs_diffs_sm else None
            ),
            "jitter_mean_abs_delta_3d_deg": mean_abs_frame_delta(series_3d),
            "jitter_mean_abs_delta_2d_raw_deg": mean_abs_frame_delta(series_2d_raw),
            "jitter_mean_abs_delta_2d_smoothed_deg": mean_abs_frame_delta(series_2d_sm),
        }

    return {
        "analysis_id": analysis_id,
        "backend": "mediapipe_solutions_pose_complexity_2",
        "landmarks_source": art["source"],
        "video": art.get("video"),
        "mp_frame_count": int(len(art["frame_index"])),
        "mp_detected_frames": int(np.sum(art["detected"])),
        "two_d_note": two_d["note"],
        "per_joint": per_joint,
    }


def plot_overlay(
    outputs: Path,
    analysis_id: str,
    art: dict[str, Any],
    out_path: Path,
    *,
    angle_name: str = "right_elbow",
    confidence_threshold: float = 0.5,
) -> Path | None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    two_d = load_2d_angle_series(
        outputs, analysis_id, confidence_threshold=confidence_threshold
    )
    xs: list[int] = []
    y3: list[float] = []
    y2r: list[float] = []
    y2s: list[float] = []
    for i, fi in enumerate(art["frame_index"].tolist()):
        fi = int(fi)
        if not bool(art["detected"][i]) or fi not in two_d["raw_by_frame"]:
            continue
        xyz = art["world_landmarks"][i]
        if np.isnan(xyz).any():
            continue
        v3 = angles_from_mp_world(xyz).get(angle_name)
        v2r = two_d["raw_by_frame"][fi].get(angle_name)
        v2s = two_d["smoothed_by_frame"][fi].get(angle_name)
        if v3 is None or v2r is None:
            continue
        xs.append(fi)
        y3.append(v3)
        y2r.append(v2r)
        y2s.append(v2s if v2s is not None else float("nan"))
    if not xs:
        return None

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, y2r, label="2D raw (recomputed)", linewidth=1.0, alpha=0.85)
    ax.plot(xs, y2s, label="2D smoothed", linewidth=1.2, alpha=0.9)
    ax.plot(xs, y3, label="3D MediaPipe world", linewidth=1.2, alpha=0.9)
    ax.set_xlabel("frame_index")
    ax.set_ylabel(f"{angle_name} (deg)")
    ax.set_title(f"{analysis_id} — {angle_name}")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def aggregate(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    by_view: dict[str, list[dict[str, Any]]] = {}
    overall: dict[str, dict[str, list[float]]] = {
        j: {"mad_raw": [], "jitter_3d": [], "jitter_2d_raw": []} for j in ANGLE_NAMES
    }
    for s in summaries:
        view = (s.get("filming_angle_proxy") or {}).get("label", "unknown")
        by_view.setdefault(view, []).append(s)
        for j, st in s["per_joint"].items():
            if st["mad_vs_2d_raw_deg"] is not None:
                overall[j]["mad_raw"].append(st["mad_vs_2d_raw_deg"])
            if st["jitter_mean_abs_delta_3d_deg"] is not None:
                overall[j]["jitter_3d"].append(st["jitter_mean_abs_delta_3d_deg"])
            if st["jitter_mean_abs_delta_2d_raw_deg"] is not None:
                overall[j]["jitter_2d_raw"].append(st["jitter_mean_abs_delta_2d_raw_deg"])

    def mean(xs: list[float]) -> float | None:
        return float(sum(xs) / len(xs)) if xs else None

    overall_means = {
        j: {
            "mean_mad_vs_2d_raw_deg": mean(v["mad_raw"]),
            "mean_jitter_3d_deg": mean(v["jitter_3d"]),
            "mean_jitter_2d_raw_deg": mean(v["jitter_2d_raw"]),
            "n": len(v["mad_raw"]),
        }
        for j, v in overall.items()
    }

    view_mad: dict[str, float | None] = {}
    for view, items in by_view.items():
        mads: list[float] = []
        for s in items:
            for st in s["per_joint"].values():
                if st["mad_vs_2d_raw_deg"] is not None:
                    mads.append(st["mad_vs_2d_raw_deg"])
        view_mad[view] = mean(mads)

    return {
        "n_clips": len(summaries),
        "overall_per_joint": overall_means,
        "mean_mad_by_filming_proxy": view_mad,
        "clips_by_filming_proxy": {k: len(v) for k, v in by_view.items()},
    }


def write_recommendation(
    path: Path,
    summaries: list[dict[str, Any]],
    agg: dict[str, Any],
    align_failures: list[str],
) -> None:
    lines = [
        "# MediaPipe world-3D vs RTMPose 2D angles — results",
        "",
        f"Clips compared: **{agg['n_clips']}**",
        f"Frame-alignment failures: {align_failures or '(none)'}",
        "",
        "## Overall (mean across clips)",
    ]
    for j, st in agg["overall_per_joint"].items():
        lines.append(
            f"- **{j}**: MAD(3D vs 2D raw)={_fmt(st['mean_mad_vs_2d_raw_deg'])}°, "
            f"jitter3d={_fmt(st['mean_jitter_3d_deg'])}°, "
            f"jitter2d_raw={_fmt(st['mean_jitter_2d_raw_deg'])}° "
            f"(n={st['n']})"
        )
    lines += [
        "",
        "## Filming-angle proxy vs divergence",
        f"Clip counts: {agg['clips_by_filming_proxy']}",
        f"Mean MAD by proxy label: { {k: _fmt(v) for k, v in agg['mean_mad_by_filming_proxy'].items()} }",
        "",
        "(Proxy = mid-frame 2D shoulder-width / torso-height from RTMPose; "
        "keyframes saved under results/*_midframe_*.jpg for manual check.)",
        "",
        "## Per clip (elbow MAD / jitter)",
    ]
    for s in summaries:
        el = s["per_joint"]["right_elbow"]
        view = (s.get("filming_angle_proxy") or {}).get("label")
        lines.append(
            f"- `{s['analysis_id'][:8]}…` view={view} "
            f"MAD_raw={_fmt(el['mad_vs_2d_raw_deg'])} "
            f"jitter3d={_fmt(el['jitter_mean_abs_delta_3d_deg'])} "
            f"jitter2d={_fmt(el['jitter_mean_abs_delta_2d_raw_deg'])} "
            f"det={s['mp_detected_frames']}/{s['mp_frame_count']}"
        )

    # Recommendation logic
    mads = [
        agg["overall_per_joint"][j]["mean_mad_vs_2d_raw_deg"]
        for j in ANGLE_NAMES
        if agg["overall_per_joint"][j]["mean_mad_vs_2d_raw_deg"] is not None
    ]
    jit3 = [
        agg["overall_per_joint"][j]["mean_jitter_3d_deg"]
        for j in ANGLE_NAMES
        if agg["overall_per_joint"][j]["mean_jitter_3d_deg"] is not None
    ]
    jit2 = [
        agg["overall_per_joint"][j]["mean_jitter_2d_raw_deg"]
        for j in ANGLE_NAMES
        if agg["overall_per_joint"][j]["mean_jitter_2d_raw_deg"] is not None
    ]
    mean_mad = sum(mads) / len(mads) if mads else None
    mean_j3 = sum(jit3) / len(jit3) if jit3 else None
    mean_j2 = sum(jit2) / len(jit2) if jit2 else None

    view_mad = agg["mean_mad_by_filming_proxy"]
    side = view_mad.get("side-on-ish")
    front = view_mad.get("front-on-ish")
    tracks_view = (
        side is not None
        and front is not None
        and side > front + 5.0  # side-on at least 5° more divergent
    )

    lines += ["", "## Answers to the three questions", ""]
    if mean_mad is None:
        lines.append("1. **Difference:** insufficient detections to judge.")
    elif mean_mad >= 15:
        lines.append(
            f"1. **Difference:** Yes — mean |3D−2D| ≈ **{mean_mad:.1f}°** across joints "
            "(materially different, not noise-scale)."
        )
    elif mean_mad >= 8:
        lines.append(
            f"1. **Difference:** Moderate — mean |3D−2D| ≈ **{mean_mad:.1f}°**."
        )
    else:
        lines.append(
            f"1. **Difference:** Small — mean |3D−2D| ≈ **{mean_mad:.1f}°** "
            "(little evidence 2D is badly camera-distorted vs MP world angles)."
        )
    if tracks_view:
        lines.append(
            f"   Divergence **tracks filming proxy**: side-on MAD={side:.1f}° vs "
            f"front-on MAD={front:.1f}° — supports camera-perspective distortion of 2D."
        )
    else:
        lines.append(
            f"   Divergence **does not clearly track** filming proxy "
            f"(side={_fmt(side)} front={_fmt(front)} oblique="
            f"{_fmt(view_mad.get('oblique-ish'))})."
        )

    if mean_j3 is not None and mean_j2 is not None:
        ratio = mean_j3 / mean_j2 if mean_j2 > 1e-6 else float("inf")
        if ratio > 2.0 and mean_j3 > 5:
            lines.append(
                f"2. **Noise:** 3D is **noisier** than 2D raw "
                f"(jitter3d≈{mean_j3:.2f}° vs jitter2d≈{mean_j2:.2f}°, ratio≈{ratio:.1f}×) "
                "— may need temporal smoothing before coaching use."
            )
            noisy = True
        elif mean_j3 <= mean_j2 * 1.25:
            lines.append(
                f"2. **Noise:** 3D jitter is **comparable or better** than 2D raw "
                f"({mean_j3:.2f}° vs {mean_j2:.2f}°) — usable on noise grounds."
            )
            noisy = False
        else:
            lines.append(
                f"2. **Noise:** 3D somewhat noisier ({mean_j3:.2f}° vs {mean_j2:.2f}°) "
                "but not dramatically."
            )
            noisy = False
    else:
        lines.append("2. **Noise:** could not compute.")
        noisy = True

    lines.append("3. **Recommendation:**")
    if mean_mad is not None and mean_mad >= 10 and not noisy:
        lines.append(
            "   **Validate A2 (MediaPipe world landmarks)** as the next precision path — "
            "3D differs enough from 2D to matter, without catastrophic frame jitter."
        )
        rec = "A2"
    elif mean_mad is not None and mean_mad >= 10 and noisy:
        lines.append(
            "   **Conditional A2**: values differ (worth fixing camera distortion) but "
            "add smoothing / quality gates before replacing 2D angles in product."
        )
        rec = "A2_conditional"
    elif mean_mad is not None and mean_mad < 8:
        lines.append(
            "   **Weak support for A2** as a distortion fix — MP world angles stay close "
            "to 2D; consider A3 (dedicated lift) only if coaching still fails for other reasons, "
            "or keep 2D + better calibration."
        )
        rec = "weak_A2"
    else:
        lines.append("   Inconclusive — inspect per-clip JSON and overlay plot.")
        rec = "inconclusive"
    lines += ["", f"Recommendation code: `{rec}`", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outputs",
        type=Path,
        default=_BACKEND_ROOT.parent / "outputs",
    )
    parser.add_argument("--force-rerun-mp", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Max clips (debug)")
    parser.add_argument("--plot-id", type=str, default=None)
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    args = parser.parse_args(argv)

    outputs = args.outputs.resolve()
    _assert_2d_formula_parity()

    clips = discover_rtmpose_clips(outputs)
    if args.limit is not None:
        clips = clips[: args.limit]
    print(f"Clips: {len(clips)} (MediaPipe Pose model_complexity=2 / heavy)")

    summaries: list[dict[str, Any]] = []
    align_failures: list[str] = []

    for i, aid in enumerate(clips, 1):
        print(f"[{i}/{len(clips)}] {aid}")
        try:
            art, align = load_or_run_mp(
                outputs,
                aid,
                force=args.force_rerun_mp,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  SKIP: {exc}")
            align_failures.append(f"{aid}: run failed: {exc}")
            continue
        if not align.get("ok"):
            align_failures.append(f"{aid}: {align}")
            print(f"  ALIGN WARNING: {align}")
            # Still compare on overlapping indices if MP ran; flag in report.
        view = filming_angle_proxy(outputs, aid)
        summary = compare_clip(
            outputs,
            aid,
            art,
            confidence_threshold=args.confidence_threshold,
        )
        summary["frame_alignment"] = align
        summary["filming_angle_proxy"] = view
        summaries.append(summary)
        el = summary["per_joint"]["right_elbow"]
        print(
            f"  view={view['label']} MAD_elbow={el['mad_vs_2d_raw_deg']} "
            f"jitter3d={el['jitter_mean_abs_delta_3d_deg']} "
            f"det={summary['mp_detected_frames']}/{summary['mp_frame_count']}"
        )

    if not summaries:
        print("No clips compared.", file=sys.stderr)
        return 1

    agg = aggregate(summaries)
    out_json = results_dir() / "mediapipe_vs_2d_angles_SUMMARY.json"
    out_json.write_text(
        json.dumps({"aggregate": agg, "clips": summaries}, indent=2),
        encoding="utf-8",
    )
    rec_path = results_dir() / "mediapipe_vs_2d_angles_RECOMMENDATION.md"
    write_recommendation(rec_path, summaries, agg, align_failures)

    # Representative plot: prefer largest elbow MAD among well-detected clips.
    plot_id = args.plot_id
    if plot_id is None:
        ranked = sorted(
            summaries,
            key=lambda s: (
                s["per_joint"]["right_elbow"]["mad_vs_2d_raw_deg"] or 0.0
            ),
            reverse=True,
        )
        plot_id = ranked[0]["analysis_id"]
    art, _ = load_or_run_mp(outputs, plot_id, force=False)
    plot_path = results_dir() / f"{plot_id}_right_elbow_overlay.png"
    written = plot_overlay(outputs, plot_id, art, plot_path)
    print(f"Wrote {out_json}")
    print(f"Wrote {rec_path}")
    print(f"Plot: {written}")
    print(json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
