"""Tiered technique evaluation for forehand smash and clear.

Thresholds live in ``technique_rules_config``. Reference profiles are only
used to decide whether the reference is validated (severity cap) and to supply
reference confidence; no metric is compared to a seeded distribution.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.processing.reference_profile_selector import MATCH_NONE, ReferenceProfileSelector
from app.processing.reference_profiles import default_reference_profiles
from app.processing.technique import _evaluation_confidence, _profile_reference_confidence
from app.processing.technique_config import reference_profile_from_settings
from app.processing.technique_rules_config import (
    BENT_ELBOW_AT_CONTACT,
    KINETIC_CHAIN_ORDER,
    LATE_ELBOW_ACCELERATION,
    LIMITED_LEG_DRIVE,
    LOW_CONTACT_POINT,
    LOW_RACKET_PREPARATION,
    STIFF_PREPARATION_KNEE,
    TIER_BY_CODE,
    TIER_HINT_CAMERA_VIEW,
    TIER_PRINCIPLE,
    TieredRulesConfig,
    default_tiered_rules_config,
)
from app.schemas.final_analysis import FinalAnalysisState
from app.schemas.phases import SmashPhase
from app.schemas.reference import ReferenceProfile
from app.schemas.technique import (
    TECHNIQUE_RULE_VERSION_TIERED,
    IssueSeverity,
    ReferenceRange,
    TechniqueEvaluation,
    TechniqueIssue,
    status_to_severity,
)
from app.schemas.technique_calibration import (
    IssueStatus,
    SeverityCalibrationConfig,
    build_evaluation_confidence,
    default_severity_calibration,
)

DECISION_MODE_TIERED = "tiered_rules"

STROKE_SMASH = "SMASH"
STROKE_CLEAR = "FOREHAND_CLEAR"

_STATUS_RANK = {
    IssueStatus.MINOR.value: 1,
    IssueStatus.MODERATE.value: 2,
    IssueStatus.MAJOR.value: 3,
}


@dataclass(frozen=True, slots=True)
class _Finding:
    code: str
    phase: SmashPhase
    measured: float
    unit: str
    metric_name: str
    reference_range: ReferenceRange
    base_status: str
    description: str

    @property
    def tier(self) -> int:
        return TIER_BY_CODE[self.code]


def normalize_tiered_stroke(stroke_type: str | None) -> str:
    raw = str(stroke_type or STROKE_SMASH).strip().upper()
    if raw in {"CLEAR", "FOREHAND_CLEAR"}:
        return STROKE_CLEAR
    return STROKE_SMASH


def is_reference_validated(profile: ReferenceProfile | None) -> bool:
    if profile is None:
        return False
    return (
        str(profile.status or "").strip().upper() == "VALIDATED"
        and not bool(profile.provisional)
    )


def cap_status(status: str, cap: str) -> str:
    if _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(cap, 0):
        return cap
    return status


def evaluate_tiered_from_final(
    state: FinalAnalysisState,
    metrics,
    **kwargs,
) -> TechniqueEvaluation:
    if metrics.estimated_contact_frame_index != state.contact.frame_index:
        raise ValueError(
            "Stroke metrics contact frame must match FinalAnalysisState.contact; "
            f"got metrics={metrics.estimated_contact_frame_index}, "
            f"state={state.contact.frame_index}."
        )
    if kwargs.get("quality_confidence") is None:
        kwargs["quality_confidence"] = float(state.video_quality.analysis_confidence)
    return evaluate_tiered(metrics, **kwargs)


def evaluate_tiered(
    metrics,
    *,
    stroke_type: str = STROKE_SMASH,
    handedness: str | None = None,
    camera_view: str | None = None,
    skill_level: str | None = None,
    quality_confidence: float | None = None,
    pose_confidence: float | None = None,
    profile: ReferenceProfile | None = None,
    profiles: Sequence[ReferenceProfile] | None = None,
    config: TieredRulesConfig | None = None,
    calibration: SeverityCalibrationConfig | None = None,
) -> TechniqueEvaluation:
    """Apply Tier 1 (always) and Tier 2 (side view only) rules; no LLM."""
    cfg = config or default_tiered_rules_config()
    calib = calibration or default_severity_calibration()
    stroke = normalize_tiered_stroke(stroke_type)

    selected, match_level = _select_profile(
        stroke,
        profile=profile,
        profiles=profiles,
        handedness=handedness,
        camera_view=camera_view,
        skill_level=skill_level,
    )
    validated = is_reference_validated(selected)
    reference_confidence = (
        _profile_reference_confidence(selected) if selected is not None else 0.2
    )

    q_conf = (
        float(max(0.0, min(1.0, quality_confidence)))
        if quality_confidence is not None
        else 1.0
    )
    pose_conf = (
        float(max(0.0, min(1.0, pose_confidence))) if pose_confidence is not None else 1.0
    )
    phase_conf = float(metrics.phase_confidence)
    measurement_conf = _measurement_confidence(
        metrics, quality_confidence=quality_confidence, pose_confidence=pose_conf
    )
    eval_conf = build_evaluation_confidence(
        measurement_confidence=measurement_conf,
        phase_confidence=phase_conf,
        video_quality_confidence=q_conf,
        reference_confidence=reference_confidence,
        pose_confidence=pose_conf,
        config=calib,
    )

    findings = list(tier1_findings(metrics, cfg))
    if str(camera_view or "").upper() == TIER_HINT_CAMERA_VIEW:
        findings.extend(tier2_findings(metrics, cfg, stroke=stroke))

    profile_id = selected.profile_id if selected is not None else ""
    issues = [
        _issue_from_finding(
            f,
            cfg=cfg,
            calib=calib,
            eval_conf=eval_conf,
            validated=validated,
            profile_id=profile_id,
        )
        for f in findings
    ]

    if stroke == STROKE_SMASH:
        confidence = _evaluation_confidence(metrics, issues, measurement_conf)
    else:
        confidence = float(eval_conf.combined_confidence)

    return TechniqueEvaluation(
        video=metrics.video,
        issues=issues,
        confidence=confidence,
        reference_profile_id=profile_id,
        reference_profile_version=selected.profile_version if selected is not None else "",
        profile_match_level=match_level,
        decision_mode=DECISION_MODE_TIERED,
        rule_version=TECHNIQUE_RULE_VERSION_TIERED,
        severity_calibration_version=calib.version,
        evaluation_confidence=eval_conf,
    )


def tier1_findings(metrics, cfg: TieredRulesConfig) -> list[_Finding]:
    out: list[_Finding] = []

    elbow_off = getattr(metrics, "swing_peak_elbow_omega_offset_frames", None)
    shoulder_off = getattr(metrics, "swing_peak_shoulder_omega_offset_frames", None)
    if elbow_off is not None and shoulder_off is not None:
        elbow_lead = float(shoulder_off - elbow_off)
        if elbow_lead > cfg.chain_elbow_lead_max_frames:
            out.append(
                _Finding(
                    code=KINETIC_CHAIN_ORDER,
                    phase=SmashPhase.ACCELERATION,
                    measured=elbow_lead,
                    unit="frames",
                    metric_name="swing_elbow_lead_over_shoulder_frames",
                    reference_range=ReferenceRange(
                        min=None, max=float(cfg.chain_elbow_lead_max_frames)
                    ),
                    base_status=cfg.kinetic_chain_order_status,
                    description=(
                        f"Elbow angular velocity peaked {elbow_lead:.0f} frames before "
                        "the shoulder peak (expected shoulder first)."
                    ),
                )
            )

    wrist_y = getattr(metrics, "contact_wrist_y_normalized", None)
    nose_y = getattr(metrics, "contact_nose_y_normalized", None)
    if wrist_y is not None and nose_y is not None:
        below = float(wrist_y - nose_y)
        if below > cfg.contact_wrist_below_nose_margin:
            out.append(
                _Finding(
                    code=LOW_CONTACT_POINT,
                    phase=SmashPhase.ESTIMATED_CONTACT,
                    measured=below,
                    unit="normalized_y",
                    metric_name="contact_wrist_minus_nose_y",
                    reference_range=ReferenceRange(
                        min=None, max=float(cfg.contact_wrist_below_nose_margin)
                    ),
                    base_status=cfg.low_contact_point_status,
                    description="Racket-arm wrist was below the nose at estimated contact.",
                )
            )

    if elbow_off is not None and elbow_off > cfg.late_elbow_peak_max_frames:
        out.append(
            _Finding(
                code=LATE_ELBOW_ACCELERATION,
                phase=SmashPhase.ACCELERATION,
                measured=float(elbow_off),
                unit="frames",
                metric_name="swing_peak_elbow_omega_offset_frames",
                reference_range=ReferenceRange(
                    min=None, max=float(cfg.late_elbow_peak_max_frames)
                ),
                base_status=cfg.late_elbow_acceleration_status,
                description=(
                    f"Peak elbow angular velocity came {elbow_off} frames after "
                    "estimated contact."
                ),
            )
        )

    bs_wrist = getattr(metrics, "backswing_end_wrist_y_normalized", None)
    bs_shoulder = getattr(metrics, "backswing_end_shoulder_y_normalized", None)
    if bs_wrist is not None and bs_shoulder is not None:
        below = float(bs_wrist - bs_shoulder)
        if below > cfg.backswing_wrist_below_shoulder_margin:
            out.append(
                _Finding(
                    code=LOW_RACKET_PREPARATION,
                    phase=SmashPhase.BACKSWING,
                    measured=below,
                    unit="normalized_y",
                    metric_name="backswing_end_wrist_minus_shoulder_y",
                    reference_range=ReferenceRange(
                        min=None, max=float(cfg.backswing_wrist_below_shoulder_margin)
                    ),
                    base_status=cfg.low_racket_preparation_status,
                    description="Racket-arm wrist was below the shoulder at the end of the backswing.",
                )
            )
    return out


def tier2_findings(metrics, cfg: TieredRulesConfig, *, stroke: str) -> list[_Finding]:
    out: list[_Finding] = []
    min_elbow = (
        cfg.clear_min_contact_elbow_deg
        if stroke == STROKE_CLEAR
        else cfg.smash_min_contact_elbow_deg
    )
    elbow = getattr(metrics, "contact_elbow_angle_deg", None)
    if elbow is not None and elbow < min_elbow:
        out.append(
            _Finding(
                code=BENT_ELBOW_AT_CONTACT,
                phase=SmashPhase.ESTIMATED_CONTACT,
                measured=float(elbow),
                unit="deg",
                metric_name="contact_elbow_angle_deg",
                reference_range=ReferenceRange(min=float(min_elbow), max=180.0),
                base_status=cfg.tier_hint_status,
                description=f"Elbow angle at estimated contact was below {min_elbow:.0f}°.",
            )
        )

    knee = getattr(metrics, "knee_contribution_deg", None)
    if knee is not None and knee < cfg.min_leg_drive_deg:
        out.append(
            _Finding(
                code=LIMITED_LEG_DRIVE,
                phase=SmashPhase.ACCELERATION,
                measured=float(knee),
                unit="deg",
                metric_name="knee_contribution_deg",
                reference_range=ReferenceRange(min=float(cfg.min_leg_drive_deg), max=None),
                base_status=cfg.tier_hint_status,
                description=(
                    "Knee extension from preparation to contact was below "
                    f"{cfg.min_leg_drive_deg:.0f}°."
                ),
            )
        )

    prep_knee = getattr(metrics, "preparation_knee_angle_deg", None)
    if prep_knee is not None and prep_knee > cfg.max_preparation_knee_deg:
        out.append(
            _Finding(
                code=STIFF_PREPARATION_KNEE,
                phase=SmashPhase.PREPARATION,
                measured=float(prep_knee),
                unit="deg",
                metric_name="preparation_knee_angle_deg",
                reference_range=ReferenceRange(
                    min=None, max=float(cfg.max_preparation_knee_deg)
                ),
                base_status=cfg.tier_hint_status,
                description=(
                    "Preparation knee angle was above "
                    f"{cfg.max_preparation_knee_deg:.0f}° (little knee bend)."
                ),
            )
        )
    return out


def _issue_from_finding(
    finding: _Finding,
    *,
    cfg: TieredRulesConfig,
    calib: SeverityCalibrationConfig,
    eval_conf,
    validated: bool,
    profile_id: str,
) -> TechniqueIssue:
    if finding.tier == TIER_PRINCIPLE:
        cap = cfg.tier1_cap_validated if validated else cfg.tier1_cap_provisional
    else:
        cap = cfg.tier2_cap_validated if validated else cfg.tier2_cap_provisional

    combined = float(eval_conf.combined_confidence)
    if combined < calib.min_combined_confidence:
        status = IssueStatus.INSUFFICIENT_EVIDENCE.value
        reason = "Combined confidence below calibrated minimum"
    elif eval_conf.measurement_confidence < calib.min_measurement_confidence:
        status = IssueStatus.INSUFFICIENT_EVIDENCE.value
        reason = "Measurement confidence too low for a technique judgement"
    else:
        status = cap_status(finding.base_status, cap)
        reason = (
            f"Tier {finding.tier} rule (unvalidated prior); capped at {cap}"
            + ("" if validated else " while reference is provisional")
        )

    uncertain = status == IssueStatus.INSUFFICIENT_EVIDENCE.value
    severity = status_to_severity(IssueStatus(status)) or IssueSeverity.LOW
    confidence = min(combined, 0.49) if uncertain else combined
    description = (
        f"{finding.description} [{reason}]" if uncertain else finding.description
    )
    return TechniqueIssue(
        code=finding.code,
        phase=finding.phase,
        severity=severity,
        confidence=confidence,
        measured_value=finding.measured,
        reference_range=finding.reference_range,
        unit=finding.unit,
        description=description,
        reference_profile_id=profile_id,
        metric_name=finding.metric_name,
        measurement_confidence=eval_conf.measurement_confidence,
        phase_confidence=eval_conf.phase_confidence,
        video_quality_confidence=eval_conf.video_quality_confidence,
        reference_confidence=eval_conf.reference_confidence,
        combined_confidence=combined,
        rule_version=TECHNIQUE_RULE_VERSION_TIERED,
        severity_calibration_version=calib.version,
        decision_mode=DECISION_MODE_TIERED,
        status=status,
        uncertain=uncertain,
        status_reason=reason,
        tier=finding.tier,
        reference_validated=validated,
        unvalidated_prior=True,
    )


def _measurement_confidence(
    metrics,
    *,
    quality_confidence: float | None,
    pose_confidence: float,
) -> float:
    if metrics.estimated_contact_frame_index is None:
        return 0.0
    parts = [float(metrics.phase_confidence), float(pose_confidence)]
    if quality_confidence is not None:
        parts.append(float(max(0.0, min(1.0, quality_confidence))))
    contact_conf = getattr(metrics, "contact_confidence", None)
    if contact_conf is not None:
        parts.append(float(max(0.0, min(1.0, contact_conf))))
    return float(sum(parts) / len(parts))


def _select_profile(
    stroke: str,
    *,
    profile: ReferenceProfile | None,
    profiles: Sequence[ReferenceProfile] | None,
    handedness: str | None,
    camera_view: str | None,
    skill_level: str | None,
) -> tuple[ReferenceProfile | None, str]:
    # Imported lazily: the clear package imports its analyzer, which imports this module.
    from app.processing.strokes.clear.reference_profiles import (
        default_clear_reference_profiles,
    )

    if profile is not None:
        return profile, "explicit"
    if stroke == STROKE_SMASH and profiles is None:
        return (
            reference_profile_from_settings(
                stroke_type=STROKE_SMASH,
                handedness=handedness,
                camera_view=camera_view,
                skill_level=skill_level,
            ),
            "explicit",
        )
    default_catalog: Callable[[], list[ReferenceProfile]] = (
        default_clear_reference_profiles
        if stroke == STROKE_CLEAR
        else default_reference_profiles
    )
    catalog = list(profiles) if profiles is not None else default_catalog()
    selection = ReferenceProfileSelector(catalog).select(
        stroke_type=stroke,
        handedness=handedness,
        camera_view=camera_view,
        skill_level=skill_level,
    )
    if selection.has_valid_profile and selection.profile is not None:
        return selection.profile, selection.match_level
    return None, MATCH_NONE
