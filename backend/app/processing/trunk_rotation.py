"""Image-plane trunk rotation (X-factor proxy) from bilateral shoulder/hip keypoints.

Uses left+right shoulders and hips already tracked by RTMPose (COCO-17).
This is a 2D projected angle, not a full 3D spiral X-factor — useful as a
relative preparation cue, not a calibrated biomechanical degree of freedom.
"""

from __future__ import annotations

import math

from app.schemas.phases import PhaseSequence, SmashPhase
from app.schemas.pose import Keypoint, PoseFrame, PoseSequence


def trunk_rotation_deg(
    left_shoulder: Keypoint,
    right_shoulder: Keypoint,
    left_hip: Keypoint,
    right_hip: Keypoint,
) -> float:
    """Absolute angular difference (deg) between shoulder line and hip line."""
    shoulder = math.atan2(
        right_shoulder.y - left_shoulder.y,
        right_shoulder.x - left_shoulder.x,
    )
    hip = math.atan2(
        right_hip.y - left_hip.y,
        right_hip.x - left_hip.x,
    )
    diff = math.degrees(shoulder - hip)
    while diff > 180.0:
        diff -= 360.0
    while diff < -180.0:
        diff += 360.0
    return abs(diff)


def trunk_rotation_at_frame(
    frame: PoseFrame,
    *,
    confidence_threshold: float = 0.5,
) -> float | None:
    names = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
    pts: list[Keypoint] = []
    for name in names:
        kp = frame.keypoints.get(name)
        if kp is None or kp.confidence < confidence_threshold:
            return None
        pts.append(kp)
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
    values: list[float] = []
    for start, end in windows:
        for idx in range(start, end + 1):
            frame = pose_by.get(idx)
            if frame is None:
                continue
            value = trunk_rotation_at_frame(
                frame, confidence_threshold=confidence_threshold
            )
            if value is not None:
                values.append(value)
    if not values:
        return None
    return float(max(values))
