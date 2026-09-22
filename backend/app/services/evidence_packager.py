"""Assemble an EvidencePackage from already-computed analysis artifacts.

Performs no biomechanics, pose estimation, or other CV calculations.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from app.schemas.contact import ContactEvent
from app.schemas.evidence import (
    CONTACT_TYPE_KINEMATIC,
    EVIDENCE_VERSION,
    STROKE_TYPE_SMASH,
    ContactEvidence,
    EvidencePackage,
)
from app.schemas.final_analysis import FinalAnalysisState
from app.schemas.keyframes import KeyframeSet
from app.schemas.phases import PhaseSequence, SmashPhase
from app.schemas.provenance import (
    AnalysisSnapshot,
    apply_provenance,
    validate_object_provenance,
)
from app.schemas.technique import TechniqueEvaluation, TechniqueIssue
from app.schemas.video_quality import VideoQualityReport

logger = logging.getLogger(__name__)


# Maps technique issue codes → metrics field that supplies measured_value.
# Timing / follow-through may use a secondary field when the primary is absent;
# ``issue_source_metric`` resolves that from the issue unit.
ISSUE_PRIMARY_METRIC: dict[str, str] = {
    "INSUFFICIENT_ELBOW_EXTENSION": "contact_elbow_angle_deg",
    "LOW_KNEE_CONTRIBUTION": "knee_contribution_deg",
    "PREPARATION_KNEE_OUT_OF_RANGE": "preparation_knee_angle_deg",
    "POOR_ARM_ACCELERATION_TIMING": "peak_elbow_omega_offset_frames",
    "LOW_CONTACT_POSTURE": "contact_wrist_y_normalized",
    "WEAK_FOLLOW_THROUGH": "follow_through_speed_ratio",
    # Forehand clear
    "LIMITED_CLEAR_PREPARATION": "preparation_elbow_angle_deg",
    "INSUFFICIENT_ARM_EXTENSION": "contact_elbow_angle_deg",
    "POOR_PROXIMAL_DISTAL_TIMING": "peak_elbow_omega_offset_frames",
    "RESTRICTED_FOLLOW_THROUGH": "follow_through_speed_ratio",
    "SLOW_RECOVERY": "recovery_frame_count",
}


def issue_source_metric(issue: TechniqueIssue) -> str:
    """Return the StrokeMetrics attribute that backs ``issue.measured_value``."""
    if issue.code == "POOR_ARM_ACCELERATION_TIMING":
        if issue.unit == "frames":
            return "peak_elbow_omega_offset_frames"
        return "acceleration_phase_fraction"
    if issue.code == "WEAK_FOLLOW_THROUGH":
        if issue.unit == "speed_ratio":
            return "follow_through_speed_ratio"
        return "follow_through_frame_count"
    return ISSUE_PRIMARY_METRIC.get(issue.code, "")


class EvidencePackager:
    """Coaching-facing evidence assembler (pure data merge)."""

    def package_from_final(
        self,
        state: FinalAnalysisState,
        *,
        metrics: Any,
        technique: TechniqueEvaluation,
        keyframes: KeyframeSet,
        snapshot: AnalysisSnapshot,
        stroke_type: str = STROKE_TYPE_SMASH,
        handedness: str | None = None,
        evidence_version: str = EVIDENCE_VERSION,
    ) -> EvidencePackage:
        """Build evidence exclusively from ``FinalAnalysisState`` + derived artifacts."""
        validate_object_provenance(metrics, snapshot)
        validate_object_provenance(technique, snapshot)
        validate_object_provenance(keyframes, snapshot)
        contact_idx = getattr(metrics, "estimated_contact_frame_index", None)
        if contact_idx != state.contact.frame_index:
            raise ValueError(
                "Stroke metrics contact must match FinalAnalysisState.contact."
            )
        package = self.package(
            video_quality=state.video_quality,
            phases=state.phases,
            metrics=metrics,
            technique=technique,
            keyframes=keyframes,
            stroke_type=stroke_type,
            handedness=handedness,
            evidence_version=evidence_version,
            contact=state.contact,
        )
        apply_provenance(
            package,
            snapshot,
            artifact_schema_version=evidence_version,
        )
        validate_object_provenance(package, snapshot)
        _log_evidence_observability(package)
        return package


    def package(
        self,
        *,
        video_quality: VideoQualityReport,
        phases: PhaseSequence,
        metrics: Any,
        technique: TechniqueEvaluation,
        keyframes: KeyframeSet,
        stroke_type: str = STROKE_TYPE_SMASH,
        handedness: str | None = None,
        evidence_version: str = EVIDENCE_VERSION,
        contact: ContactEvent | ContactEvidence | None = None,
    ) -> EvidencePackage:
        video = (
            metrics.video
            or phases.video
            or technique.video
            or video_quality.video
            or keyframes.video
        )
        contact_evidence = _resolve_contact_evidence(contact, phases)
        analysis_confidence = _analysis_confidence(
            video_quality.analysis_confidence,
            phases.confidence,
            technique.confidence,
            video_quality.usable,
        )
        return EvidencePackage(
            evidence_version=evidence_version,
            video=video,
            stroke_type=stroke_type,
            handedness=handedness,
            analysis_confidence=analysis_confidence,
            video_quality=video_quality.to_dict(),
            phase_boundaries=[seg.to_dict() for seg in phases.segments],
            phase_confidence=float(phases.confidence),
            contact=contact_evidence,
            metrics=metrics.to_dict(),
            technique_issues=[issue.to_dict() for issue in technique.issues],
            technique_confidence=float(technique.confidence),
            keyframes=[kf.to_dict() for kf in keyframes.keyframes],
            keyframes_output_dir=keyframes.output_dir or None,
        )


def package_evidence_from_final(
    state: FinalAnalysisState,
    *,
    metrics: Any,
    technique: TechniqueEvaluation,
    keyframes: KeyframeSet,
    snapshot: AnalysisSnapshot,
    stroke_type: str = STROKE_TYPE_SMASH,
    handedness: str | None = None,
) -> EvidencePackage:
    """Module-level convenience wrapper around ``EvidencePackager.package_from_final``."""
    return EvidencePackager().package_from_final(
        state,
        metrics=metrics,
        technique=technique,
        keyframes=keyframes,
        snapshot=snapshot,
        stroke_type=stroke_type,
        handedness=handedness,
    )


def package_evidence(
    *,
    video_quality: VideoQualityReport,
    phases: PhaseSequence,
    metrics: Any,
    technique: TechniqueEvaluation,
    keyframes: KeyframeSet,
    stroke_type: str = STROKE_TYPE_SMASH,
    handedness: str | None = None,
    contact: ContactEvent | ContactEvidence | None = None,
) -> EvidencePackage:
    """Module-level convenience wrapper around ``EvidencePackager``."""
    return EvidencePackager().package(
        video_quality=video_quality,
        phases=phases,
        metrics=metrics,
        technique=technique,
        keyframes=keyframes,
        stroke_type=stroke_type,
        handedness=handedness,
        contact=contact,
    )


def _resolve_contact_evidence(
    contact: ContactEvent | ContactEvidence | None,
    phases: PhaseSequence,
) -> ContactEvidence:
    if isinstance(contact, ContactEvidence):
        return contact
    if isinstance(contact, ContactEvent):
        return ContactEvidence.from_contact_event(contact)
    return ContactEvidence(
        contact_type=CONTACT_TYPE_KINEMATIC,
        confidence=_contact_confidence(phases),
        frame_index=phases.estimated_contact_frame_index,
        timestamp=phases.estimated_contact_timestamp,
        kinematic_frame_index=phases.estimated_contact_frame_index,
    )


def _contact_confidence(phases: PhaseSequence) -> float:
    for segment in phases.segments:
        if segment.phase is SmashPhase.ESTIMATED_CONTACT:
            return float(max(0.0, min(1.0, segment.confidence)))
    return float(max(0.0, min(1.0, phases.confidence)))


def _analysis_confidence(
    quality_confidence: float,
    phase_confidence: float,
    technique_confidence: float,
    usable: bool,
) -> float:
    if not usable:
        return 0.0
    parts = [
        float(quality_confidence),
        float(phase_confidence),
        float(technique_confidence),
    ]
    return float(max(0.0, min(1.0, sum(parts) / len(parts))))


def _log_evidence_observability(package: EvidencePackage) -> None:
    """One JSON line per evidence package for later confidence calibration."""
    status_counts: Counter[str] = Counter()
    for issue in package.technique_issues:
        status = str(issue.get("status") or "UNKNOWN").upper()
        status_counts[status] += 1
    quality = package.video_quality or {}
    payload = {
        "event": "evidence_package_built",
        "analysis_id": package.analysis_id or "",
        "video": package.video,
        "stroke_type": package.stroke_type,
        "video_quality_analysis_confidence": quality.get("analysis_confidence"),
        "phase_confidence": package.phase_confidence,
        "technique_confidence": package.technique_confidence,
        "analysis_confidence": package.analysis_confidence,
        "contact_type": package.contact.contact_type,
        "technique_issue_status_counts": {
            "MINOR": int(status_counts.get("MINOR", 0)),
            "MODERATE": int(status_counts.get("MODERATE", 0)),
            "MAJOR": int(status_counts.get("MAJOR", 0)),
            "INSUFFICIENT_EVIDENCE": int(
                status_counts.get("INSUFFICIENT_EVIDENCE", 0)
            ),
        },
        "technique_issue_total": len(package.technique_issues),
    }
    logger.info("observability %s", json.dumps(payload, sort_keys=True))


evidence_packager = EvidencePackager()
