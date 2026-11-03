"""Physiological plausibility gate: drop, record and warn on impossible values."""

from __future__ import annotations

import pytest

from app.processing.composite_scores import compute_composite_scores
from app.processing.plausibility import (
    PLAUSIBLE_RANGES_DEG,
    WARNING_IMPLAUSIBLE_MEASUREMENT,
    apply_plausibility_gate,
)
from app.processing.tiered_technique import evaluate_tiered
from app.schemas.clear_metrics import ForehandClearMetrics
from app.schemas.stroke_metrics import StrokeMetrics


def _metrics(cls=StrokeMetrics, **overrides):
    base = dict(
        video="t.mp4",
        estimated_contact_frame_index=10,
        phase_confidence=0.9,
        contact_confidence=0.9,
        contact_elbow_angle_deg=150.0,
        contact_knee_angle_deg=160.0,
        preparation_knee_angle_deg=140.0,
        knee_contribution_deg=20.0,
        contact_shoulder_angle_deg=110.0,
        peak_trunk_rotation_deg=30.0,
    )
    base.update(overrides)
    return cls(**base)


def test_ranges_match_spec() -> None:
    assert PLAUSIBLE_RANGES_DEG == {
        "elbow": (60.0, 180.0),
        "knee": (60.0, 180.0),
        "shoulder": (0.0, 180.0),
        "trunk_rotation": (0.0, 90.0),
    }


def test_in_range_values_are_untouched() -> None:
    m = _metrics()
    apply_plausibility_gate(m)
    assert m.contact_elbow_angle_deg == 150.0
    assert m.implausible_measurements == []
    assert m.measurement_warnings == []


@pytest.mark.parametrize(("value", "kept"), [(60.0, True), (180.0, True), (59.9, False), (7.2, False)])
def test_elbow_boundaries_inclusive(value: float, kept: bool) -> None:
    m = _metrics(contact_elbow_angle_deg=value)
    apply_plausibility_gate(m)
    assert (m.contact_elbow_angle_deg == value) is kept
    assert (m.measurement_warnings == [WARNING_IMPLAUSIBLE_MEASUREMENT]) is (not kept)


def test_implausible_value_is_recorded() -> None:
    m = _metrics(contact_elbow_angle_deg=7.2, peak_trunk_rotation_deg=95.0)
    apply_plausibility_gate(m)
    recorded = {d["metric"]: d for d in m.implausible_measurements}
    assert recorded["contact_elbow_angle_deg"]["value"] == pytest.approx(7.2)
    assert recorded["contact_elbow_angle_deg"]["plausible_min"] == 60.0
    assert recorded["peak_trunk_rotation_deg"]["plausible_max"] == 90.0
    assert m.peak_trunk_rotation_deg is None


def test_implausible_knee_drops_derived_knee_contribution() -> None:
    m = _metrics(contact_knee_angle_deg=40.0)
    apply_plausibility_gate(m)
    assert m.contact_knee_angle_deg is None
    assert m.knee_contribution_deg is None
    derived = next(d for d in m.implausible_measurements if d["metric"] == "knee_contribution_deg")
    assert "contact_knee_angle_deg" in derived["reason"]


def test_gated_elbow_cannot_fire_bent_elbow_rule() -> None:
    m = _metrics(contact_elbow_angle_deg=7.2)
    before = evaluate_tiered(m, camera_view="SIDE", quality_confidence=0.9, pose_confidence=0.9)
    assert "BENT_ELBOW_AT_CONTACT" in {i.code for i in before.issues}
    apply_plausibility_gate(m)
    after = evaluate_tiered(m, camera_view="SIDE", quality_confidence=0.9, pose_confidence=0.9)
    assert "BENT_ELBOW_AT_CONTACT" not in {i.code for i in after.issues}


def test_gated_values_leave_composite_scores() -> None:
    m = _metrics(contact_knee_angle_deg=30.0, peak_trunk_rotation_deg=120.0)
    apply_plausibility_gate(m)
    scores = compute_composite_scores(m.to_dict())
    assert scores["components"]["chain"]["leg_drive"] is None
    assert scores["components"]["chain"]["trunk_rotation"] is None


def test_clear_metrics_are_gated_too() -> None:
    m = _metrics(ForehandClearMetrics, backswing_min_elbow_angle_deg=20.0)
    apply_plausibility_gate(m)
    assert m.backswing_min_elbow_angle_deg is None
    assert m.measurement_warnings == [WARNING_IMPLAUSIBLE_MEASUREMENT]
