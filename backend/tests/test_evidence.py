"""Tests for EvidencePackager — assembly only; issue values match StrokeMetrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.processing.technique import evaluate_technique
from app.processing.reference_profiles import build_provisional_smash_right_side
from app.schemas.evidence import (
    CONTACT_TYPE_ESTIMATED,
    EVIDENCE_VERSION,
    STROKE_TYPE_SMASH,
)
from app.schemas.keyframes import Keyframe, KeyframeSet
from app.schemas.technique import TechniqueIssue
from app.schemas.video_quality import VideoQualityMetrics, VideoQualityReport
from app.services.evidence_packager import (
    ISSUE_PRIMARY_METRIC,
    EvidencePackager,
    issue_source_metric,
    package_evidence,
)
from tests.test_technique import _build_pipeline


def _quality(video: str = "smash.mp4") -> VideoQualityReport:
    return VideoQualityReport(
        video=video,
        usable=True,
        analysis_confidence=0.85,
        metrics=VideoQualityMetrics(
            fps=30.0,
            width=1280,
            height=720,
            full_body_coverage=0.95,
            racket_arm_visibility=0.98,
            mean_pose_confidence=0.9,
            missing_keypoint_fraction=0.05,
            interpolated_keypoint_fraction=0.02,
            player_size_ratio=0.5,
            camera_stability=0.8,
        ),
        warnings=[],
    )


def _keyframes(video: str = "smash.mp4") -> KeyframeSet:
    return KeyframeSet(
        video=video,
        output_dir="/tmp/keyframes",
        keyframes=[
            Keyframe(
                phase="ESTIMATED_CONTACT",
                frame_index=28,
                timestamp=1.4,
                file_path="/tmp/keyframes/ESTIMATED_CONTACT_f000028.jpg",
                confidence=0.9,
            )
        ],
    )


def test_package_contains_versioned_coaching_fields(tmp_path: Path) -> None:
    _, _, _, phases, metrics = _build_pipeline()
    technique = evaluate_technique(metrics, profile=build_provisional_smash_right_side())
    quality = _quality()
    keyframes = _keyframes()

    package = EvidencePackager().package(
        video_quality=quality,
        phases=phases,
        metrics=metrics,
        technique=technique,
        keyframes=keyframes,
        handedness=None,
    )

    assert package.evidence_version == EVIDENCE_VERSION
    assert package.stroke_type == STROKE_TYPE_SMASH
    assert package.handedness is None
    assert package.contact.contact_type == CONTACT_TYPE_ESTIMATED
    assert package.contact.frame_index == phases.estimated_contact_frame_index
    assert package.contact.confidence > 0
    assert package.phase_boundaries == [seg.to_dict() for seg in phases.segments]
    assert "frame_phases" not in package.to_dict()
    assert package.metrics == metrics.to_dict()
    assert package.video_quality == quality.to_dict()
    assert [
        {k: v for k, v in i.items() if k not in ("tentative", "source_metrics")}
        for i in package.technique_issues
    ] == [i.to_dict() for i in technique.issues]
    assert all("tentative" in i and "source_metrics" in i for i in package.technique_issues)
    assert package.keyframes == [kf.to_dict() for kf in keyframes.keyframes]
    assert "chain_score" in package.composite_scores
    assert "power_score" in package.composite_scores
    assert "base_score" in package.composite_scores
    assert "available" in package.composite_scores
    assert package.to_dict()["composite_scores"] == package.composite_scores
    assert "frames" not in package.to_dict()  # no raw pose sequence
    assert "keypoints" not in package.to_dict()

    out = tmp_path / "evidence.json"
    package.save_json(out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert '"evidence_version"' in text
    assert EVIDENCE_VERSION in text
    assert '"composite_scores"' in text


def test_all_issue_measured_values_match_stroke_metrics() -> None:
    _, _, _, phases, metrics = _build_pipeline()
    # Force every known rule to fire so each measured_value is checked.
    metrics.contact_elbow_angle_deg = 120.0
    metrics.knee_contribution_deg = 4.0
    metrics.peak_elbow_omega_offset_frames = 10
    metrics.acceleration_phase_fraction = 0.02
    metrics.contact_wrist_y_normalized = 0.85
    metrics.follow_through_speed_ratio = 0.05
    metrics.follow_through_frame_count = 0

    technique = evaluate_technique(
        metrics,
        profile=build_provisional_smash_right_side(),
    )
    assert technique.issue_count >= 4

    package = package_evidence(
        video_quality=_quality(),
        phases=phases,
        metrics=metrics,
        technique=technique,
        keyframes=_keyframes(),
    )

    packaged_by_code = {i["code"]: i for i in package.technique_issues}
    for issue in technique.issues:
        field_name = issue_source_metric(issue)
        if not field_name:
            continue
        expected = getattr(metrics, field_name)
        assert expected is not None
        assert issue.measured_value == pytest.approx(float(expected))
        assert packaged_by_code[issue.code]["measured_value"] == pytest.approx(
            float(expected)
        )
        # Packaged metrics mirror the same underlying values.
        assert package.metrics[field_name] == pytest.approx(float(expected))
        assert packaged_by_code[issue.code].get("reference_profile_id")


def test_issue_source_metric_covers_known_codes() -> None:
    from app.schemas.clear_metrics import ForehandClearMetrics
    from app.schemas.phases import SmashPhase
    from app.schemas.stroke_metrics import StrokeMetrics
    from app.schemas.technique import IssueSeverity, ReferenceRange

    clear_codes = {
        "LIMITED_CLEAR_PREPARATION",
        "INSUFFICIENT_ARM_EXTENSION",
        "POOR_PROXIMAL_DISTAL_TIMING",
        "RESTRICTED_FOLLOW_THROUGH",
        "SLOW_RECOVERY",
    }

    for code, field_name in ISSUE_PRIMARY_METRIC.items():
        if code == "POOR_ARM_ACCELERATION_TIMING":
            unit = "frames"
        elif code in {"WEAK_FOLLOW_THROUGH", "RESTRICTED_FOLLOW_THROUGH"}:
            unit = "speed_ratio"
        elif code == "SLOW_RECOVERY":
            unit = "frames"
        else:
            unit = "deg"
        issue = TechniqueIssue(
            code=code,
            phase=SmashPhase.ESTIMATED_CONTACT,
            severity=IssueSeverity.LOW,
            confidence=0.5,
            measured_value=1.0,
            reference_range=ReferenceRange(min=0.0, max=1.0),
            unit=unit,
        )
        resolved = issue_source_metric(issue)
        assert resolved == field_name
        schema = ForehandClearMetrics if code in clear_codes else StrokeMetrics
        assert hasattr(schema, resolved)


def test_handedness_passed_through_when_available() -> None:
    _, _, _, phases, metrics = _build_pipeline()
    technique = evaluate_technique(metrics, profile=build_provisional_smash_right_side())
    package = package_evidence(
        video_quality=_quality(),
        phases=phases,
        metrics=metrics,
        technique=technique,
        keyframes=_keyframes(),
        handedness="RIGHT",
    )
    assert package.handedness == "RIGHT"
    assert package.stroke_type == STROKE_TYPE_SMASH


def test_unusable_quality_zeros_analysis_confidence() -> None:
    _, _, _, phases, metrics = _build_pipeline()
    technique = evaluate_technique(metrics, profile=build_provisional_smash_right_side())
    quality = _quality()
    quality.usable = False
    quality.analysis_confidence = 0.4
    package = package_evidence(
        video_quality=quality,
        phases=phases,
        metrics=metrics,
        technique=technique,
        keyframes=_keyframes(),
    )
    assert package.analysis_confidence == pytest.approx(0.0)


def _tiered_package(**overrides):
    from app.processing.tiered_technique import evaluate_tiered

    _, _, _, phases, metrics = _build_pipeline()
    values = dict(
        swing_peak_elbow_omega_offset_frames=4,
        swing_peak_shoulder_omega_offset_frames=8,
        contact_wrist_y_normalized=0.50,
        contact_window_min_wrist_y_normalized=0.50,
        contact_nose_y_normalized=0.40,
        backswing_end_wrist_y_normalized=0.55,
        backswing_end_shoulder_y_normalized=0.45,
        contact_elbow_angle_deg=120.0,
        knee_contribution_deg=2.0,
        preparation_knee_angle_deg=175.0,
        contact_shoulder_angle_deg=110.0,
        peak_trunk_rotation_deg=20.0,
        preparation_elbow_angle_deg=95.0,
        follow_through_speed_ratio=0.4,
    )
    values.update(overrides)
    for key, value in values.items():
        setattr(metrics, key, value)
    technique = evaluate_tiered(
        metrics, camera_view="SIDE", quality_confidence=0.9, pose_confidence=0.9
    )
    package = package_evidence(
        video_quality=_quality(),
        phases=phases,
        metrics=metrics,
        technique=technique,
        keyframes=_keyframes(),
    )
    return metrics, technique, package


def test_tiered_issues_carry_tier_and_tentative_flags() -> None:
    _, technique, package = _tiered_package()
    assert package.evidence_version == "1.8.0"
    packaged = {i["code"]: i for i in package.technique_issues}
    assert set(packaged) == {i.code for i in technique.issues}
    assert len(packaged) == 6
    for issue in packaged.values():
        assert issue["tier"] in (1, 2)
        assert issue["reference_validated"] is False
        assert issue["unvalidated_prior"] is True
        assert issue["tentative"] is True
        assert issue["status"] != "MAJOR"
        assert issue["source_metrics"]


def test_tiered_measured_values_match_source_metrics() -> None:
    metrics, technique, package = _tiered_package()
    packaged = {i["code"]: i for i in package.technique_issues}
    for issue in technique.issues:
        fields = packaged[issue.code]["source_metrics"]
        values = [float(package.metrics[f]) for f in fields]
        expected = values[0] if len(values) == 1 else values[0] - values[1]
        assert issue.measured_value == pytest.approx(expected)
        assert packaged[issue.code]["measured_value"] == pytest.approx(expected)


def test_display_metrics_are_tier3_and_never_issues() -> None:
    _, technique, package = _tiered_package(
        peak_wrist_speed=None,
        acceleration_elbow_extension_lead_over_trunk_frames=3,
        peak_trunk_rotation_velocity_deg_s=400.0,
    )
    display = {d["metric_id"]: d for d in package.display_metrics}
    assert {
        "contact_shoulder_angle_deg",
        "peak_trunk_rotation_deg",
        "preparation_elbow_angle_deg",
        "follow_through_speed_ratio",
        "acceleration_elbow_extension_lead_over_trunk_frames",
        "peak_trunk_rotation_velocity_deg_s",
    } <= set(display)
    assert "peak_wrist_speed" not in display
    assert all(d["tier"] == 3 for d in display.values())
    assert display["contact_shoulder_angle_deg"]["value"] == pytest.approx(110.0)
    assert display["contact_shoulder_angle_deg"]["note"] is None
    for key in ("acceleration_elbow_extension_lead_over_trunk_frames", "peak_trunk_rotation_velocity_deg_s"):
        assert display[key]["note"] == "Low reliability in 2D video."
    assert "KINETIC_CHAIN_ORDER" not in {i["code"] for i in package.technique_issues}
    issue_metrics = {f for i in package.technique_issues for f in i["source_metrics"]}
    assert not issue_metrics & set(display)
    assert package.to_dict()["display_metrics"] == package.display_metrics


def test_evidence_records_implausible_measurements() -> None:
    from app.processing.plausibility import apply_plausibility_gate

    _, _, _, phases, metrics = _build_pipeline()
    metrics.contact_elbow_angle_deg = 7.2
    apply_plausibility_gate(metrics)
    technique = evaluate_technique(metrics, profile=build_provisional_smash_right_side())
    package = package_evidence(
        video_quality=_quality(),
        phases=phases,
        metrics=metrics,
        technique=technique,
        keyframes=_keyframes(),
    )
    payload = package.to_dict()
    assert payload["measurement_warnings"] == ["IMPLAUSIBLE_MEASUREMENT"]
    assert payload["implausible_measurements"][0]["metric"] == "contact_elbow_angle_deg"
    assert payload["metrics"]["contact_elbow_angle_deg"] is None
