"""Clip view for coaches: video, capture context, moments, questions and pose.

Everything is read from the saved analysis artifacts; nothing is recomputed
by the analysis pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.labelling.batches import is_safe_id, labelling_dir
from app.processing.technique_rules_config import CONTACT_WRIST_WINDOW_FRAMES
from app.schemas.stroke_types import stroke_type_label
from app.services.video_service import (
    angles_json_path_for,
    contact_json_path_for,
    evidence_json_path_for,
    phases_json_path_for,
    smoothed_pose_json_path_for,
    stroke_metrics_json_path_for,
)

STATS_CONFIG_PATH = Path(__file__).with_name("labelling_stats.json")
KIND_MEASURED = "measured"
KIND_COACH_ONLY = "coach_only"
DEFAULT_QUESTION_SET = "default"
# COCO-17 order used by the pose estimator.
KEYPOINT_NAMES = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


def load_stats_config(path: Path | None = None) -> dict[str, Any]:
    """Coach-facing wording; read on every call so edits apply without a restart."""
    return json.loads((path or STATS_CONFIG_PATH).read_text(encoding="utf-8"))


def question_set(config: dict[str, Any], stroke_type: str) -> list[dict[str, Any]]:
    sets = config["question_sets"]
    return sets.get(stroke_type) or sets[DEFAULT_QUESTION_SET]


def legacy_ids(questions: list[dict[str, Any]]) -> dict[str, str]:
    """Older stat id -> the question that replaced it."""
    return {old: q["id"] for q in questions for old in q.get("replaces") or []}


def normalize_stats(stats: dict[str, Any], legacy: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Read answers saved under older stat ids as the questions that replaced them
    (legacy: old id -> new id, see legacy_ids)."""
    out = {k: dict(v) for k, v in stats.items()}
    for old, new in legacy.items():
        if old in out and new not in out:
            out[new] = out.pop(old)
    return out


def normalize_label(label: dict[str, Any] | None, clip: dict[str, Any]) -> dict[str, Any] | None:
    if label is None:
        return None
    return {**label, "stats": normalize_stats(label.get("stats") or {}, clip["legacy_ids"])}


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


