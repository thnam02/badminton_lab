"""Versioned coaching evidence package (assembled from deterministic analysis)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.schemas.contact import (
    CONTACT_TYPE_ESTIMATED,
    CONTACT_TYPE_KINEMATIC,
    CONTACT_TYPE_TRACKED,
    ContactEvent,
)

# Bump when the coaching-facing evidence shape changes.
# 1.2.0: camera_view field; handedness is user-declared (RIGHT/LEFT/UNKNOWN).
# 1.3.0: swing_count / swing_candidates; contact carries
#        contact_peak_confidence and warnings.
# 1.4.0: contact.shuttle_verified.
EVIDENCE_VERSION = "1.4.0"

EVIDENCE_DEFAULT_NOTES = (
    "Assembled from already-computed analysis artifacts; "
    "no biomechanics or CV recalculation."
)

STROKE_TYPE_SMASH = "SMASH"


@dataclass(slots=True)
class ContactEvidence:
    """Contact event summary for the coaching layer."""

    contact_type: str = CONTACT_TYPE_KINEMATIC
    confidence: float = 0.0
    frame_index: int | None = None
    timestamp: float | None = None
    kinematic_frame_index: int | None = None
    notes: str = (
        "KINEMATIC_ESTIMATE is anchored at peak right-wrist speed when "
        "shuttle/racket evidence is unavailable or unreliable."
    )
    evidence: list[dict[str, Any]] = field(default_factory=list)
    contact_peak_confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    shuttle_verified: bool = False

    @classmethod
    def from_contact_event(cls, event: ContactEvent) -> ContactEvidence:
        return cls(
            contact_type=event.contact_type,
            confidence=float(event.confidence),
            frame_index=event.frame_index,
            timestamp=event.timestamp,
            kinematic_frame_index=event.kinematic_frame_index,
            notes=event.notes,
            evidence=[e.to_dict() for e in event.evidence],
            contact_peak_confidence=event.contact_peak_confidence,
            warnings=list(event.warnings),
            shuttle_verified=event.shuttle_verified,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "contact_type": self.contact_type,
            "confidence": self.confidence,
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "kinematic_frame_index": self.kinematic_frame_index,
            "notes": self.notes,
            "contact_peak_confidence": self.contact_peak_confidence,
            "warnings": list(self.warnings),
            "shuttle_verified": self.shuttle_verified,
        }
        if self.evidence:
            payload["evidence"] = list(self.evidence)
        return payload


@dataclass(slots=True)
class EvidencePackage:
    """Deterministic analysis snapshot consumed by a later coaching layer.

    Does not embed full raw pose sequences. When ``handedness == "LEFT"`` every
    ``right_*`` metric refers to the racket arm (labels swapped after pose
    estimation); ``notes`` says so explicitly.
    """

    evidence_version: str
    video: str
    stroke_type: str
    handedness: str | None
    analysis_confidence: float
    video_quality: dict[str, Any]
    phase_boundaries: list[dict[str, Any]]
    phase_confidence: float
    contact: ContactEvidence
    metrics: dict[str, Any]
    technique_issues: list[dict[str, Any]]
    technique_confidence: float
    keyframes: list[dict[str, Any]]
    composite_scores: dict[str, Any] = field(default_factory=dict)
    camera_view: str | None = None
    # Distinct swings found in the clip; only the chosen one is analysed.
    swing_count: int | None = None
    swing_candidates: list[dict[str, Any]] = field(default_factory=list)
    keyframes_output_dir: str | None = None
    notes: str = EVIDENCE_DEFAULT_NOTES
    extra: dict[str, Any] = field(default_factory=dict)
    analysis_id: str = ""
    snapshot_id: str = ""
    fingerprint: str = ""
    snapshot_schema_version: str = ""
    artifact_schema_version: str = ""
    artifact_role: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "evidence_version": self.evidence_version,
            "video": self.video,
            "stroke_type": self.stroke_type,
            "handedness": self.handedness,
            "camera_view": self.camera_view,
            "analysis_confidence": self.analysis_confidence,
            "video_quality": self.video_quality,
            "phase_boundaries": self.phase_boundaries,
            "phase_confidence": self.phase_confidence,
            "contact": self.contact.to_dict(),
            "metrics": self.metrics,
            "technique_issues": self.technique_issues,
            "technique_confidence": self.technique_confidence,
            "keyframes": self.keyframes,
            "composite_scores": self.composite_scores,
            "swing_count": self.swing_count,
            "swing_candidates": list(self.swing_candidates),
            "keyframes_output_dir": self.keyframes_output_dir,
            "notes": self.notes,
        }
        if self.extra:
            payload["extra"] = self.extra
        from app.schemas.provenance import provenance_fields_from_object

        payload.update(provenance_fields_from_object(self))
        return payload

    def save_json(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path
