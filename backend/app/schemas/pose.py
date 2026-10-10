"""Internal pose schema — MMPose-agnostic types used across the app."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Keypoint:
    """Normalized joint in image space: x/y in [0, 1], plus confidence."""

    x: float
    y: float
    confidence: float

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "confidence": self.confidence}


@dataclass(slots=True)
class PoseFrame:
    frame_index: int
    timestamp: float
    keypoints: dict[str, Keypoint] = field(default_factory=dict)
    # Joints filled by temporal gap interpolation rather than detected here;
    # their confidence is borrowed from neighbouring frames.
    interpolated: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "keypoints": {name: kp.to_dict() for name, kp in self.keypoints.items()},
        }
        if self.interpolated:
            payload["interpolated"] = sorted(self.interpolated)
        return payload


@dataclass(slots=True)
class PoseSequence:
    video: str
    frames: list[PoseFrame] = field(default_factory=list)
    analysis_id: str = ""
    snapshot_id: str = ""
    fingerprint: str = ""
    snapshot_schema_version: str = ""
    artifact_schema_version: str = ""
    artifact_role: str = ""

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def append(self, frame: PoseFrame) -> None:
        self.frames.append(frame)

    def to_dict(self) -> dict[str, Any]:
        from app.schemas.provenance import provenance_fields_from_object

        payload: dict[str, Any] = {
            "video": self.video,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
        }
        payload.update(provenance_fields_from_object(self))
        return payload

    def save_json(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path
