"""Tiered technique rules: boundaries, view gating, severity caps, confidence gates."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.processing.reference_profiles import build_provisional_smash_right_side
from app.processing.technique_rules_config import (
    BENT_ELBOW_AT_CONTACT,
    KINETIC_CHAIN_ORDER,
    LATE_ELBOW_ACCELERATION,
    LIMITED_LEG_DRIVE,
    LOW_CONTACT_POINT,
    LOW_RACKET_PREPARATION,
    STIFF_PREPARATION_KNEE,
    TieredRulesConfig,
)
from app.processing.tiered_technique import evaluate_tiered
from app.schemas.clear_metrics import ForehandClearMetrics
from app.schemas.stroke_metrics import StrokeMetrics
from app.schemas.technique import TECHNIQUE_RULE_VERSION_TIERED
from app.schemas.technique_calibration import IssueStatus

RETIRED_CODES = {
    "INSUFFICIENT_ELBOW_EXTENSION",
    "LOW_KNEE_CONTRIBUTION",
    "PREPARATION_KNEE_OUT_OF_RANGE",
    "POOR_ARM_ACCELERATION_TIMING",
    "LOW_CONTACT_POSTURE",
    "WEAK_FOLLOW_THROUGH",
    "LIMITED_CLEAR_PREPARATION",
    "INSUFFICIENT_ARM_EXTENSION",
    "POOR_PROXIMAL_DISTAL_TIMING",
    "RESTRICTED_FOLLOW_THROUGH",
    "SLOW_RECOVERY",
}


def _clean(cls=StrokeMetrics, **overrides):
    base = dict(
        video="t.mp4",
        estimated_contact_frame_index=10,
        phase_confidence=0.9,
        contact_confidence=0.9,
        contact_wrist_y_normalized=0.30,
        contact_window_min_wrist_y_normalized=0.30,
        contact_nose_y_normalized=0.40,
        swing_peak_elbow_omega_offset_frames=-1,
        swing_peak_shoulder_omega_offset_frames=-2,
        swing_peak_elbow_extension_offset_frames=-1,
        swing_peak_trunk_rotation_velocity_offset_frames=-2,
        backswing_end_wrist_y_normalized=0.30,
        backswing_end_shoulder_y_normalized=0.45,
        contact_elbow_angle_deg=150.0,
        knee_contribution_deg=10.0,
        preparation_knee_angle_deg=150.0,
    )
    base.update(overrides)
    return cls(**base)


def _eval(metrics, *, stroke="SMASH", camera_view=None, **kw):
    kw.setdefault("quality_confidence", 0.9)
    kw.setdefault("pose_confidence", 0.9)
    return evaluate_tiered(metrics, stroke_type=stroke, camera_view=camera_view, **kw)


def _codes(evaluation) -> dict[str, str]:
    return {i.code: i.status for i in evaluation.issues}


def test_clean_metrics_produce_no_issues_and_tiered_version():
    evaluation = _eval(_clean(), camera_view="SIDE")
    assert evaluation.issues == []
    assert evaluation.rule_version == TECHNIQUE_RULE_VERSION_TIERED
    assert evaluation.decision_mode == "tiered_rules"
    assert evaluation.reference_profile_id


@pytest.mark.parametrize(
    ("elbow_ext", "trunk", "fires"),
    [(-1, -2, False), (-3, -2, False), (-3, -1, True), (-4, -1, True), (-3, 5, True)],
)
def test_kinetic_chain_order_trunk_before_elbow_boundary(elbow_ext, trunk, fires):
    m = _clean(
        swing_peak_elbow_extension_offset_frames=elbow_ext,
        swing_peak_trunk_rotation_velocity_offset_frames=trunk,
    )
    codes = _codes(_eval(m, camera_view="SIDE"))
    assert (KINETIC_CHAIN_ORDER in codes) is fires
    if fires:
        assert codes[KINETIC_CHAIN_ORDER] == IssueStatus.MINOR.value


def test_kinetic_chain_order_is_tier2_side_only():
    m = _clean(
        swing_peak_elbow_extension_offset_frames=-6,
        swing_peak_trunk_rotation_velocity_offset_frames=0,
    )
    assert KINETIC_CHAIN_ORDER not in _codes(_eval(m))
    issue = next(i for i in _eval(m, camera_view="SIDE").issues if i.code == KINETIC_CHAIN_ORDER)
    assert issue.tier == 2
    assert issue.measured_value == pytest.approx(6.0)


def test_shoulder_before_elbow_no_longer_triggers_chain_rule():
    m = _clean(
        swing_peak_elbow_omega_offset_frames=-10,
        swing_peak_shoulder_omega_offset_frames=5,
    )
    assert KINETIC_CHAIN_ORDER not in _codes(_eval(m, camera_view="SIDE"))


def test_low_contact_point_uses_nose_not_absolute_height():
    assert LOW_CONTACT_POINT not in _codes(
        _eval(_clean(contact_window_min_wrist_y_normalized=0.40, contact_nose_y_normalized=0.40))
    )
    # Wrist at y=0.55 (old 0.42 band would flag) but still above a low-framed nose.
    assert LOW_CONTACT_POINT not in _codes(
        _eval(_clean(contact_window_min_wrist_y_normalized=0.55, contact_nose_y_normalized=0.60))
    )
    codes = _codes(
        _eval(_clean(contact_window_min_wrist_y_normalized=0.45, contact_nose_y_normalized=0.40))
    )
    assert codes[LOW_CONTACT_POINT] == IssueStatus.MODERATE.value


def test_low_contact_point_uses_highest_wrist_near_contact():
    # Wrist already dropping at the contact frame, but it was above the nose 2 frames earlier.
    m = _clean(
        contact_wrist_y_normalized=0.46,
        contact_window_min_wrist_y_normalized=0.37,
        contact_nose_y_normalized=0.43,
    )
    assert LOW_CONTACT_POINT not in _codes(_eval(m))


def test_late_elbow_acceleration_boundary_is_minor():
    m2 = _clean(swing_peak_elbow_omega_offset_frames=2, swing_peak_shoulder_omega_offset_frames=2)
    assert LATE_ELBOW_ACCELERATION not in _codes(_eval(m2))
    m3 = _clean(swing_peak_elbow_omega_offset_frames=3, swing_peak_shoulder_omega_offset_frames=3)
    assert _codes(_eval(m3))[LATE_ELBOW_ACCELERATION] == IssueStatus.MINOR.value


def test_low_racket_preparation_boundary_is_minor():
    level = _clean(backswing_end_wrist_y_normalized=0.45)
    assert LOW_RACKET_PREPARATION not in _codes(_eval(level))
    below = _clean(backswing_end_wrist_y_normalized=0.50)
    assert _codes(_eval(below))[LOW_RACKET_PREPARATION] == IssueStatus.MINOR.value


def test_missing_inputs_skip_rules():
    m = _clean(
        contact_nose_y_normalized=None,
        swing_peak_trunk_rotation_velocity_offset_frames=None,
        backswing_end_wrist_y_normalized=None,
    )
    assert _eval(m, camera_view="SIDE").issues == []


def _tier2_failing(cls=StrokeMetrics, **kw):
    return _clean(
        cls,
        contact_elbow_angle_deg=100.0,
        knee_contribution_deg=1.0,
        preparation_knee_angle_deg=175.0,
        **kw,
    )


@pytest.mark.parametrize("view", [None, "FRONT", "REAR", "UNKNOWN"])
def test_tier2_skipped_unless_side_view(view):
    assert _eval(_tier2_failing(), camera_view=view).issues == []


def test_tier2_runs_for_side_view_capped_minor():
    evaluation = _eval(_tier2_failing(), camera_view="SIDE")
    codes = _codes(evaluation)
    assert set(codes) == {BENT_ELBOW_AT_CONTACT, LIMITED_LEG_DRIVE, STIFF_PREPARATION_KNEE}
    assert set(codes.values()) == {IssueStatus.MINOR.value}
    assert all(i.tier == 2 for i in evaluation.issues)


@pytest.mark.parametrize(("elbow", "fires"), [(180.0, False), (150.0, False), (130.0, False), (129.9, True)])
def test_smash_elbow_hint_only_below_130(elbow, fires):
    codes = _codes(_eval(_clean(contact_elbow_angle_deg=elbow), camera_view="SIDE"))
    assert (BENT_ELBOW_AT_CONTACT in codes) is fires


@pytest.mark.parametrize(("elbow", "fires"), [(140.0, False), (139.9, True)])
def test_clear_elbow_hint_threshold_140(elbow, fires):
    m = _clean(ForehandClearMetrics, contact_elbow_angle_deg=elbow)
    codes = _codes(_eval(m, stroke="FOREHAND_CLEAR", camera_view="SIDE"))
    assert (BENT_ELBOW_AT_CONTACT in codes) is fires


def test_leg_drive_and_prep_knee_boundaries():
    ok = _clean(knee_contribution_deg=5.0, preparation_knee_angle_deg=170.0)
    assert _eval(ok, camera_view="SIDE").issues == []
    bad = _clean(knee_contribution_deg=4.9, preparation_knee_angle_deg=170.1)
    codes = _codes(_eval(bad, camera_view="SIDE"))
    assert {LIMITED_LEG_DRIVE, STIFF_PREPARATION_KNEE} <= set(codes)


def _all_failing():
    return _tier2_failing(
        swing_peak_elbow_omega_offset_frames=5,
        swing_peak_elbow_extension_offset_frames=4,
        swing_peak_trunk_rotation_velocity_offset_frames=9,
        contact_window_min_wrist_y_normalized=0.5,
        backswing_end_wrist_y_normalized=0.6,
    )


def test_provisional_caps_even_when_base_status_is_major():
    cfg = TieredRulesConfig(
        kinetic_chain_order_status="MAJOR",
        low_contact_point_status="MAJOR",
        late_elbow_acceleration_status="MAJOR",
        low_racket_preparation_status="MAJOR",
        tier_hint_status="MAJOR",
    )
    evaluation = _eval(_all_failing(), camera_view="SIDE", config=cfg)
    assert len(evaluation.issues) == 7
    for issue in evaluation.issues:
        assert issue.reference_validated is False
        assert issue.unvalidated_prior is True
        expected = "MODERATE" if issue.tier == 1 else "MINOR"
        assert issue.status == expected
    assert all(i.status != "MAJOR" for i in evaluation.issues)


def test_validated_profile_lifts_tier1_cap_only():
    validated = replace(
        build_provisional_smash_right_side(), status="VALIDATED", provisional=False
    )
    cfg = TieredRulesConfig(
        low_contact_point_status="MAJOR",
        kinetic_chain_order_status="MAJOR",
        tier_hint_status="MAJOR",
    )
    evaluation = _eval(_all_failing(), camera_view="SIDE", config=cfg, profile=validated)
    by_code = {i.code: i for i in evaluation.issues}
    assert by_code[LOW_CONTACT_POINT].status == "MAJOR"
    assert by_code[LOW_CONTACT_POINT].reference_validated is True
    assert by_code[KINETIC_CHAIN_ORDER].status == "MINOR"
    assert by_code[BENT_ELBOW_AT_CONTACT].status == "MINOR"


def test_low_combined_confidence_yields_insufficient_evidence():
    m = _clean(
        phase_confidence=0.1,
        contact_confidence=0.1,
        contact_window_min_wrist_y_normalized=0.5,
    )
    evaluation = _eval(m, quality_confidence=0.1, pose_confidence=0.1)
    issue = next(i for i in evaluation.issues if i.code == LOW_CONTACT_POINT)
    assert issue.combined_confidence < 0.5
    assert issue.status == IssueStatus.INSUFFICIENT_EVIDENCE.value
    assert issue.uncertain is True
    assert issue.confidence <= 0.49


def test_issue_dict_records_tier_fields():
    issue = _eval(_clean(contact_window_min_wrist_y_normalized=0.5)).issues[0].to_dict()
    assert issue["tier"] == 1
    assert issue["reference_validated"] is False
    assert issue["unvalidated_prior"] is True
    assert issue["rule_version"] == TECHNIQUE_RULE_VERSION_TIERED


def test_production_analyzers_use_tiered_rules(tmp_path: Path):
    from app.processing.strokes.clear.analyzer import ForehandClearAnalyzer
    from app.processing.strokes.smash.analyzer import SmashAnalyzer
    from tests.test_stroke_analyzers import _clear_state

    state = _clear_state(tmp_path)
    for analyzer in (ForehandClearAnalyzer(), SmashAnalyzer()):
        metrics = analyzer.extract_metrics(state)
        technique = analyzer.evaluate(state, metrics, camera_view="SIDE")
        assert technique.rule_version == TECHNIQUE_RULE_VERSION_TIERED
        assert not {i.code for i in technique.issues} & RETIRED_CODES
