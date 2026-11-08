"""Racket-arm visibility near contact feeds quality and technique confidence."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.processing.strokes import get_stroke_analyzer
from app.processing.temporal import preprocess_pose_sequence
from app.processing.video_quality import (
    WARNING_LOW_RACKET_ARM_AT_CONTACT,
    apply_contact_visibility,
    racket_arm_visibility_at_contact,
)
from app.schemas.pose import Keypoint, PoseFrame, PoseSequence
from app.schemas.video_quality import VideoQualityReport
from app.services.pose_service import pose_service
from tests.test_capture_context import _load_fixture

_ARM = ("right_shoulder", "right_elbow", "right_wrist")


def _arm_sequence(n: int, hidden: set[int] = frozenset()) -> PoseSequence:
    frames = []
    for i in range(n):
        kps = {
            name: Keypoint(x=0.5 + 0.01 * i, y=0.3 + 0.1 * j, confidence=0.9)
            for j, name in enumerate(_ARM)
        }
        if i in hidden:
            kps["right_wrist"] = Keypoint(x=0.0, y=0.0, confidence=0.1)
        frames.append(PoseFrame(frame_index=i, timestamp=i / 30, keypoints=kps))
    return PoseSequence(video="v.mp4", frames=frames)


def test_interpolated_joints_are_recorded_per_frame():
    smoothed = preprocess_pose_sequence(_arm_sequence(20, hidden={9, 10}))
    assert smoothed.frames[9].interpolated == {"right_wrist"}
    assert smoothed.frames[10].interpolated == {"right_wrist"}
    assert smoothed.frames[8].interpolated == set()
    # Interpolated confidence is borrowed from neighbours, so it looks "good".
    assert smoothed.frames[9].keypoints["right_wrist"].confidence >= 0.5


def test_visibility_at_contact_ignores_interpolated_frames():
    smoothed = preprocess_pose_sequence(_arm_sequence(30, hidden={13, 14, 15, 16}))
    vis = racket_arm_visibility_at_contact(smoothed, 15)
    assert vis == pytest.approx(7 / 11)
    assert racket_arm_visibility_at_contact(smoothed, 25) == 1.0
    assert racket_arm_visibility_at_contact(smoothed, None) is None


def test_apply_contact_visibility_caps_and_warns_only_below_threshold():
    report = VideoQualityReport(video="v.mp4", analysis_confidence=0.9, warnings=[])
    low = apply_contact_visibility(report, 0.6)
    assert low.analysis_confidence == pytest.approx(0.6)
    assert WARNING_LOW_RACKET_ARM_AT_CONTACT in low.warnings
    assert low.metrics.racket_arm_visibility_at_contact == pytest.approx(0.6)
    assert report.warnings == []  # input report not mutated

    ok = apply_contact_visibility(report, 0.8)
    assert ok.analysis_confidence == pytest.approx(0.9)
    assert ok.warnings == []


def _final(raw: PoseSequence, meta: dict, tmp_path: Path, stroke: str, name: str):
    kin = pose_service.kinematics_from_raw_pose(
        raw,
        input_path=tmp_path / f"{name}.mp4",
        output_path=tmp_path / f"{name}_pose.mp4",
        stroke_type=stroke,
        handedness="RIGHT",
        camera_view="SIDE",
        video_fps=meta["fps"],
        video_width=meta["width"],
        video_height=meta["height"],
    )
    state = pose_service.build_final_state(kin)
    analyzer = get_stroke_analyzer(stroke)
    metrics = analyzer.extract_metrics(state)
    technique = analyzer.evaluate(
        state,
        metrics,
        quality_confidence=float(state.video_quality.analysis_confidence),
        pose_confidence=state.video_quality.metrics.racket_arm_visibility_at_contact,
        handedness="RIGHT",
        camera_view="SIDE",
    )
    return kin, state, technique


def _issue_confidences(technique) -> list[float]:
    return [float(i.confidence) for i in technique.issues]


@pytest.mark.parametrize("stroke", ["FOREHAND_CLEAR", "FOREHAND_SMASH"])
def test_fully_visible_arm_at_contact_changes_nothing(tmp_path, stroke):
    raw, meta = _load_fixture()
    kin, state, technique = _final(raw, meta, tmp_path, stroke, "visible")
    q = state.video_quality
    assert q.metrics.racket_arm_visibility_at_contact == 1.0
    assert q.analysis_confidence == kin.quality_report.analysis_confidence
    assert WARNING_LOW_RACKET_ARM_AT_CONTACT not in q.warnings

    analyzer = get_stroke_analyzer(stroke)
    default_pose = analyzer.evaluate(
        state,
        analyzer.extract_metrics(state),
        quality_confidence=float(q.analysis_confidence),
        handedness="RIGHT",
        camera_view="SIDE",
    )
    assert _issue_confidences(technique) == pytest.approx(
        _issue_confidences(default_pose)
    )


@pytest.mark.parametrize("stroke", ["FOREHAND_CLEAR", "FOREHAND_SMASH"])
def test_wrist_hidden_around_contact_lowers_confidence(tmp_path, stroke):
    raw, meta = _load_fixture()
    _, base_state, base_technique = _final(raw, meta, tmp_path, stroke, "base")
    contact = base_state.contact.frame_index
    assert contact is not None

    occluded = copy.deepcopy(raw)
    for frame in occluded.frames:
        if contact - 1 <= frame.frame_index <= contact + 2:
            wrist = frame.keypoints["right_wrist"]
            frame.keypoints["right_wrist"] = Keypoint(
                x=wrist.x, y=wrist.y, confidence=0.1
            )
    _, state, technique = _final(occluded, meta, tmp_path, stroke, "occluded")

    q = state.video_quality
    vis = q.metrics.racket_arm_visibility_at_contact
    assert vis is not None and vis < 0.70
    assert WARNING_LOW_RACKET_ARM_AT_CONTACT in q.warnings
    assert q.analysis_confidence <= vis
    assert q.analysis_confidence < base_state.video_quality.analysis_confidence
    assert max(_issue_confidences(technique)) < min(
        _issue_confidences(base_technique)
    )
