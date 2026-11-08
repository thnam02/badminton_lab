"""Clip view for coaches: video, capture context, system hit frame and stats.

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
    contact_json_path_for,
    evidence_json_path_for,
    phases_json_path_for,
    smoothed_pose_json_path_for,
    stroke_metrics_json_path_for,
)

STATS_CONFIG_PATH = Path(__file__).with_name("labelling_stats.json")


def load_stats_config(path: Path | None = None) -> dict[str, Any]:
    """Coach-facing wording; read on every call so edits apply without a restart."""
    return json.loads((path or STATS_CONFIG_PATH).read_text(encoding="utf-8"))


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

    def contact_frame(self) -> int | None:
        for value in (
            self.contact.get("frame_index"),
            self.phases.get("estimated_contact_frame_index"),
            self.metrics.get("estimated_contact_frame_index"),
        ):
            if value is not None:
                return int(value)
        return None

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


def stat_value(art: ClipArtifacts, source: dict[str, Any]) -> float | None:
    kind = source.get("kind")
    if kind == "metric":
        value = art.metrics.get(str(source.get("field")))
        return float(value) if isinstance(value, (int, float)) else None
    if kind == "hand_height_at_contact":
        hit = art.contact_frame()
        if hit is None:
            return None
        by_frame = {int(f["frame_index"]): f for f in art.pose.get("frames") or []}
        heights = [
            h
            for idx in range(
                hit - CONTACT_WRIST_WINDOW_FRAMES, hit + CONTACT_WRIST_WINDOW_FRAMES + 1
            )
            if (h := hand_height(by_frame.get(idx), settings.pose_confidence_threshold))
            is not None
        ]
        return max(heights) if heights else None
    raise ValueError(f"Unknown stat source kind {kind!r}")


def clip_stats(art: ClipArtifacts, config: dict[str, Any]) -> list[dict[str, Any]]:
    stats = []
    for stat in config["stats"]:
        value = stat_value(art, stat["source"])
        stats.append(
            {
                "id": stat["id"],
                "name": stat["name"],
                "description": stat.get("description", ""),
                "when": stat["when"],
                "unit": stat["unit"],
                "value": value,
                "available": value is not None,
            }
        )
    return stats


def clip_view(analysis_id: str, output_dir: Path | None = None) -> dict[str, Any]:
    art = ClipArtifacts(analysis_id, output_dir)
    config = load_stats_config()
    stroke = art.evidence.get("stroke_type") or art.metrics.get("stroke_type") or "FOREHAND_SMASH"
    fps, frame_count = _timing(art.pose)
    hit = art.contact_frame()
    overlay = f"/outputs/{art.video.name}" if art.video.is_file() else None
    raw = art.raw_video_url()
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
        "stats": clip_stats(art, config),
        "rating_options": config["rating_options"],
        "overall_ratings": config["overall_ratings"],
    }
