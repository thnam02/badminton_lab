"""MMPose / RTMPose wrapper returning internal Keypoint schema."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.config import settings
from app.cv.person_selection import PersonCandidate, PersonTracker, resolve_bbox
from app.cv.skeleton import COCO_KEYPOINT_NAMES
from app.schemas.pose import Keypoint


class MMPoseEstimator:
    """Thin adapter around MMPoseInferencer (RTMPose).

    MMPose raw predictions are converted here and must not leak elsewhere.
    Stateful across frames: call ``reset_tracking()`` before each new video.
    """

    def __init__(self) -> None:
        from mmpose.apis import MMPoseInferencer

        init_kwargs: dict[str, Any] = {"device": settings.device}

        if settings.mmpose_config and settings.mmpose_checkpoint:
            init_kwargs["pose2d"] = settings.mmpose_config
            init_kwargs["pose2d_weights"] = settings.mmpose_checkpoint
        else:
            # Alias resolves to RTMPose-m (see mmpose model aliases).
            init_kwargs["pose2d"] = "human"

        self._inferencer = MMPoseInferencer(**init_kwargs)
        self._threshold = settings.pose_confidence_threshold
        self.tracker = PersonTracker()

    def reset_tracking(self) -> None:
        self.tracker.reset()

    def predict(self, frame: np.ndarray) -> dict[str, Keypoint]:
        """Run pose estimation on a BGR frame and return the tracked player.

        Returns named Keypoint values with x/y normalized to [0, 1], or ``{}``
        when the tracked player is not found in this frame.
        """
        chosen = self.tracker.select(self.predict_candidates(frame))
        return dict(chosen.keypoints) if chosen is not None else {}

    def predict_candidates(self, frame: np.ndarray) -> list[PersonCandidate]:
        """All detected people in a BGR frame (normalized coordinates)."""
        height, width = frame.shape[:2]
        if height == 0 or width == 0:
            return []

        result_generator = self._inferencer(
            frame,
            show=False,
            return_vis=False,
            return_datasample=False,
        )
        result = next(result_generator)
        predictions = result.get("predictions") or []
        # predictions is List[List[dict]] — one list of instances per image.
        instances = predictions[0] if predictions else []

        candidates: list[PersonCandidate] = []
        for inst in instances or []:
            candidate = _candidate_from_instance(inst, width=width, height=height)
            if candidate is not None:
                candidates.append(candidate)
        return candidates


def _candidate_from_instance(
    inst: dict[str, Any], *, width: int, height: int
) -> PersonCandidate | None:
    raw_keypoints = inst.get("keypoints")
    scores = inst.get("keypoint_scores")
    if raw_keypoints is None or scores is None:
        return None
    raw_keypoints = np.asarray(raw_keypoints, dtype=np.float32)
    scores = np.asarray(scores, dtype=np.float32)

    named: dict[str, Keypoint] = {}
    for idx, name in enumerate(COCO_KEYPOINT_NAMES):
        if idx >= len(raw_keypoints) or idx >= len(scores):
            break
        x_px, y_px = float(raw_keypoints[idx][0]), float(raw_keypoints[idx][1])
        named[name] = Keypoint(
            x=x_px / width,
            y=y_px / height,
            confidence=float(scores[idx]),
        )

    detector_bbox = None
    raw_bbox = inst.get("bbox")
    if raw_bbox is not None:
        # MMPose wraps the box as ([x1, y1, x2, y2],).
        flat = np.asarray(raw_bbox, dtype=np.float32).reshape(-1)
        if flat.size >= 4:
            detector_bbox = (
                float(flat[0]) / width,
                float(flat[1]) / height,
                float(flat[2]) / width,
                float(flat[3]) / height,
            )
    bbox = resolve_bbox(detector_bbox, named)
    if bbox is None:
        return None
    return PersonCandidate(
        keypoints=named,
        bbox=bbox,
        mean_confidence=float(np.mean(scores)) if scores.size else 0.0,
    )
