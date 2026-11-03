"""Smash stroke analyzer — smash phases/metrics with the tiered rule set."""

from __future__ import annotations

from app.processing.phases import detect_smash_phases
from app.processing.stroke_metrics import compute_stroke_metrics_from_final
from app.processing.tiered_technique import evaluate_tiered_from_final
from app.schemas.angles import AngleSequence
from app.schemas.final_analysis import FinalAnalysisState
from app.schemas.motion import MotionSequence
from app.schemas.phases import PhaseSequence
from app.schemas.pose import PoseSequence
from app.schemas.stroke_metrics import StrokeMetrics
from app.schemas.stroke_types import StrokeType
from app.schemas.technique import TechniqueEvaluation


class SmashAnalyzer:
    """FOREHAND_SMASH strategy."""

    stroke_type = StrokeType.FOREHAND_SMASH

    def detect_phases(
        self,
        pose: PoseSequence,
        angles: AngleSequence,
        motion: MotionSequence,
        *,
        forced_contact_frame_index: int | None = None,
    ) -> PhaseSequence:
        return detect_smash_phases(
            pose,
            angles,
            motion,
            forced_contact_frame_index=forced_contact_frame_index,
        )

    def extract_metrics(self, state: FinalAnalysisState) -> StrokeMetrics:
        return compute_stroke_metrics_from_final(state)

    def evaluate(
        self,
        state: FinalAnalysisState,
        metrics: StrokeMetrics,
        *,
        quality_confidence: float | None = None,
        pose_confidence: float | None = None,
        handedness: str | None = None,
        camera_view: str | None = None,
        skill_level: str | None = None,
    ) -> TechniqueEvaluation:
        return evaluate_tiered_from_final(
            state,
            metrics,
            stroke_type="SMASH",
            handedness=handedness,
            camera_view=camera_view,
            skill_level=skill_level,
            quality_confidence=quality_confidence,
            pose_confidence=pose_confidence,
        )
