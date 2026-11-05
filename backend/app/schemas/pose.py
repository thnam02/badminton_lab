"""Internal pose schema — MMPose-agnostic types used across the app."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Keypoint:
    """Normalized joint in image space: x/y in [0, 1], plus confidence.

    x is divided by frame width and y by frame height, so x and y units differ
    on non-square frames. Scale with ``to_pixels`` before any geometry.
    """

    x: float
    y: float
    confidence: float

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "confidence": self.confidence}


# (x multiplier, y multiplier) from normalized coordinates to pixels.
PixelScale = tuple[float, float]
UNIT_SCALE: PixelScale = (1.0, 1.0)


def to_pixels(kp: Keypoint, scale: PixelScale) -> Keypoint:
    return Keypoint(x=kp.x * scale[0], y=kp.y * scale[1], confidence=kp.confidence)


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
    # Source frame size in pixels; needed to turn normalized keypoints into
    # pixel geometry. None for sequences built without video metadata.
    frame_width: int | None = None
    frame_height: int | None = None
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

    def pixel_scale(self) -> PixelScale:
        """Normalized → pixel multipliers; unit scale when the frame size is unknown."""
        if self.frame_width and self.frame_height:
            return float(self.frame_width), float(self.frame_height)
        return UNIT_SCALE

    def with_frames(self, frames: list[PoseFrame]) -> PoseSequence:
        """New sequence with the same video and frame size."""
        return PoseSequence(
            video=self.video,
            frames=frames,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
        )

    def to_dict(self) -> dict[str, Any]:
        from app.schemas.provenance import provenance_fields_from_object

        payload: dict[str, Any] = {
            "video": self.video,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
        }
        payload.update(provenance_fields_from_object(self))
        return payload

    def save_json(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path
