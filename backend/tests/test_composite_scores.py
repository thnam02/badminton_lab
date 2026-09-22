"""Unit tests for composite score helpers (canonical formulas)."""

from __future__ import annotations

import pytest

from app.processing.composite_scores import (
    base_score,
    chain_score,
    clip,
    compute_composite_scores,
    power_score,
    range_score,
    weighted_average,
)
from app.processing.trunk_rotation import trunk_rotation_deg
from app.schemas.pose import Keypoint


def test_clip_and_range_score_basics() -> None:
    assert clip(1.5) == 1.0
    assert clip(-0.2) == 0.0
    assert range_score(None, ideal_min=0.0, ideal_max=1.0, tolerance=1.0) is None
    assert range_score(0.5, ideal_min=0.0, ideal_max=1.0, tolerance=1.0) == 1.0
    assert range_score(-1.0, ideal_min=0.0, ideal_max=1.0, tolerance=1.0) == 0.0
    assert range_score(-0.5, ideal_min=0.0, ideal_max=1.0, tolerance=1.0) == 0.5


def test_weighted_average_renormalizes_when_term_missing() -> None:
    full = weighted_average((1.0, 0.5), (0.0, 0.5))
    assert full == pytest.approx(0.5)
    # Missing second term → remaining weight renormalizes to 1.0 (not deflated to 0.5).
    partial = weighted_average((1.0, 0.5), (None, 0.5))
    assert partial == pytest.approx(1.0)
    assert weighted_average((None, 1.0)) is None


def test_renormalized_chain_without_leg_drive_stays_on_0_1_scale() -> None:
    """Clear-like metrics omit knee_contribution_deg; score must not deflate."""
    complete = {
        "kinetic_chain_order": "hip_shoulder_elbow",
        "kinetic_chain_hip_shoulder_gap_frames": 4,
        "kinetic_chain_shoulder_elbow_gap_frames": 3,
        "peak_elbow_omega_offset_frames": -3,
        "knee_contribution_deg": 20.0,
        "peak_trunk_rotation_deg": 25.0,
    }
    missing_leg = {k: v for k, v in complete.items() if k != "knee_contribution_deg"}
    s_full = chain_score(complete)
    s_partial = chain_score(missing_leg)
    assert s_full is not None and s_partial is not None
    assert 0.0 <= s_partial <= 1.0
    # With all remaining terms at "ideal", partial stays near 1.0 (not ~0.85).
    assert s_partial == pytest.approx(1.0, abs=0.05)
    assert abs(s_full - s_partial) < 0.2


def test_trunk_rotation_orthogonal_lines_approx_90() -> None:
    value = trunk_rotation_deg(
        Keypoint(0.0, 0.0, 1.0),
        Keypoint(1.0, 0.0, 1.0),
        Keypoint(0.5, 0.0, 1.0),
        Keypoint(0.5, 1.0, 1.0),
    )
    assert value == pytest.approx(90.0)


def test_power_score_canonical_shape() -> None:
    score = power_score(
        peak_speed_percentile=0.8,
        follow_through_ratio=0.6,
        accel_fraction=0.40,
    )
    assert score is not None
    # 0.8*0.5 + 1.0*0.3 + 1.0*0.2 = 0.9
    assert score == pytest.approx(0.9, abs=0.02)

    # Missing speed percentile renormalizes onto retention + timing.
    no_speed = power_score(None, 0.6, 0.40)
    assert no_speed is not None
    assert no_speed == pytest.approx(1.0, abs=0.05)


def test_base_score_anchors_on_technique_threshold() -> None:
    # At threshold 0.58 → height score 0; well above (y=0.38) → strong height score.
    high = base_score(prep_knee_angle=125.0, contact_wrist_y=0.38)
    low = base_score(prep_knee_angle=125.0, contact_wrist_y=0.58)
    assert high is not None and low is not None
    assert high > low
    assert low == pytest.approx(0.5, abs=0.05)  # knee ideal 1.0 * 0.5 + height 0 * 0.5


def test_compute_composite_available_false_when_empty() -> None:
    payload = compute_composite_scores({})
    assert payload["available"] is False
    assert payload["chain_score"] is None
    assert payload["power_score"] is None
    assert payload["base_score"] is None


def test_compute_composite_with_shared_power_inputs() -> None:
    metrics = {
        "kinetic_chain_order": "hip_shoulder_elbow",
        "kinetic_chain_hip_shoulder_gap_frames": 4,
        "kinetic_chain_shoulder_elbow_gap_frames": 3,
        "peak_elbow_omega_offset_frames": -3,
        "peak_trunk_rotation_deg": 25.0,
        "follow_through_speed_ratio": 0.5,
        "acceleration_phase_fraction": 0.40,
        "preparation_knee_angle_deg": 125.0,
        "contact_wrist_y_normalized": 0.40,
    }
    payload = compute_composite_scores(metrics, peak_speed_percentile=0.7)
    assert payload["available"] is True
    assert payload["chain_score"] is not None
    assert payload["power_score"] is not None
    assert payload["base_score"] is not None
    assert payload["components"]["power"]["speed_score_source"] == "explicit_percentile"


def test_stopgap_speed_score_from_peak_wrist_feeds_power() -> None:
    from app.processing.composite_scores import (
        _PEAK_WRIST_SPEED_STOPGAP_MAX,
        _PEAK_WRIST_SPEED_STOPGAP_MIN,
        stopgap_speed_score_from_peak_wrist,
    )

    mid = (_PEAK_WRIST_SPEED_STOPGAP_MIN + _PEAK_WRIST_SPEED_STOPGAP_MAX) / 2.0
    assert stopgap_speed_score_from_peak_wrist(mid) == pytest.approx(0.5)
    assert stopgap_speed_score_from_peak_wrist(_PEAK_WRIST_SPEED_STOPGAP_MIN) == 0.0
    assert stopgap_speed_score_from_peak_wrist(_PEAK_WRIST_SPEED_STOPGAP_MAX) == 1.0
    assert stopgap_speed_score_from_peak_wrist(None) is None

    # Real analysis path: no explicit percentile → stopgap from peak_wrist_speed.
    metrics = {
        "peak_wrist_speed": mid,
        "follow_through_speed_ratio": 0.6,
        "acceleration_phase_fraction": 0.40,
    }
    payload = compute_composite_scores(metrics)
    assert payload["power_score"] is not None
    assert payload["components"]["power"]["peak_speed_percentile"] == pytest.approx(0.5)
    assert (
        payload["components"]["power"]["speed_score_source"]
        == "stopgap_minmax_peak_wrist_speed"
    )
    # 0.5*0.5 + 1.0*0.3 + 1.0*0.2 = 0.75
    assert payload["power_score"] == pytest.approx(0.75, abs=0.02)

    # Faster wrist → higher power when retention/timing held constant.
    faster = compute_composite_scores({**metrics, "peak_wrist_speed": mid + 1.0})
    assert faster["power_score"] is not None
    assert faster["power_score"] > payload["power_score"]
