"""Check a coach rule against that coach's own clip labels.

Each labelled clip is measured from its saved analysis files: at the
coach-marked hit frame for "the hit", otherwise at the analysis's own phase
frame (or the live metric for that phase).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.coach.rule_builder_config import (
    AGREEMENT_MIN_CLIPS_PER_CLASS,
    AGREEMENT_NOT_ENOUGH_DATA,
    AGREEMENT_OVERLAPS,
    AGREEMENT_SEPARATES_WELL,
    BOUNDARY_SETS,
    FLAG_BELOW,
    HIT_WRIST_WINDOW_FRAMES,
    MEASURE_ELBOW_AT_HIT,
    MEASURE_HAND_HEIGHT_AT_BACKSWING_END,
    MEASURE_HAND_HEIGHT_AT_HIT,
    MEASURE_PREPARATION_KNEE,
    SEPARATES_WELL_MIN_BALANCED_ACCURACY,
    BoundaryPicture,
    RuleTarget,
)
from app.coach.stores import ANSWER_NO, ANSWER_YES, ClipLabel
from app.config import settings
from app.services.video_service import (
    angles_json_path_for,
    phases_json_path_for,
    smoothed_pose_json_path_for,
    stroke_metrics_json_path_for,
)

KIND_MISSED = "missed"
KIND_FALSE_FLAG = "false_flag"


@dataclass(slots=True)
class ClipMeasurement:
    analysis_id: str
    value: float | None
    frame_index: int | None = None
    timestamp: float | None = None
    reason: str | None = None


class _Artifacts:
    def __init__(self, analysis_id: str, output_dir: Path) -> None:
        self.video = Path(output_dir) / f"{analysis_id}_pose.mp4"
        self._cache: dict[str, Any] = {}

    def _load(self, path: Path) -> Any:
        key = str(path)
        if key not in self._cache:
            self._cache[key] = (
                json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
            )
        return self._cache[key]

    def frames(self, kind: str) -> dict[int, dict[str, Any]]:
        path = (
            angles_json_path_for(self.video)
            if kind == "angles"
            else smoothed_pose_json_path_for(self.video)
        )
        data = self._load(path) or {}
        return {int(f["frame_index"]): f for f in data.get("frames") or []}

    def phases(self) -> dict[str, Any] | None:
        return self._load(phases_json_path_for(self.video))

    def metrics(self) -> dict[str, Any] | None:
        return self._load(stroke_metrics_json_path_for(self.video))


def _segment(phases: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    return next(
        (s for s in (phases or {}).get("segments") or [] if s.get("phase") == name),
        None,
    )


def _timestamp(art: _Artifacts, frame: int | None) -> float | None:
    if frame is None:
        return None
    f = art.frames("pose").get(frame) or art.frames("angles").get(frame)
    return float(f["timestamp"]) if f and f.get("timestamp") is not None else None


def hand_height(frame: dict[str, Any] | None, threshold: float) -> float | None:
    """Wrist height above the shoulder in torso lengths (image y grows downward)."""
    if frame is None:
        return None
    kps = frame.get("keypoints") or {}
    pts = [kps.get(n) for n in ("right_wrist", "right_shoulder", "right_hip")]
    if any(p is None or float(p.get("confidence", 0.0)) < threshold for p in pts):
        return None
    wrist, shoulder, hip = (float(p["y"]) for p in pts)
    torso = hip - shoulder
    if torso <= 1e-6:
        return None
    return (shoulder - wrist) / torso


def measure_clip(
    label: ClipLabel, target: RuleTarget, output_dir: Path | None = None
) -> ClipMeasurement:
    art = _Artifacts(label.analysis_id, Path(output_dir or settings.output_dir))
    threshold = float(settings.pose_confidence_threshold)
    aid = label.analysis_id

    if target.measure in (MEASURE_ELBOW_AT_HIT, MEASURE_HAND_HEIGHT_AT_HIT):
        hit = label.hit_frame_index
        if hit is None:
            return ClipMeasurement(aid, None, reason="no hit frame marked")
        if target.measure == MEASURE_ELBOW_AT_HIT:
            angles = (art.frames("angles").get(hit) or {}).get("angles") or {}
            value = angles.get("right_elbow")
            return ClipMeasurement(
                aid,
                float(value) if value is not None else None,
                hit,
                _timestamp(art, hit),
                None if value is not None else "elbow not visible at the hit",
            )
        pose = art.frames("pose")
        heights = [
            h
            for idx in range(hit - HIT_WRIST_WINDOW_FRAMES, hit + HIT_WRIST_WINDOW_FRAMES + 1)
            if (h := hand_height(pose.get(idx), threshold)) is not None
        ]
        return ClipMeasurement(
            aid,
            max(heights) if heights else None,
            hit,
            _timestamp(art, hit),
            None if heights else "hand or body not visible at the hit",
        )

    if target.measure == MEASURE_HAND_HEIGHT_AT_BACKSWING_END:
        back = _segment(art.phases(), "BACKSWING")
        if back is None:
            return ClipMeasurement(aid, None, reason="no racket-back moment found")
        frame = int(back["end_frame_index"])
        value = hand_height(art.frames("pose").get(frame), threshold)
        return ClipMeasurement(
            aid,
            value,
            frame,
            _timestamp(art, frame),
            None if value is not None else "hand or body not visible at racket-back",
        )

    if target.measure == MEASURE_PREPARATION_KNEE:
        value = (art.metrics() or {}).get(target.metric_id)
        prep = _segment(art.phases(), "PREPARATION")
        frame = (
            (int(prep["start_frame_index"]) + int(prep["end_frame_index"])) // 2
            if prep is not None
            else None
        )
        return ClipMeasurement(
            aid,
            float(value) if value is not None else None,
            frame,
            _timestamp(art, frame),
            None if value is not None else "knee not measured while getting ready",
        )

    return ClipMeasurement(aid, None, reason=f"unknown measurement {target.measure}")


def is_flagged(value: float, boundary: float, direction: str) -> bool:
    return value < boundary if direction == FLAG_BELOW else value > boundary


def _counts(
    rows: list[tuple[ClipMeasurement, bool]], boundary: float, direction: str
) -> dict[str, Any]:
    caught = missed = false_flags = fine_ok = 0
    for m, fault in rows:
        flagged = is_flagged(float(m.value), boundary, direction)
        if fault:
            caught += flagged
            missed += not flagged
        else:
            false_flags += flagged
            fine_ok += not flagged
    faults, fine = caught + missed, false_flags + fine_ok
    balanced = (
        0.5 * (caught / faults + fine_ok / fine) if faults and fine else None
    )
    return {
        "caught": caught,
        "missed": missed,
        "false_flags": false_flags,
        "fine_not_flagged": fine_ok,
        "balanced_accuracy": balanced,
    }


def agreement_status(fault_clips: int, fine_clips: int, balanced: float | None) -> str:
    if (
        fault_clips < AGREEMENT_MIN_CLIPS_PER_CLASS
        or fine_clips < AGREEMENT_MIN_CLIPS_PER_CLASS
        or balanced is None
    ):
        return AGREEMENT_NOT_ENOUGH_DATA
    if balanced >= SEPARATES_WELL_MIN_BALANCED_ACCURACY:
        return AGREEMENT_SEPARATES_WELL
    return AGREEMENT_OVERLAPS


def _suggest(
    rows: list[tuple[ClipMeasurement, bool]],
    pictures: tuple[BoundaryPicture, ...],
    chosen: BoundaryPicture,
    direction: str,
) -> BoundaryPicture | None:
    """Picture with the best balanced accuracy; ties go to the one nearest the choice."""
    chosen_idx = pictures.index(chosen)
    scored = [
        (b, i, p)
        for i, p in enumerate(pictures)
        if (b := _counts(rows, p.value, direction)["balanced_accuracy"]) is not None
    ]
    if not scored:
        return None
    return max(scored, key=lambda t: (t[0], -abs(t[1] - chosen_idx)))[2]


def check_rule(
    target: RuleTarget,
    chosen: BoundaryPicture,
    labels: list[ClipLabel],
    output_dir: Path | None = None,
) -> dict[str, Any]:
    pictures = BOUNDARY_SETS[target.boundary_set].pictures
    rows: list[tuple[ClipMeasurement, bool]] = []
    unmeasured: list[dict[str, Any]] = []
    unanswered = 0
    for label in labels:
        answer = label.answers.get(target.label_question)
        if answer not in (ANSWER_YES, ANSWER_NO):
            unanswered += 1
            continue
        m = measure_clip(label, target, output_dir)
        if m.value is None:
            unmeasured.append({"analysis_id": m.analysis_id, "reason": m.reason})
            continue
        rows.append((m, answer == ANSWER_YES))

    fault_clips = sum(1 for _, fault in rows if fault)
    fine_clips = len(rows) - fault_clips
    counts = _counts(rows, chosen.value, target.direction)
    suggestion = _suggest(rows, pictures, chosen, target.direction)
    suggested = None
    if suggestion is not None:
        suggested = {
            "picture_id": suggestion.id,
            "label": suggestion.label,
            "value": suggestion.value,
            "steps_from_choice": pictures.index(suggestion) - pictures.index(chosen),
            **_counts(rows, suggestion.value, target.direction),
        }

    disagreements = []
    for m, fault in rows:
        flagged = is_flagged(float(m.value), chosen.value, target.direction)
        if fault == flagged:
            continue
        disagreements.append(
            {
                "analysis_id": m.analysis_id,
                "kind": KIND_MISSED if fault else KIND_FALSE_FLAG,
                "value": m.value,
                "frame_index": m.frame_index,
                "timestamp": m.timestamp,
            }
        )

    return {
        "reviewed_clips": len(labels),
        "answered_clips": len(rows) + len(unmeasured),
        "unanswered_clips": unanswered,
        "fault_clips": fault_clips,
        "fine_clips": fine_clips,
        "unmeasured": unmeasured,
        **counts,
        "agreement_status": agreement_status(
            fault_clips, fine_clips, counts["balanced_accuracy"]
        ),
        "suggested": suggested,
        "disagreements": disagreements,
    }
