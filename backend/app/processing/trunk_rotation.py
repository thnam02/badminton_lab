"""Image-plane trunk rotation (X-factor proxy) from bilateral shoulder/hip keypoints.

Uses left+right shoulders and hips already tracked by RTMPose (COCO-17).
This is a 2D projected angle, not a full 3D spiral X-factor — useful as a
relative preparation cue, not a calibrated biomechanical degree of freedom.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from app.schemas.phases import PhaseSequence, SmashPhase
from app.schemas.pose import (
    UNIT_SCALE,
    Keypoint,
    PixelScale,
    PoseFrame,
    PoseSequence,
    to_pixels,
)


def trunk_rotation_deg(
    left_shoulder: Keypoint,
    right_shoulder: Keypoint,
    left_hip: Keypoint,
    right_hip: Keypoint,
) -> float:
    """Angle (deg, in [0, 90]) between the shoulder line and the hip line.

    Lines have no direction, so 170° between the vectors means 10° between
    the lines (e.g. when left/right keypoints cross in a turned 2D view).
    """
    shoulder = math.atan2(
        right_shoulder.y - left_shoulder.y,
        right_shoulder.x - left_shoulder.x,
    )
    hip = math.atan2(
        right_hip.y - left_hip.y,
        right_hip.x - left_hip.x,
    )
    diff = abs(math.degrees(shoulder - hip)) % 180.0
    return min(diff, 180.0 - diff)


def trunk_rotation_at_frame(
    frame: PoseFrame,
    *,
    confidence_threshold: float = 0.5,
    scale: PixelScale = UNIT_SCALE,
) -> float | None:
    names = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
    pts: list[Keypoint] = []
    for name in names:
        kp = frame.keypoints.get(name)
        if kp is None or kp.confidence < confidence_threshold:
            return None
        pts.append(to_pixels(kp, scale))
    try:
        return trunk_rotation_deg(pts[0], pts[1], pts[2], pts[3])
    except (ValueError, ZeroDivisionError):
        return None


def peak_trunk_rotation_in_phases(
    pose: PoseSequence,
    phases: PhaseSequence,
    *,
    target_phases: tuple[SmashPhase, ...] = (SmashPhase.PREPARATION, SmashPhase.BACKSWING),
    confidence_threshold: float = 0.5,
) -> float | None:
    """Max |trunk rotation| over preparation/backswing frames (X-factor proxy peak)."""
    windows: list[tuple[int, int]] = []
    for seg in phases.segments:
        if seg.phase in target_phases:
            if seg.start_frame_index is None or seg.end_frame_index is None:
                continue
            windows.append((int(seg.start_frame_index), int(seg.end_frame_index)))
    if not windows:
        return None

    pose_by = {f.frame_index: f for f in pose.frames}
    scale = pose.pixel_scale()
    values: list[float] = []
    for start, end in windows:
        for idx in range(start, end + 1):
            frame = pose_by.get(idx)
            if frame is None:
                continue
            value = trunk_rotation_at_frame(
                frame, confidence_threshold=confidence_threshold, scale=scale
            )
            if value is not None:
                values.append(value)
    if not values:
        return None
    return float(max(values))


def peak_trunk_rotation_velocity_in_window(
    pose_frames: Iterable[PoseFrame],
    start: int,
    end: int,
    *,
    confidence_threshold: float = 0.5,
    scale: PixelScale = UNIT_SCALE,
) -> tuple[float | None, int | None]:
    """Peak |d(trunk rotation)/dt| (deg/s) and its frame within [start, end].

    Uses consecutive frames whose trunk rotation is measurable; the velocity
    is assigned to the later frame of each pair.
    """
    frames = sorted(
        (f for f in pose_frames if start <= f.frame_index <= end),
        key=lambda f: f.frame_index,
    )
    best_value: float | None = None
    best_frame: int | None = None
    prev: tuple[PoseFrame, float] | None = None
    for frame in frames:
        value = trunk_rotation_at_frame(
            frame, confidence_threshold=confidence_threshold, scale=scale
        )
        if value is None:
            prev = None
            continue
        if prev is not None and frame.frame_index == prev[0].frame_index + 1:
            dt = frame.timestamp - prev[0].timestamp
            if dt > 0 and math.isfinite(dt):
                omega = abs(value - prev[1]) / dt
                if best_value is None or omega > best_value:
                    best_value = omega
                    best_frame = frame.frame_index
        prev = (frame, value)
    return best_value, best_frame
