"""Tests for phase-specific stroke feature extraction."""

from __future__ import annotations

import pytest

from app.processing.phases import detect_smash_phases
from app.processing.stroke_metrics import extract_stroke_metrics
from app.schemas.angles import AngleSequence
from app.schemas.motion import MotionSequence
from app.schemas.phases import PhaseSequence, SmashPhase
from tests.test_phases import _synthetic_smash


def test_contact_metrics_use_estimated_contact_anchor() -> None:
    pose, angles, motion, contact = _synthetic_smash()
    phases = detect_smash_phases(pose, angles, motion)
    metrics = extract_stroke_metrics(phases, angles, motion)

    assert metrics.estimated_contact.frame_index == contact
    assert metrics.estimated_contact.right_elbow_angle == pytest.approx(155.0)
    assert metrics.estimated_contact.right_knee_angle == pytest.approx(160.0)
    assert metrics.estimated_contact.right_wrist_speed == pytest.approx(2.0)


def test_acceleration_peaks_are_windowed_not_global() -> None:
    pose, angles, motion, contact = _synthetic_smash()
    phases = detect_smash_phases(pose, angles, motion)
    metrics = extract_stroke_metrics(phases, angles, motion)

    accel = next(s for s in phases.segments if s.phase is SmashPhase.ACCELERATION)
    window_speeds = [
        f.right_wrist_speed
        for f in motion.frames
        if accel.start_frame_index <= f.frame_index <= accel.end_frame_index
        and f.right_wrist_speed is not None
    ]
    window_omega = [
        abs(f.right_elbow_angular_velocity)
        for f in motion.frames
        if accel.start_frame_index <= f.frame_index <= accel.end_frame_index
        and f.right_elbow_angular_velocity is not None
    ]

    assert metrics.acceleration.peak_wrist_speed.value == pytest.approx(max(window_speeds))
    assert metrics.acceleration.peak_elbow_angular_velocity.value == pytest.approx(
        max(window_omega)
    )
    # Global wrist-speed peak is at contact, so accel peak must be strictly lower.
    assert metrics.acceleration.peak_wrist_speed.value < 2.0
    assert metrics.acceleration.peak_wrist_speed.frame_index != contact
    assert metrics.acceleration.peak_elbow_angular_velocity.value == pytest.approx(180.0)


def test_preparation_and_follow_through_have_basic_metrics() -> None:
    pose, angles, motion, _ = _synthetic_smash()
    phases = detect_smash_phases(pose, angles, motion)
    metrics = extract_stroke_metrics(phases, angles, motion)

    assert SmashPhase.PREPARATION in {s.phase for s in phases.segments}
    assert SmashPhase.FOLLOW_THROUGH in {s.phase for s in phases.segments}

    assert metrics.preparation.window.duration is not None
    assert metrics.preparation.window.duration >= 0.0
    assert metrics.preparation.mean_wrist_speed is not None
    assert metrics.preparation.mean_elbow_angle is not None
    assert metrics.preparation.mean_knee_angle is not None

    assert metrics.follow_through.window.duration is not None
    assert metrics.follow_through.window.duration >= 0.0
    assert metrics.follow_through.mean_wrist_speed is not None
    assert metrics.follow_through.wrist_speed_at_end is not None
    assert metrics.follow_through.elbow_angle_at_end is not None
    assert metrics.follow_through.wrist_speed_at_end < metrics.estimated_contact.right_wrist_speed


def test_backswing_min_elbow_is_in_backswing_window() -> None:
    pose, angles, motion, _ = _synthetic_smash()
    phases = detect_smash_phases(pose, angles, motion)
    metrics = extract_stroke_metrics(phases, angles, motion)

    back = next(s for s in phases.segments if s.phase is SmashPhase.BACKSWING)
    idx = metrics.backswing.min_elbow_angle.frame_index
    assert idx is not None
    assert back.start_frame_index <= idx <= back.end_frame_index
    assert metrics.backswing.min_elbow_angle.value is not None


def test_missing_phases_yield_null_metrics() -> None:
    metrics = extract_stroke_metrics(
        PhaseSequence(video="empty.mp4"),
        AngleSequence(video="empty.mp4"),
        MotionSequence(video="empty.mp4"),
    )
    assert metrics.estimated_contact.right_elbow_angle is None
    assert metrics.estimated_contact.right_wrist_speed is None
    assert metrics.acceleration.peak_wrist_speed.value is None
    assert metrics.acceleration.peak_elbow_angular_velocity.value is None
    assert metrics.preparation.mean_wrist_speed is None
    assert metrics.follow_through.wrist_speed_at_end is None
    assert "scoring" not in metrics.to_dict()
    assert "feedback" not in metrics.to_dict()


