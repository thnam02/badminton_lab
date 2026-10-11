"""Kinematic contact peak selection and contact_peak_confidence."""

from __future__ import annotations

import math

import pytest

from app.processing.contact_peaks import (
    WARNING_CONTACT_AMBIGUOUS_PEAKS,
    WARNING_CONTACT_SPIKE_PEAK,
    WARNING_CONTACT_UNSTABLE_TRACKING,
    WARNING_MULTIPLE_SWINGS_DETECTED,
    analyze_contact_peaks,
)
from app.processing.contact_resolver import (
    WARNING_CONTACT_NOT_VERIFIED_BY_SHUTTLE,
    shuttle_detected_near,
)
from app.schemas.contact import ContactEvent
from app.schemas.evidence import ContactEvidence
from app.schemas.shuttle import ShuttlePoint, ShuttleTrajectory
from app.schemas.keyframes import KeyframeSet
from app.schemas.stroke_metrics import StrokeMetrics
from app.schemas.motion import MotionFrame, MotionSequence
from app.schemas.phases import PhaseSequence
from app.schemas.pose import Keypoint, PoseFrame, PoseSequence
from app.schemas.technique import TechniqueEvaluation
from app.schemas.video_quality import VideoQualityReport
from app.services.evidence_packager import EvidencePackager
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


def _two_bumps(n: int, a: int, b: int, ha: float = 1.5, hb: float = 1.2) -> list[float]:
    return _with_baseline(
        [x + y for x, y in zip(_bump(n, a, ha, 4.0), _bump(n, b, hb, 4.0))]
    )


def test_two_swings_are_detected_and_best_is_chosen():
    result = analyze_contact_peaks(_motion(_two_bumps(150, 110, 40)), _pose(150))
    assert [s.frame_index for s in result.swings] == [40, 110]
    assert [s.chosen for s in result.swings] == [False, True]
    assert result.chosen.frame_index == 110
    assert WARNING_MULTIPLE_SWINGS_DETECTED in result.warnings
    chosen = next(s for s in result.swings if s.chosen)
    assert chosen.confidence == pytest.approx(result.confidence)


def test_peaks_within_one_second_are_one_swing():
    result = analyze_contact_peaks(_motion(_two_bumps(150, 80, 60)), _pose(150))
    assert len(result.candidates) == 2
    assert len(result.swings) == 1
    assert WARNING_MULTIPLE_SWINGS_DETECTED not in result.warnings


def test_spike_is_not_counted_as_a_swing():
    speeds = _with_baseline(_bump(150, 110, 1.5, 4.0))
    speeds[30] = 2.5
    result = analyze_contact_peaks(_motion(speeds), _pose(150))
    assert [s.frame_index for s in result.swings] == [110]


def test_evidence_reports_swings_and_chosen_frame():
    swings = [
        {"frame_index": 40, "timestamp": 1.33, "speed": 1.2, "confidence": 0.5, "chosen": False},
        {"frame_index": 110, "timestamp": 3.67, "speed": 1.5, "confidence": 0.6, "chosen": True},
    ]
    contact = ContactEvent(
        contact_type="KINEMATIC_ESTIMATE",
        frame_index=110,
        timestamp=3.67,
        confidence=0.6,
        swing_candidates=swings,
    )
    package = EvidencePackager().package(
        video_quality=VideoQualityReport(video="v.mp4", analysis_confidence=0.8),
        phases=PhaseSequence(video="v.mp4"),
        metrics=StrokeMetrics(video="v.mp4"),
        technique=TechniqueEvaluation(video="v.mp4"),
        keyframes=KeyframeSet(video="v.mp4", output_dir=""),
        contact=contact,
    )
    payload = package.to_dict()
    assert payload["evidence_version"] == "1.4.0"
    assert payload["swing_count"] == 2
    assert payload["swing_candidates"] == swings
    assert "frame 110 was analysed" in payload["notes"]
    assert "frames 40" in payload["notes"]


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
    assert state.contact.warnings == [
        *peaks.warnings,
        WARNING_CONTACT_NOT_VERIFIED_BY_SHUTTLE,
    ]


def _shuttle(frames: range, *, interpolated: bool = False) -> ShuttleTrajectory:
    return ShuttleTrajectory(
        video="v.mp4",
        backend="test",
        fps=FPS,
        width=720,
        height=1280,
        frames=[
            ShuttlePoint(
                frame_index=i,
                timestamp=i / FPS,
                x=0.5,
                y=0.2,
                visible=True,
                confidence=0.9,
                interpolated=interpolated,
            )
            for i in frames
        ],
    )


def _fixture_contact(tmp_path, shuttle):
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
    return pose_service.build_final_state(kin, shuttle=shuttle)


def test_contact_without_shuttle_is_not_verified(tmp_path):
    state = _fixture_contact(tmp_path, None)
    assert state.contact.shuttle_verified is False
    assert WARNING_CONTACT_NOT_VERIFIED_BY_SHUTTLE in state.contact.warnings
    assert WARNING_CONTACT_NOT_VERIFIED_BY_SHUTTLE in state.video_quality.warnings
    evidence = ContactEvidence.from_contact_event(state.contact).to_dict()
    assert evidence["shuttle_verified"] is False


def test_shuttle_far_from_contact_or_interpolated_is_not_verified(tmp_path):
    contact = _fixture_contact(tmp_path, None).contact.frame_index
    assert not shuttle_detected_near(_shuttle(range(0, 10)), contact)
    assert not shuttle_detected_near(
        _shuttle(range(contact - 3, contact + 4), interpolated=True), contact
    )


def test_shuttle_near_contact_verifies_it(tmp_path):
    contact = _fixture_contact(tmp_path, None).contact.frame_index
    state = _fixture_contact(tmp_path, _shuttle(range(contact - 3, contact + 4)))
    assert state.contact.shuttle_verified is True
    assert WARNING_CONTACT_NOT_VERIFIED_BY_SHUTTLE not in state.contact.warnings