def _read(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


class ClipArtifacts:
    def __init__(self, analysis_id: str, output_dir: Path | None = None) -> None:
        if not is_safe_id(analysis_id):
            raise FileNotFoundError(f"Analysis '{analysis_id}' not found")
        self.analysis_id = analysis_id
        self.root = Path(output_dir or settings.output_dir)
        self.video = self.root / f"{analysis_id}_pose.mp4"
        self.metrics = _read(stroke_metrics_json_path_for(self.video))
        if self.metrics is None and not self.video.is_file():
            raise FileNotFoundError(f"Analysis '{analysis_id}' not found")
        self.metrics = self.metrics or {}
        self.evidence = _read(evidence_json_path_for(self.video)) or {}
        self.contact = _read(contact_json_path_for(self.video)) or {}
        self.phases = _read(phases_json_path_for(self.video)) or {}
        self._pose: dict[str, Any] | None = None

    @property
    def pose(self) -> dict[str, Any]:
        if self._pose is None:
            self._pose = _read(smoothed_pose_json_path_for(self.video)) or {}
        return self._pose

    def pose_by_frame(self) -> dict[int, dict[str, Any]]:
        return {int(f["frame_index"]): f for f in self.pose.get("frames") or []}

    def stroke_type(self) -> str:
        return self.evidence.get("stroke_type") or self.metrics.get("stroke_type") or "FOREHAND_SMASH"

    def contact_frame(self) -> int | None:
        for value in (
            self.contact.get("frame_index"),
            self.phases.get("estimated_contact_frame_index"),
            self.metrics.get("estimated_contact_frame_index"),
        ):
            if value is not None:
                return int(value)
        return None

    def segment(self, phase: str) -> dict[str, Any] | None:
        return next(
            (s for s in self.phases.get("segments") or [] if s.get("phase") == phase), None
        )

    def named_frames(self) -> dict[str, int | None]:
        """Frames of each stroke moment, from the saved phase data."""

        def edge(phase: str, key: str) -> int | None:
            seg = self.segment(phase)
            return int(seg[key]) if seg is not None and seg.get(key) is not None else None

        return {
            "preparation_end": edge("PREPARATION", "end_frame_index"),
            "backswing_end": edge("BACKSWING", "end_frame_index"),
            "contact": self.contact_frame(),
            "follow_through_start": edge("FOLLOW_THROUGH", "start_frame_index"),
            "follow_through_end": edge("FOLLOW_THROUGH", "end_frame_index"),
        }

    def raw_video_url(self) -> str | None:
        videos = labelling_dir(self.root) / "videos"
        found = sorted(videos.glob(f"{self.analysis_id}.*")) if videos.is_dir() else []
        return f"/outputs/{found[0].relative_to(self.root).as_posix()}" if found else None


def _timing(pose: dict[str, Any]) -> tuple[float | None, int | None]:
    frames = pose.get("frames") or []
    count = pose.get("frame_count") or (len(frames) or None)
    if len(frames) >= 2:
        first, last = frames[0], frames[-1]
        span = float(last["timestamp"]) - float(first["timestamp"])
        steps = int(last["frame_index"]) - int(first["frame_index"])
        if span > 0 and steps > 0:
            return steps / span, int(count) if count else None
    return None, int(count) if count else None


def _visible_y(frame: dict[str, Any] | None, name: str) -> float | None:
    kp = ((frame or {}).get("keypoints") or {}).get(name)
    if kp is None or float(kp.get("confidence", 0.0)) < settings.pose_confidence_threshold:
        return None
    return float(kp["y"])


def stat_value(art: ClipArtifacts, source: dict[str, Any]) -> float | None:
    kind = source.get("kind")
    if kind == "metric":
        value = art.metrics.get(str(source.get("field")))
        return float(value) if isinstance(value, (int, float)) else None
    if kind == "hand_height_at_contact":
        hit = art.contact_frame()
        if hit is None:
            return None
        by_frame = art.pose_by_frame()
        heights = [
            h
            for idx in range(
                hit - CONTACT_WRIST_WINDOW_FRAMES, hit + CONTACT_WRIST_WINDOW_FRAMES + 1
            )
            if (h := hand_height(by_frame.get(idx), settings.pose_confidence_threshold))
            is not None
        ]
        return max(heights) if heights else None
    if kind == "wrist_above_shoulder_at_backswing_end":
        wrist = art.metrics.get("backswing_end_wrist_y_normalized")
        shoulder = art.metrics.get("backswing_end_shoulder_y_normalized")
        if wrist is None or shoulder is None:
            frame = art.named_frames()["backswing_end"]
            pose = art.pose_by_frame().get(frame) if frame is not None else None
            wrist, shoulder = _visible_y(pose, "right_wrist"), _visible_y(pose, "right_shoulder")
        if wrist is None or shoulder is None:
            return None
        return 1.0 if float(wrist) < float(shoulder) else 0.0
    raise ValueError(f"Unknown stat source kind {kind!r}")


def clip_questions(art: ClipArtifacts, config: dict[str, Any]) -> list[dict[str, Any]]:
    frames = art.named_frames()
    moments = {m["id"]: m for m in config["moments"]}
    out = []
    for q in question_set(config, art.stroke_type()):
        measured = q["kind"] == KIND_MEASURED
        metric = q.get("metric") or {}
        point = config["measure_points"].get(metric.get("measured_at", "")) if measured else None
        value = stat_value(art, metric["source"]) if measured else None
        out.append(
            {
                "id": q["id"],
                "title": q["title"],
                "hint": q.get("hint", ""),
                "moment": q["moment"],
                "moment_title": moments[q["moment"]]["title"],
                "kind": q["kind"],
                "unit": metric.get("unit") if measured else None,
                "value": value,
                # Coach-only questions can always be answered (or "Can't see").
                "available": value is not None if measured else True,
                "measured_at": (
                    {"label": point["label"], "frame": frames.get(point["frame"])}
                    if point
                    else None
                ),
                "joints": q.get("joints") or [],
                "rating_options": config["rating_options"][q["kind"]],
            }
        )
    return out


def clip_view(analysis_id: str, output_dir: Path | None = None) -> dict[str, Any]:
    art = ClipArtifacts(analysis_id, output_dir)
    config = load_stats_config()
    stroke = art.stroke_type()
    fps, frame_count = _timing(art.pose)
    hit = art.contact_frame()
    frames = art.named_frames()
    overlay = f"/outputs/{art.video.name}" if art.video.is_file() else None
    raw = art.raw_video_url()
    questions = clip_questions(art, config)
    return {
        "analysis_id": analysis_id,
        "video_url": raw or overlay,
        "raw_video_url": raw,
        "overlay_video_url": overlay,
        "stroke_type": stroke,
        "stroke_label": stroke_type_label(stroke),
        "handedness": art.evidence.get("handedness"),
        "camera_view": art.evidence.get("camera_view"),
        "system_contact_frame": hit,
        "system_contact_timestamp": (
            art.contact.get("timestamp")
            if art.contact.get("timestamp") is not None
            else (hit / fps if hit is not None and fps else None)
        ),
        "fps": fps,
        "frame_count": frame_count,
        "moment_frames": frames,
        "moments": [
            {"id": m["id"], "title": m["title"], "frame": frames.get(m["seek_frame"])}
            for m in config["moments"]
        ],
        "questions": questions,
        "legacy_ids": legacy_ids(question_set(config, stroke)),
        "overall_ratings": config["overall_ratings"],
        "fix_options": [{"id": q["id"], "title": q["title"]} for q in questions]
        + [{"id": "not_listed", "title": config["fix_not_listed_label"]}],
    }


def answerable_ids(clip: dict[str, Any]) -> list[str]:
    """Questions a finished label must rate: coach-only ones and measured ones with a value."""
    return [q["id"] for q in clip["questions"] if q["available"]]


def clip_pose(analysis_id: str, output_dir: Path | None = None) -> dict[str, Any]:
    """Saved smoothed pose (racket arm is right_* after the handedness swap) and joint
    angles per frame, compact enough to draw the overlay in the browser."""
    art = ClipArtifacts(analysis_id, output_dir)
    fps, frame_count = _timing(art.pose)
    angles = {
        int(f["frame_index"]): f.get("angles") or {}
        for f in (_read(angles_json_path_for(art.video)) or {}).get("frames") or []
    }
    frames = []
    for f in art.pose.get("frames") or []:
        kps = f.get("keypoints") or {}
        idx = int(f["frame_index"])
        frames.append(
            {
                "frame_index": idx,
                "points": [
                    (
                        [round(float(k["x"]), 5), round(float(k["y"]), 5), round(float(k.get("confidence", 0.0)), 3)]
                        if (k := kps.get(name)) is not None
                        else None
                    )
                    for name in KEYPOINT_NAMES
                ],
                "angles": {
                    name: round(float(v), 1)
                    for name, v in angles.get(idx, {}).items()
                    if name in ("right_elbow", "right_knee") and v is not None
                },
            }
        )
    return {
        "analysis_id": analysis_id,
        "fps": fps,
        "frame_count": frame_count,
        "keypoint_names": list(KEYPOINT_NAMES),
        "confidence_threshold": settings.pose_confidence_threshold,
        "frames": frames,
    }