def _swing_fixture():
    """30 frames: prep 0–9, backswing 10–19, accel 20–24, contact 25, follow 26–29.

    The whole-clip |elbow ω| peak sits in preparation (frame 2); inside the swing
    window the elbow peaks at 24 and the shoulder at 22.
    """
    from app.schemas.angles import AngleFrame
    from app.schemas.motion import MotionFrame
    from app.schemas.phases import PhaseSegment
    from app.schemas.pose import Keypoint, PoseFrame, PoseSequence

    fps = 30.0
    n = 30
    contact = 25
    pose = PoseSequence(video="swing.mp4")
    angles = AngleSequence(video="swing.mp4")
    motion = MotionSequence(video="swing.mp4")
    for i in range(n):
        ts = i / fps
        wrist_y = 0.30 if i == 19 else 0.50
        pose.append(
            PoseFrame(
                frame_index=i,
                timestamp=ts,
                keypoints={
                    "nose": Keypoint(x=0.5, y=0.40, confidence=0.9),
                    "right_wrist": Keypoint(x=0.6, y=wrist_y if i != contact else 0.35, confidence=0.9),
                    "right_shoulder": Keypoint(x=0.55, y=0.45, confidence=0.9),
                },
            )
        )
        angles.append(
            AngleFrame(
                frame_index=i,
                timestamp=ts,
                right_elbow=100.0 if i < 10 else 150.0,
                right_knee=140.0 if i < 10 else 150.0,
                right_shoulder=90.0,
            )
        )
        elbow_w = {2: 900.0, 24: 500.0}.get(i, 50.0)
        shoulder_w = {3: 800.0, 22: 400.0}.get(i, 40.0)
        motion.append(
            MotionFrame(
                frame_index=i,
                timestamp=ts,
                right_wrist_speed=2.0 if i == contact else 0.5,
                right_elbow_angular_velocity=elbow_w,
                right_shoulder_angular_velocity=shoulder_w,
            )
        )

    def seg(phase, a, b):
        return PhaseSegment(
            phase=phase,
            start_frame_index=a,
            end_frame_index=b,
            start_timestamp=a / fps,
            end_timestamp=b / fps,
            confidence=0.9,
        )

    phases = PhaseSequence(
        video="swing.mp4",
        segments=[
            seg(SmashPhase.PREPARATION, 0, 9),
            seg(SmashPhase.BACKSWING, 10, 19),
            seg(SmashPhase.ACCELERATION, 20, 24),
            seg(SmashPhase.ESTIMATED_CONTACT, contact, contact),
            seg(SmashPhase.FOLLOW_THROUGH, 26, 29),
        ],
        estimated_contact_frame_index=contact,
        estimated_contact_timestamp=contact / fps,
        confidence=0.9,
    )
    return pose, angles, motion, phases, contact


def test_swing_window_peak_offsets_ignore_preparation_peaks() -> None:
    from app.processing.stroke_metrics import compute_stroke_metrics

    pose, angles, motion, phases, _ = _swing_fixture()
    m = compute_stroke_metrics(pose, angles, motion, phases)

    assert m.peak_elbow_omega_offset_frames == -23  # whole-clip search unchanged
    assert m.swing_peak_elbow_omega_offset_frames == -1
    assert m.swing_peak_shoulder_omega_offset_frames == -3


def test_posture_y_fields_at_contact_and_backswing_end() -> None:
    from app.processing.stroke_metrics import compute_stroke_metrics

    pose, angles, motion, phases, _ = _swing_fixture()
    m = compute_stroke_metrics(pose, angles, motion, phases)

    assert m.contact_nose_y_normalized == pytest.approx(0.40)
    assert m.contact_wrist_y_normalized == pytest.approx(0.35)
    assert m.backswing_end_wrist_y_normalized == pytest.approx(0.30)
    assert m.backswing_end_shoulder_y_normalized == pytest.approx(0.45)
    assert m.preparation_elbow_angle_deg == pytest.approx(100.0)


def test_clear_metrics_gain_swing_fields_and_knee_contribution() -> None:
    from app.processing.strokes.clear.metrics import compute_clear_metrics

    pose, angles, motion, phases, _ = _swing_fixture()
    m = compute_clear_metrics(pose, angles, motion, phases)

    assert m.knee_contribution_deg == pytest.approx(10.0)
    assert m.swing_peak_elbow_omega_offset_frames == -1
    assert m.swing_peak_shoulder_omega_offset_frames == -3
    assert m.contact_nose_y_normalized == pytest.approx(0.40)
    assert m.backswing_end_wrist_y_normalized == pytest.approx(0.30)
