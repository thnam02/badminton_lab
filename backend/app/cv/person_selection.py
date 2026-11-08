"""Choose and track the analysed player among multiple detected people.

Pure-Python (no MMPose dependency) so selection can be unit-tested with
synthetic candidates. Coordinates are normalized to [0, 1] image space.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from app.schemas.pose import Keypoint

# Selection score weights — unvalidated prior. Box size dominates because the
# analysed player is normally the person nearest the camera; confidence is only
# a tiebreaker (a distant, front-facing player can out-score a near player
# filmed from behind on keypoint confidence).
SELECTION_WEIGHT_AREA = 0.6  # unvalidated prior
SELECTION_WEIGHT_CENTER = 0.3  # unvalidated prior
SELECTION_WEIGHT_CONFIDENCE = 0.1  # unvalidated prior

# Tracking — unvalidated prior.
TRACK_MIN_IOU = 0.3  # unvalidated prior
TRACK_LOST_GRACE_FRAMES = 5  # unvalidated prior

# WRONG_PLAYER_POSSIBLE when the tracked player's median box is under this
# fraction of the largest box of any *other* person seen in the clip. The
# tracked player's own box is excluded: it grows ~3x during a swing (arms up),
# which would otherwise flag correctly tracked near players.
WRONG_PLAYER_AREA_RATIO = 0.5

WARNING_WRONG_PLAYER_POSSIBLE = "WRONG_PLAYER_POSSIBLE"

# Detector-free fallback boxes cover the whole frame; treat as "no box".
_FULL_FRAME_AREA = 0.95
_KEYPOINT_BOX_MIN_CONFIDENCE = 0.3

BBox = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class PersonCandidate:
    keypoints: dict[str, Keypoint]
    bbox: BBox  # normalized (x1, y1, x2, y2)
    mean_confidence: float

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def keypoint_bbox(keypoints: dict[str, Keypoint]) -> BBox | None:
    pts = [
        (kp.x, kp.y)
        for kp in keypoints.values()
        if kp.confidence >= _KEYPOINT_BOX_MIN_CONFIDENCE
        and math.isfinite(kp.x)
        and math.isfinite(kp.y)
    ]
    if len(pts) < 2:
        return None
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def resolve_bbox(detector_bbox: BBox | None, keypoints: dict[str, Keypoint]) -> BBox | None:
    """Prefer the detector box; fall back to keypoint extent for full-frame boxes."""
    if detector_bbox is not None:
        x1, y1, x2, y2 = detector_bbox
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if 0.0 < area < _FULL_FRAME_AREA:
            return detector_bbox
    return keypoint_bbox(keypoints)


def iou(a: BBox, b: BBox) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def selection_score(candidate: PersonCandidate, candidates: list[PersonCandidate]) -> float:
    max_area = max((c.area for c in candidates), default=0.0)
    area_term = candidate.area / max_area if max_area > 0 else 0.0
    cx, cy = candidate.center
    center_dist = math.hypot(cx - 0.5, cy - 0.5) / math.hypot(0.5, 0.5)
    center_term = 1.0 - min(1.0, center_dist)
    conf_term = max(0.0, min(1.0, candidate.mean_confidence))
    return (
        SELECTION_WEIGHT_AREA * area_term
        + SELECTION_WEIGHT_CENTER * center_term
        + SELECTION_WEIGHT_CONFIDENCE * conf_term
    )


@dataclass(slots=True)
class PersonTracker:
    """Select the analysed player once, then follow that box across frames.

    Switches person only after the tracked box has been unmatched for more than
    ``TRACK_LOST_GRACE_FRAMES`` frames; unmatched frames inside the grace window
    return no person (treated as missing pose, not as someone else's pose).
    """

    _track_box: BBox | None = None
    _missed: int = 0
    max_area_seen: float = 0.0
    max_other_area: float = 0.0
    multi_person_frames: int = 0
    frames_seen: int = 0
    reselections: int = 0
    chosen_areas: list[float] = field(default_factory=list)
    chosen_boxes: list[BBox | None] = field(default_factory=list)

    def reset(self) -> None:
        self._track_box = None
        self._missed = 0
        self.max_area_seen = 0.0
        self.max_other_area = 0.0
        self.multi_person_frames = 0
        self.frames_seen = 0
        self.reselections = 0
        self.chosen_areas = []
        self.chosen_boxes = []

    def select(self, candidates: list[PersonCandidate]) -> PersonCandidate | None:
        self.frames_seen += 1
        if len(candidates) > 1:
            self.multi_person_frames += 1
        for c in candidates:
            self.max_area_seen = max(self.max_area_seen, c.area)

        chosen = self._choose(candidates)
        for c in candidates:
            if c is not chosen:
                self.max_other_area = max(self.max_other_area, c.area)
        if chosen is None:
            self.chosen_boxes.append(None)
            return None
        self._track_box = chosen.bbox
        self._missed = 0
        self.chosen_areas.append(chosen.area)
        self.chosen_boxes.append(chosen.bbox)
        return chosen

    def _choose(self, candidates: list[PersonCandidate]) -> PersonCandidate | None:
        if self._track_box is not None:
            if candidates:
                best = max(candidates, key=lambda c: iou(c.bbox, self._track_box))
                if iou(best.bbox, self._track_box) >= TRACK_MIN_IOU:
                    return best
            self._missed += 1
            if self._missed <= TRACK_LOST_GRACE_FRAMES:
                return None
            self.reselections += 1
        if not candidates:
            return None
        return max(candidates, key=lambda c: selection_score(c, candidates))

    def warnings(self) -> list[str]:
        if self.multi_person_frames == 0 or not self.chosen_areas:
            return []
        typical_chosen = statistics.median(self.chosen_areas)
        if typical_chosen < WRONG_PLAYER_AREA_RATIO * self.max_other_area:
            return [WARNING_WRONG_PLAYER_POSSIBLE]
        return []
