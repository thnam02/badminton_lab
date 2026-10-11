"""Kinematic contact peak selection and contact_peak_confidence."""

from __future__ import annotations

import math

import pytest

from app.processing.contact_peaks import (
    WARNING_CONTACT_AMBIGUOUS_PEAKS,
    WARNING_CONTACT_SPIKE_PEAK,
    WARNING_CONTACT_UNSTABLE_TRACKING,
    analyze_contact_peaks,
)
from app.schemas.motion import MotionFrame, MotionSequence
from app.schemas.pose import Keypoint, PoseFrame, PoseSequence
from app.services.pose_service import pose_service
from tests.test_capture_context import _load_fixture

FPS = 30.0
_BODY = {
    "left_shoulder": (0.45, 0.35),
    "right_shoulder": (0.55, 0.35),
    "left_hip": (0.46, 0.6),
    "right_hip": (0.54, 0.6),
    "left_ankle": (0.45, 0.9),
    "right_ankle": (0.55, 0.9),
    "right_wrist": (0.6, 0.3),
}


def _bump(n: int, center: int, height: float, sigma: float) -> list[float]:
    return [height * math.exp(-0.5 * ((i - center) / sigma) ** 2) for i in range(n)]


def _motion(speeds: list[float]) -> MotionSequence:
    return MotionSequence(
        video="v.mp4",
        frames=[
            MotionFrame(frame_index=i, timestamp=i / FPS, right_wrist_speed=s)
            for i, s in enumerate(speeds)
        ],
    )


def _pose(n: int, *, shrink: set[int] = frozenset(), wrist_conf: float = 0.9) -> PoseSequence:
    frames = []
    for i in range(n):
        scale = 0.1 if i in shrink else 1.0
        kps = {
            name: Keypoint(
                x=0.5 + (x - 0.5) * scale,
                y=0.6 + (y - 0.6) * scale,
                confidence=wrist_conf if name == "right_wrist" else 0.9,
            )
            for name, (x, y) in _BODY.items()
        }
        frames.append(PoseFrame(frame_index=i, timestamp=i / FPS, keypoints=kps))
    return PoseSequence(video="v.mp4", frames=frames)


def _with_baseline(values: list[float]) -> list[float]:
    return [0.05 + v for v in values]


def test_single_clean_peak_is_chosen_with_high_confidence():
    speeds = _with_baseline(_bump(90, 50, 1.5, 4.0))
    result = analyze_contact_peaks(_motion(speeds), _pose(90))
    assert result.chosen is not None
    assert result.chosen.frame_index == 50
    assert result.chosen.width_frames >= 5
    assert result.warnings == []
    assert result.confidence > 0.9


def test_lone_one_frame_spike_is_flagged_and_low_confidence():
    speeds = [0.1] * 90
    speeds[40] = 2.0
    result = analyze_contact_peaks(_motion(speeds), _pose(90))
    assert result.chosen.frame_index == 40
    assert WARNING_CONTACT_SPIKE_PEAK in result.warnings
    assert result.confidence < 0.8


def test_spike_does_not_outrank_a_real_swing():
    speeds = _with_baseline(_bump(120, 90, 1.5, 4.0))
    speeds[30] = 2.5  # one-frame glitch higher than the real swing
    result = analyze_contact_peaks(_motion(speeds), _pose(120))
    assert result.chosen.frame_index == 90
    assert WARNING_CONTACT_SPIKE_PEAK not in result.warnings
    # A higher competing peak still makes the choice ambiguous.
    assert WARNING_CONTACT_AMBIGUOUS_PEAKS in result.warnings


def test_two_similar_peaks_are_ambiguous():
    speeds = _with_baseline(
        [a + b for a, b in zip(_bump(120, 30, 1.5, 4.0), _bump(120, 90, 1.4, 4.0))]
    )
    clean = analyze_contact_peaks(
        _motion(_with_baseline(_bump(120, 30, 1.5, 4.0))), _pose(120)
    )
    result = analyze_contact_peaks(_motion(speeds), _pose(120))
    assert result.chosen.frame_index == 30
    assert result.competitor_ratio == pytest.approx(1.4 / 1.5, abs=0.01)
    assert WARNING_CONTACT_AMBIGUOUS_PEAKS in result.warnings
    assert result.confidence < clean.confidence


def test_box_jump_near_peak_is_unstable_tracking():
    speeds = _with_baseline(_bump(90, 50, 1.5, 4.0))
    result = analyze_contact_peaks(_motion(speeds), _pose(90, shrink={49}))
    assert WARNING_CONTACT_UNSTABLE_TRACKING in result.warnings
    stable = analyze_contact_peaks(_motion(speeds), _pose(90))
    assert result.confidence < stable.confidence


def test_low_wrist_confidence_is_unstable_tracking():
    speeds = _with_baseline(_bump(90, 50, 1.5, 4.0))
    result = analyze_contact_peaks(_motion(speeds), _pose(90, wrist_conf=0.3))
    assert WARNING_CONTACT_UNSTABLE_TRACKING in result.warnings


def test_occluded_wrist_at_real_peak_does_not_move_contact():
    speeds = _with_baseline(
        [a + b for a, b in zip(_bump(120, 30, 0.6, 4.0), _bump(120, 90, 1.5, 4.0))]
    )
    result = analyze_contact_peaks(_motion(speeds), _pose(120, wrist_conf=0.3))
    assert result.chosen.frame_index == 90
    assert WARNING_CONTACT_UNSTABLE_TRACKING in result.warnings


def test_peak_confidence_feeds_contact_confidence(tmp_path):
    raw, meta = _load_fixture()
    kin = pose_service.kinematics_from_raw_pose(
        raw,
        input_path=tmp_path / "clip.mp4",
        output_path=tmp_path / "clip_pose.mp4",
        stroke_type="FOREHAND_CLEAR",
        handedness="RIGHT",
        video_fps=meta["fps"],
        video_width=meta["width"],
        video_height=meta["height"],
    )
    peaks = kin.contact_peaks
    assert peaks is not None and peaks.chosen is not None
    assert kin.motion_sequence.peaks["right_wrist_speed"].frame_index == (
        peaks.chosen.frame_index
    )
    state = pose_service.build_final_state(kin)
    assert state.contact.contact_peak_confidence == pytest.approx(peaks.confidence)
    assert state.contact.confidence == pytest.approx(
        kin.initial_phases.confidence * peaks.confidence
    )
    assert state.contact.warnings == peaks.warnings
