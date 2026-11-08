"""Trunk rotation: undirected line angle in [0, 90] and swing-window angular velocity."""

from __future__ import annotations

import math

import pytest

from app.processing.trunk_rotation import (
    peak_trunk_rotation_velocity_in_window,
    trunk_rotation_deg,
)
from app.schemas.pose import Keypoint, PoseFrame


def _line(angle_deg: float, *, cx: float = 0.5, cy: float = 0.5) -> tuple[Keypoint, Keypoint]:
    """Left/right keypoints 0.2 apart along ``angle_deg`` (image coordinates)."""
    dx = 0.1 * math.cos(math.radians(angle_deg))
    dy = 0.1 * math.sin(math.radians(angle_deg))
    return Keypoint(cx - dx, cy - dy, 1.0), Keypoint(cx + dx, cy + dy, 1.0)


def _rotation(shoulder_deg: float, hip_deg: float) -> float:
    ls, rs = _line(shoulder_deg, cy=0.3)
    lh, rh = _line(hip_deg, cy=0.6)
    return trunk_rotation_deg(ls, rs, lh, rh)


def test_parallel_lines_are_zero() -> None:
    assert _rotation(0.0, 0.0) == pytest.approx(0.0)
    assert _rotation(25.0, 25.0) == pytest.approx(0.0)


def test_antiparallel_lines_are_zero() -> None:
    # Same line, opposite left/right order (keypoints crossed in 2D).
    assert _rotation(0.0, 180.0) == pytest.approx(0.0, abs=1e-9)


def test_lines_at_170_degrees_are_10() -> None:
    assert _rotation(170.0, 0.0) == pytest.approx(10.0)
    assert _rotation(0.0, 170.0) == pytest.approx(10.0)
    assert _rotation(-170.0, 0.0) == pytest.approx(10.0)


def test_perpendicular_lines_are_90() -> None:
    assert _rotation(90.0, 0.0) == pytest.approx(90.0)
    assert _rotation(0.0, -90.0) == pytest.approx(90.0)


@pytest.mark.parametrize("shoulder", [0.0, 37.0, 95.0, 160.0, 200.0, 271.0, -45.0])
def test_result_always_in_0_90(shoulder: float) -> None:
    assert 0.0 <= _rotation(shoulder, 12.0) <= 90.0


def _frame(i: int, shoulder_deg: float, fps: float = 30.0) -> PoseFrame:
    ls, rs = _line(shoulder_deg, cy=0.3)
    lh, rh = _line(0.0, cy=0.6)
    return PoseFrame(
        frame_index=i,
        timestamp=i / fps,
        keypoints={
            "left_shoulder": ls,
            "right_shoulder": rs,
            "left_hip": lh,
            "right_hip": rh,
        },
    )


def test_peak_velocity_within_window_only() -> None:
    # Rotation (deg) per frame: big jump at 2→3 (outside window), peak inside at 7→8.
    angles = [0, 0, 0, 40, 40, 40, 42, 44, 64, 66]
    frames = [_frame(i, a) for i, a in enumerate(angles)]
    omega, frame = peak_trunk_rotation_velocity_in_window(frames, 5, 9)
    assert frame == 8
    assert omega == pytest.approx(20.0 * 30.0, rel=1e-6)


def test_peak_velocity_skips_gaps() -> None:
    frames = [_frame(0, 0), _frame(1, 5), _frame(3, 60), _frame(4, 62)]
    omega, frame = peak_trunk_rotation_velocity_in_window(frames, 0, 4)
    # 1→3 is not consecutive, so the 55° jump is ignored.
    assert frame == 1
    assert omega == pytest.approx(5.0 * 30.0, rel=1e-6)
