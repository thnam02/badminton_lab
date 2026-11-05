"""Stroke metrics extraction helpers."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from statistics import mean, median
from typing import Protocol, TypeVar

from app.schemas.angles import AngleSequence
from app.schemas.contact import ContactEvent
from app.schemas.final_analysis import FinalAnalysisState
from app.schemas.motion import MotionSequence, PeakStats
from app.schemas.phases import PhaseSegment, PhaseSequence, SmashPhase
from app.schemas.pose import PixelScale, PoseSequence
from app.schemas.stroke import (
    AccelerationMetrics,
    BackswingMetrics,
    EstimatedContactMetrics,
    FollowThroughMetrics,
    PhaseWindow,
    PreparationMetrics,
    StrokeMetrics as PhaseStrokeMetrics,
)
from app.schemas.stroke_metrics import StrokeMetrics as LegacyStrokeMetrics


class _Indexed(Protocol):
    frame_index: int
    timestamp: float


T = TypeVar("T", bound=_Indexed)
Getter = Callable[[T], float | None]


def compute_stroke_metrics_from_final(
    state: FinalAnalysisState,
) -> LegacyStrokeMetrics:
    """Compute stroke metrics exclusively from the canonical final analysis state."""
    return compute_stroke_metrics(
        state.smoothed_pose,
        state.angles,
        state.motion,
        state.phases,
        contact=state.contact,
    )


def compute_stroke_metrics(
    pose: PoseSequence,
    angles: AngleSequence,
    motion: MotionSequence,
    phases: PhaseSequence,
    *,
    contact: ContactEvent | None = None,
) -> LegacyStrokeMetrics:
    """Aggregate phase-aware metrics for rule-based technique evaluation.

    When ``contact`` is provided, contact-frame measurements snap to that event
    even if phase labels still mention ESTIMATED_CONTACT.
    Prefer ``compute_stroke_metrics_from_final`` after contact resolution.
    """
    video = pose.video or angles.video or motion.video or phases.video
    contact_idx = (
        contact.frame_index
        if contact is not None
        else phases.estimated_contact_frame_index
    )
    contact_ts = (
        contact.timestamp
        if contact is not None
        else phases.estimated_contact_timestamp
    )
    metrics = LegacyStrokeMetrics(
        video=video,
        estimated_contact_frame_index=contact_idx,
        estimated_contact_timestamp=contact_ts,
        phase_confidence=phases.confidence,
        contact_confidence=float(contact.confidence) if contact is not None else None,
    )

    if contact_idx is None:
        return metrics

    angle_by = {f.frame_index: f for f in angles.frames}
    motion_by = {f.frame_index: f for f in motion.frames}
    pose_by = {f.frame_index: f for f in pose.frames}

    contact_angle = angle_by.get(contact_idx)
    contact_motion = motion_by.get(contact_idx)
    contact_pose = pose_by.get(contact_idx)

    if contact_angle is not None:
        metrics.contact_elbow_angle_deg = contact_angle.right_elbow
        metrics.contact_knee_angle_deg = contact_angle.right_knee
        metrics.contact_shoulder_angle_deg = contact_angle.right_shoulder

    if contact_pose is not None:
        wrist = contact_pose.keypoints.get("right_wrist")
        if wrist is not None:
            metrics.contact_wrist_y_normalized = wrist.y

    peak = motion.peaks.get("right_wrist_speed")
    if peak is not None and peak.value is not None:
        metrics.peak_wrist_speed = peak.value
    elif contact_motion is not None:
        metrics.peak_wrist_speed = contact_motion.right_wrist_speed

    metrics.preparation_knee_angle_deg = _phase_mean_angle(
        phases, angle_by, SmashPhase.PREPARATION, "knee"
    )
    apply_leg_drive_fields(metrics, angle_by, phases, contact_idx)
    metrics.preparation_elbow_angle_deg = _phase_mean_angle(
        phases, angle_by, SmashPhase.PREPARATION, "elbow"
    )
    scale = pose.pixel_scale()
    apply_swing_window_fields(metrics, pose_by, motion_by, phases, contact_idx, scale=scale)
    apply_body_normalised_speed(metrics, pose_by, phases, contact_idx, scale=scale)

    metrics.peak_elbow_omega_offset_frames = _peak_elbow_omega_offset(motion_by, contact_idx)
    metrics.peak_shoulder_omega_offset_frames = _peak_omega_offset(
        motion_by, contact_idx, attr="right_shoulder_angular_velocity"
    )
    metrics.peak_hip_omega_offset_frames = _peak_omega_offset(
        motion_by, contact_idx, attr="right_hip_angular_velocity"
    )
    _apply_kinetic_chain_fields(metrics, motion)
    metrics.acceleration_phase_fraction = _acceleration_fraction(phases, contact_idx)

    from app.processing.trunk_rotation import peak_trunk_rotation_in_phases

    metrics.peak_trunk_rotation_deg = peak_trunk_rotation_in_phases(pose, phases)

    follow_ratio, follow_frames = _follow_through_stats(motion_by, phases)
    metrics.follow_through_speed_ratio = follow_ratio
    metrics.follow_through_frame_count = follow_frames

    from app.processing.plausibility import apply_plausibility_gate

    apply_plausibility_gate(metrics)
    return metrics


def extract_stroke_metrics(
    phases: PhaseSequence,
    angles: AngleSequence,
    motion: MotionSequence,
    *,
    contact: ContactEvent | None = None,
) -> PhaseStrokeMetrics:
    """Pull per-phase extrema / means; values are None when a window or sample is missing."""
    angle_by = {frame.frame_index: frame for frame in angles.frames}
    motion_by = {frame.frame_index: frame for frame in motion.frames}
    video = phases.video or angles.video or motion.video

    prep_seg = _first_segment(phases, SmashPhase.PREPARATION)
    back_seg = _first_segment(phases, SmashPhase.BACKSWING)
    accel_seg = _first_segment(phases, SmashPhase.ACCELERATION)
    follow_seg = _first_segment(phases, SmashPhase.FOLLOW_THROUGH)

    contact_idx = (
        contact.frame_index
        if contact is not None
        else phases.estimated_contact_frame_index
    )
    contact_ts = (
        contact.timestamp
        if contact is not None
        else phases.estimated_contact_timestamp
    )
    contact_angle = angle_by.get(contact_idx) if contact_idx is not None else None
    contact_motion = motion_by.get(contact_idx) if contact_idx is not None else None

    accel_motion = _frames_in(motion.frames, accel_seg)
    back_angles = _frames_in(angles.frames, back_seg)
    back_motion = _frames_in(motion.frames, back_seg)
    prep_angles = _frames_in(angles.frames, prep_seg)
    prep_motion = _frames_in(motion.frames, prep_seg)
    follow_angles = _frames_in(angles.frames, follow_seg)
    follow_motion = _frames_in(motion.frames, follow_seg)

    return PhaseStrokeMetrics(
        video=video,
        preparation=PreparationMetrics(
            window=_window(prep_seg),
            mean_wrist_speed=_mean(prep_motion, lambda f: f.right_wrist_speed),
            mean_elbow_angle=_mean(prep_angles, lambda f: f.right_elbow),
            mean_knee_angle=_mean(prep_angles, lambda f: f.right_knee),
        ),
        backswing=BackswingMetrics(
            window=_window(back_seg),
            min_elbow_angle=_extremum(back_angles, lambda f: f.right_elbow, minimize=True),
            peak_wrist_speed=_extremum(
                back_motion, lambda f: f.right_wrist_speed, minimize=False
            ),
        ),
        acceleration=AccelerationMetrics(
            window=_window(accel_seg),
            peak_wrist_speed=_extremum(
                accel_motion, lambda f: f.right_wrist_speed, minimize=False
            ),
            peak_elbow_angular_velocity=_extremum(
                accel_motion,
                lambda f: f.right_elbow_angular_velocity,
                minimize=False,
                use_abs=True,
            ),
        ),
        estimated_contact=EstimatedContactMetrics(
            frame_index=contact_idx,
            timestamp=(
                contact_ts
                if contact_ts is not None
                else contact_motion.timestamp
                if contact_motion is not None
                else contact_angle.timestamp
                if contact_angle is not None
                else None
            ),
            right_elbow_angle=_finite(
                contact_angle.right_elbow if contact_angle is not None else None
            ),
            right_knee_angle=_finite(
                contact_angle.right_knee if contact_angle is not None else None
            ),
            right_wrist_speed=_finite(
                contact_motion.right_wrist_speed if contact_motion is not None else None
            ),
        ),
        follow_through=FollowThroughMetrics(
            window=_window(follow_seg),
            mean_wrist_speed=_mean(follow_motion, lambda f: f.right_wrist_speed),
            wrist_speed_at_end=_value_at_end(
                follow_motion, follow_seg, lambda f: f.right_wrist_speed
            ),
            elbow_angle_at_end=_value_at_end(
                follow_angles, follow_seg, lambda f: f.right_elbow
            ),
        ),
    )


def _phase_mean_angle(
    phases: PhaseSequence,
    angle_by: dict,
    phase: SmashPhase,
    joint: str,
) -> float | None:
    values: list[float] = []
    for seg in phases.segments:
        if seg.phase is not phase:
            continue
        for idx in range(seg.start_frame_index, seg.end_frame_index + 1):
            af = angle_by.get(idx)
            if af is None:
                continue
            val = getattr(af, f"right_{joint}", None)
            if val is not None and math.isfinite(val):
                values.append(val)
    return mean(values) if values else None


def _peak_elbow_omega_offset(
    motion_by: dict,
    contact_idx: int,
) -> int | None:
    return _peak_omega_offset(
        motion_by, contact_idx, attr="right_elbow_angular_velocity"
    )


def _peak_omega_offset(
    motion_by: dict,
    contact_idx: int,
    *,
    attr: str,
) -> int | None:
    best_idx: int | None = None
    best_mag = float("-inf")
    for idx, mf in motion_by.items():
        omega = getattr(mf, attr, None)
        if omega is None or not math.isfinite(omega):
            continue
        mag = abs(omega)
        if mag > best_mag:
            best_mag = mag
            best_idx = idx
    if best_idx is None:
        return None
    return int(best_idx - contact_idx)


def loading_window(phases: PhaseSequence, contact_idx: int) -> tuple[int, int] | None:
    """Backswing start → frame before contact (backswing + acceleration).

    The deepest knee bend that the leg drive extends from can fall late in
    loading, after the wrist has started to accelerate.
    """
    back = _first_segment(phases, SmashPhase.BACKSWING)
    accel = _first_segment(phases, SmashPhase.ACCELERATION)
    start_seg = back if back is not None else accel
    if start_seg is None or start_seg.start_frame_index >= contact_idx:
        return None
    return start_seg.start_frame_index, contact_idx - 1


def apply_leg_drive_fields(
    metrics,
    angle_by: dict,
    phases: PhaseSequence,
    contact_idx: int,
) -> None:
    """Knee contribution = contact knee angle − deepest knee bend while loading."""
    window = loading_window(phases, contact_idx)
    knees: list[float] = []
    if window is not None:
        for idx in range(window[0], window[1] + 1):
            af = angle_by.get(idx)
            val = af.right_knee if af is not None else None
            if val is not None and math.isfinite(val):
                knees.append(float(val))
    metrics.loading_min_knee_angle_deg = min(knees) if knees else None
    if metrics.loading_min_knee_angle_deg is not None and metrics.contact_knee_angle_deg is not None:
        metrics.knee_contribution_deg = (
            metrics.contact_knee_angle_deg - metrics.loading_min_knee_angle_deg
        )
    else:
        metrics.knee_contribution_deg = None


def swing_window(phases: PhaseSequence, contact_idx: int) -> tuple[int, int]:
    """Frame span of the analysed swing: backswing start → follow-through end.

    Falls back to acceleration start, then to the contact frame, when earlier
    phases are missing.
    """
    back = _first_segment(phases, SmashPhase.BACKSWING)
    accel = _first_segment(phases, SmashPhase.ACCELERATION)
    follow = _first_segment(phases, SmashPhase.FOLLOW_THROUGH)
    start = (
        back.start_frame_index
        if back is not None
        else accel.start_frame_index
        if accel is not None
        else contact_idx
    )
    end = follow.end_frame_index if follow is not None else contact_idx
    return min(start, contact_idx), max(end, contact_idx)


def _peak_omega_offset_in_window(
    motion_by: dict,
    contact_idx: int,
    *,
    attr: str,
    start: int,
    end: int,
) -> int | None:
    window = {idx: mf for idx, mf in motion_by.items() if start <= idx <= end}
    return _peak_omega_offset(window, contact_idx, attr=attr)


def _peak_positive_offset_in_window(
    motion_by: dict,
    contact_idx: int,
    *,
    attr: str,
    start: int,
    end: int,
) -> int | None:
    """Offset of the largest positive value (e.g. elbow extension) in [start, end]."""
    best_idx: int | None = None
    best = 0.0
    for idx, mf in motion_by.items():
        if not start <= idx <= end:
            continue
        value = getattr(mf, attr, None)
        if value is None or not math.isfinite(value) or value <= best:
            continue
        best = value
        best_idx = idx
    return None if best_idx is None else int(best_idx - contact_idx)


def _keypoint_y(pose_by: dict, frame_index: int | None, joint: str) -> float | None:
    if frame_index is None:
        return None
    frame = pose_by.get(frame_index)
    kp = frame.keypoints.get(joint) if frame is not None else None
    if kp is None or not math.isfinite(kp.y):
        return None
    return float(kp.y)


def apply_swing_window_fields(
    metrics,
    pose_by: dict,
    motion_by: dict,
    phases: PhaseSequence,
    contact_idx: int,
    *,
    scale: PixelScale,
) -> None:
    """Fill swing-window peak offsets and contact / backswing-end posture y values."""
    start, end = swing_window(phases, contact_idx)
    metrics.swing_peak_elbow_omega_offset_frames = _peak_omega_offset_in_window(
        motion_by, contact_idx, attr="right_elbow_angular_velocity", start=start, end=end
    )
    metrics.swing_peak_shoulder_omega_offset_frames = _peak_omega_offset_in_window(
        motion_by,
        contact_idx,
        attr="right_shoulder_angular_velocity",
        start=start,
        end=end,
    )
    if (
        metrics.swing_peak_elbow_omega_offset_frames is not None
        and metrics.swing_peak_shoulder_omega_offset_frames is not None
    ):
        metrics.swing_elbow_lead_over_shoulder_frames = int(
            metrics.swing_peak_shoulder_omega_offset_frames
            - metrics.swing_peak_elbow_omega_offset_frames
        )
    metrics.contact_nose_y_normalized = _keypoint_y(pose_by, contact_idx, "nose")
    from app.processing.technique_rules_config import CONTACT_WRIST_WINDOW_FRAMES

    wrist_ys = [
        y
        for idx in range(
            contact_idx - CONTACT_WRIST_WINDOW_FRAMES,
            contact_idx + CONTACT_WRIST_WINDOW_FRAMES + 1,
        )
        if (y := _keypoint_y(pose_by, idx, "right_wrist")) is not None
    ]
    # Smallest image y = highest wrist position.
    metrics.contact_window_min_wrist_y_normalized = min(wrist_ys) if wrist_ys else None
    back = _first_segment(phases, SmashPhase.BACKSWING)
    back_end = back.end_frame_index if back is not None else None
    metrics.backswing_end_wrist_y_normalized = _keypoint_y(pose_by, back_end, "right_wrist")
    metrics.backswing_end_shoulder_y_normalized = _keypoint_y(
        pose_by, back_end, "right_shoulder"
    )

    apply_acceleration_chain_fields(
        metrics, pose_by, motion_by, phases, contact_idx, scale=scale
    )


def _midpoint(frame, left: str, right: str, confidence_threshold: float, scale: PixelScale):
    a = frame.keypoints.get(left)
    b = frame.keypoints.get(right)
    if a is None or b is None:
        return None
    if a.confidence < confidence_threshold or b.confidence < confidence_threshold:
        return None
    x = (a.x + b.x) / 2.0 * scale[0]
    y = (a.y + b.y) / 2.0 * scale[1]
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return x, y


def median_torso_length(
    pose_by: dict,
    start: int,
    end: int,
    *,
    scale: PixelScale,
    confidence_threshold: float = 0.5,
) -> float | None:
    """Median mid-shoulder → mid-hip distance over frames [start, end].

    Pixels, like wrist speed, so speed / torso length is in torso lengths per
    second.
    """
    lengths: list[float] = []
    for idx in range(start, end + 1):
        frame = pose_by.get(idx)
        if frame is None:
            continue
        shoulder = _midpoint(
            frame, "left_shoulder", "right_shoulder", confidence_threshold, scale
        )
        hip = _midpoint(frame, "left_hip", "right_hip", confidence_threshold, scale)
        if shoulder is None or hip is None:
            continue
        lengths.append(math.hypot(shoulder[0] - hip[0], shoulder[1] - hip[1]))
    if not lengths:
        return None
    return float(median(lengths))


def apply_body_normalised_speed(
    metrics,
    pose_by: dict,
    phases: PhaseSequence,
    contact_idx: int,
    *,
    scale: PixelScale,
) -> None:
    """Peak wrist speed in torso lengths / s, removing camera-distance scale."""
    start, end = swing_window(phases, contact_idx)
    torso = median_torso_length(pose_by, start, end, scale=scale)
    metrics.swing_median_torso_length = torso
    speed = metrics.peak_wrist_speed
    metrics.peak_wrist_speed_body_norm = (
        float(speed) / torso
        if speed is not None and torso is not None and torso > 1e-6
        else None
    )


def acceleration_window(phases: PhaseSequence, contact_idx: int) -> tuple[int, int]:
    """Backswing end → contact (the hit), falling back to acceleration start."""
    back = _first_segment(phases, SmashPhase.BACKSWING)
    accel = _first_segment(phases, SmashPhase.ACCELERATION)
    if back is not None:
        start = back.end_frame_index
    elif accel is not None:
        start = accel.start_frame_index
    else:
        start = contact_idx
    return min(start, contact_idx), contact_idx


def apply_acceleration_chain_fields(
    metrics,
    pose_by: dict,
    motion_by: dict,
    phases: PhaseSequence,
    contact_idx: int,
    *,
    scale: PixelScale,
) -> None:
    """Trunk-rotation vs elbow-extension peak timing during the hit (display only).

    Needs 3D landmarks or coach-labelled data before it can become a rule
    again: 2D trunk rotation is unreliable when the shoulders overlap.
    """
    from app.processing.trunk_rotation import peak_trunk_rotation_velocity_in_window

    start, end = acceleration_window(phases, contact_idx)
    # Elbow extension = interior elbow angle increasing (positive ω).
    metrics.acceleration_peak_elbow_extension_offset_frames = (
        _peak_positive_offset_in_window(
            motion_by,
            contact_idx,
            attr="right_elbow_angular_velocity",
            start=start,
            end=end,
        )
    )
    trunk_omega, trunk_frame = peak_trunk_rotation_velocity_in_window(
        pose_by.values(), start, end, scale=scale
    )
    metrics.peak_trunk_rotation_velocity_deg_s = trunk_omega
    metrics.acceleration_peak_trunk_rotation_velocity_offset_frames = (
        int(trunk_frame - contact_idx) if trunk_frame is not None else None
    )
    elbow_off = metrics.acceleration_peak_elbow_extension_offset_frames
    trunk_off = metrics.acceleration_peak_trunk_rotation_velocity_offset_frames
    metrics.acceleration_elbow_extension_lead_over_trunk_frames = (
        int(trunk_off - elbow_off)
        if elbow_off is not None and trunk_off is not None
        else None
    )


def _apply_kinetic_chain_fields(metrics, motion: MotionSequence) -> None:
    """Fill proximal→distal peak gaps and order from motion peaks."""
    hip_peak = motion.peaks.get("right_hip_angular_velocity")
    shoulder_peak = motion.peaks.get("right_shoulder_angular_velocity")
    elbow_peak = motion.peaks.get("right_elbow_angular_velocity")
    hip_f = hip_peak.frame_index if hip_peak is not None else None
    shoulder_f = shoulder_peak.frame_index if shoulder_peak is not None else None
    elbow_f = elbow_peak.frame_index if elbow_peak is not None else None
    if hip_f is not None and shoulder_f is not None:
        metrics.kinetic_chain_hip_shoulder_gap_frames = int(shoulder_f - hip_f)
    if shoulder_f is not None and elbow_f is not None:
        metrics.kinetic_chain_shoulder_elbow_gap_frames = int(elbow_f - shoulder_f)
    peaks = [
        ("hip", hip_f),
        ("shoulder", shoulder_f),
        ("elbow", elbow_f),
    ]
    present = [(name, idx) for name, idx in peaks if idx is not None]
    if len(present) >= 2:
        present.sort(key=lambda item: item[1])
        metrics.kinetic_chain_order = "_".join(name for name, _ in present)


def _acceleration_fraction(phases: PhaseSequence, contact_idx: int) -> float | None:
    accel_seg = _first_segment(phases, SmashPhase.ACCELERATION)
    prep_seg = _first_segment(phases, SmashPhase.PREPARATION)
    if accel_seg is None:
        return None
    accel_frames = accel_seg.end_frame_index - accel_seg.start_frame_index + 1
    start = prep_seg.start_frame_index if prep_seg else accel_seg.start_frame_index
    total = max(1, contact_idx - start + 1)
    return accel_frames / total


def _follow_through_stats(
    motion_by: dict,
    phases: PhaseSequence,
) -> tuple[float | None, int | None]:
    follow_seg = _first_segment(phases, SmashPhase.FOLLOW_THROUGH)
    if follow_seg is None:
        return None, None

    frame_count = follow_seg.end_frame_index - follow_seg.start_frame_index + 1

    speeds: list[float] = []
    for idx in range(follow_seg.start_frame_index, follow_seg.end_frame_index + 1):
        mf = motion_by.get(idx)
        if mf is None or mf.right_wrist_speed is None:
            continue
        speeds.append(mf.right_wrist_speed)

    if not speeds:
        return 0.0, frame_count

    peak_candidates = [
        mf.right_wrist_speed
        for mf in motion_by.values()
        if mf.right_wrist_speed is not None and mf.right_wrist_speed > 0
    ]
    peak = max(peak_candidates) if peak_candidates else None
    if peak is None:
        return None, frame_count

    ratio = max(speeds) / peak
    return ratio, frame_count


def _first_segment(phases: PhaseSequence, phase: SmashPhase) -> PhaseSegment | None:
    for segment in phases.segments:
        if segment.phase is phase:
            return segment
    return None


def _window(segment: PhaseSegment | None) -> PhaseWindow:
    if segment is None:
        return PhaseWindow()
    duration = segment.end_timestamp - segment.start_timestamp
    if not math.isfinite(duration) or duration < 0.0:
        duration_value: float | None = None
    else:
        duration_value = duration
    return PhaseWindow(
        start_frame_index=segment.start_frame_index,
        end_frame_index=segment.end_frame_index,
        start_timestamp=segment.start_timestamp,
        end_timestamp=segment.end_timestamp,
        duration=duration_value,
    )


def _frames_in(frames: Sequence[T], segment: PhaseSegment | None) -> list[T]:
    if segment is None:
        return []
    start = segment.start_frame_index
    end = segment.end_frame_index
    return [frame for frame in frames if start <= frame.frame_index <= end]


def _finite(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value


def _mean(frames: Sequence[T], getter: Getter[T]) -> float | None:
    values = [v for v in (_finite(getter(frame)) for frame in frames) if v is not None]
    if not values:
        return None
    return float(sum(values) / len(values))


def _extremum(
    frames: Sequence[T],
    getter: Getter[T],
    *,
    minimize: bool,
    use_abs: bool = False,
) -> PeakStats:
    best_frame: T | None = None
    best_score = float("inf") if minimize else float("-inf")
    best_value: float | None = None

    for frame in frames:
        value = _finite(getter(frame))
        if value is None:
            continue
        score = abs(value) if use_abs else value
        better = score < best_score if minimize else score > best_score
        if better:
            best_score = score
            best_frame = frame
            best_value = value

    if best_frame is None or best_value is None:
        return PeakStats(value=None, frame_index=None, timestamp=None)

    peak_value = abs(best_value) if use_abs else best_value
    return PeakStats(
        value=peak_value,
        frame_index=best_frame.frame_index,
        timestamp=best_frame.timestamp,
    )


def _value_at_end(
    frames: Sequence[T],
    segment: PhaseSegment | None,
    getter: Getter[T],
) -> float | None:
    if segment is None:
        return None
    by_index = {frame.frame_index: frame for frame in frames}
    at_end = by_index.get(segment.end_frame_index)
    if at_end is not None:
        value = _finite(getter(at_end))
        if value is not None:
            return value
    for frame in reversed(list(frames)):
        value = _finite(getter(frame))
        if value is not None:
            return value
    return None
