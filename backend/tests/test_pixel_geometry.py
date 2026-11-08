"""Geometry must be measured in pixels, not in per-axis normalized coordinates."""

from __future__ import annotations

import math

import pytest

from app.processing.angles import compute_angle_sequence
from app.processing.capture_context import swap_left_right
from app.processing.motion import compute_motion_derivatives
from app.processing.stroke_metrics import median_torso_length
from app.processing.temporal import preprocess_pose_sequence
from app.processing.trunk_rotation import trunk_rotation_at_frame
from app.schemas.angles import AngleFrame, AngleSequence
from app.schemas.pose import Keypoint, PoseFrame, PoseSequence

LANDSCAPE = (1280, 720)  # 16:9
PORTRAIT = (720, 1280)  # 9:16


def _norm(px: float, py: float, size: tuple[int, int]) -> Keypoint:
    return Keypoint(x=px / size[0], y=py / size[1], confidence=0.95)


def _right_angle_frame(size: tuple[int, int], index: int = 0) -> PoseFrame:
    """Elbow at the frame centre; upper arm and forearm 45° off the axes, 90° apart."""
    cx, cy = size[0] / 2.0, size[1] / 2.0
    return PoseFrame(
        frame_index=index,
        timestamp=index / 30.0,
        keypoints={
            "right_shoulder": _norm(cx + 150.0, cy - 150.0, size),
            "right_elbow": _norm(cx, cy, size),
            "right_wrist": _norm(cx + 150.0, cy + 150.0, size),
        },
    )


@pytest.mark.parametrize("size", [LANDSCAPE, PORTRAIT], ids=["16:9", "9:16"])
def test_right_angle_measures_90_degrees_in_any_aspect(size) -> None:
    seq = PoseSequence(
        video="clip.mp4",
        frames=[_right_angle_frame(size)],
        frame_width=size[0],
        frame_height=size[1],
    )
    elbow = compute_angle_sequence(seq).frames[0].right_elbow
    assert elbow == pytest.approx(90.0, abs=1e-6)

    # Without the frame size the per-axis normalization distorts it.
    unscaled = compute_angle_sequence(PoseSequence(video="clip.mp4", frames=seq.frames))
    assert abs(unscaled.frames[0].right_elbow - 90.0) > 20.0


@pytest.mark.parametrize("size", [LANDSCAPE, PORTRAIT], ids=["16:9", "9:16"])
def test_trunk_rotation_uses_pixel_angles(size) -> None:
    # Shoulder line tilted 30° in pixels, hip line horizontal.
    cx, cy = size[0] / 2.0, size[1] / 2.0
    dx, dy = 100.0 * math.cos(math.radians(30.0)), 100.0 * math.sin(math.radians(30.0))
    frame = PoseFrame(
        frame_index=0,
        timestamp=0.0,
        keypoints={
            "left_shoulder": _norm(cx - dx, cy - 200.0 - dy, size),
            "right_shoulder": _norm(cx + dx, cy - 200.0 + dy, size),
            "left_hip": _norm(cx - 80.0, cy, size),
            "right_hip": _norm(cx + 80.0, cy, size),
        },
    )
    assert trunk_rotation_at_frame(frame, scale=(float(size[0]), float(size[1]))) == (
        pytest.approx(30.0, abs=1e-6)
    )


@pytest.mark.parametrize("size", [LANDSCAPE, PORTRAIT], ids=["16:9", "9:16"])
def test_wrist_speed_and_torso_length_are_in_pixels(size) -> None:
    # Wrist moves 60 px right and 80 px down (100 px) in 0.1 s → 1000 px/s.
    frames = [
        PoseFrame(
            frame_index=i,
            timestamp=i * 0.1,
            keypoints={
                "right_wrist": _norm(300.0 + 60.0 * i, 300.0 + 80.0 * i, size),
                "left_shoulder": _norm(300.0, 200.0, size),
                "right_shoulder": _norm(340.0, 200.0, size),
                "left_hip": _norm(300.0 + 30.0, 200.0 + 40.0, size),
                "right_hip": _norm(340.0 + 30.0, 200.0 + 40.0, size),
            },
        )
        for i in range(2)
    ]
    pose = PoseSequence(
        video="clip.mp4", frames=frames, frame_width=size[0], frame_height=size[1]
    )
    angles = AngleSequence(
        video="clip.mp4",
        frames=[AngleFrame(frame_index=f.frame_index, timestamp=f.timestamp) for f in frames],
    )
    motion = compute_motion_derivatives(pose, angles)
    assert motion.frames[1].right_wrist_speed == pytest.approx(1000.0)

    pose_by = {f.frame_index: f for f in frames}
    torso = median_torso_length(pose_by, 0, 1, scale=pose.pixel_scale())
    assert torso == pytest.approx(50.0)  # (30, 40) px offset


def test_frame_size_survives_preprocessing_swap_and_serialization() -> None:
    seq = PoseSequence(
        video="clip.mp4",
        frames=[_right_angle_frame(PORTRAIT, i) for i in range(5)],
        frame_width=PORTRAIT[0],
        frame_height=PORTRAIT[1],
    )
    smoothed = preprocess_pose_sequence(
        seq, confidence_threshold=0.5, max_gap=3, savgol_window=5, savgol_polyorder=2
    )
    swapped = swap_left_right(smoothed)
    for out in (smoothed, swapped):
        assert (out.frame_width, out.frame_height) == PORTRAIT
        assert out.pixel_scale() == (720.0, 1280.0)
    payload = swapped.to_dict()
    assert payload["frame_width"] == 720
    assert payload["frame_height"] == 1280
    assert PoseSequence(video="x").pixel_scale() == (1.0, 1.0)
