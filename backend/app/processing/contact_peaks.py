"""Kinematic contact peak selection over the right-wrist speed series.

Without shuttle/racket tracking, contact is anchored at a right-wrist speed
peak. A single global argmax is fragile: one wrong-person frame can create a
spike that outranks the real swing. Here every local peak is a candidate, each
is scored for shape (width) and tracking stability around it, and the chosen
peak gets a ``contact_peak_confidence`` in [0, 1].

The wrist-speed series comes from ``MotionSequence`` (already derived from the
smoothed pose); tracking stability is read from the raw pose.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.signal import find_peaks

from app.schemas.motion import MotionSequence
from app.schemas.pose import PoseFrame, PoseSequence

# Minimum peak prominence as a fraction of the clip's highest wrist speed.
MIN_PEAK_PROMINENCE_FRACTION = 0.2  # unvalidated prior
# Half-width (frames) of the window around a peak used for tracking checks.
CONTACT_PEAK_WINDOW_FRAMES = 3  # unvalidated prior
# Relative frame-to-frame keypoint-box area change treated as a box jump.
CONTACT_BOX_JUMP_RATIO = 0.5  # unvalidated prior

AMBIGUOUS_PEAK_RATIO = 0.8
SPIKE_MAX_WIDTH_FRAMES = 3
# Peaks at least this far apart count as distinct swings.
SWING_MIN_SEPARATION_SECONDS = 1.0
# A peak is an overhead swing only if the racket-arm wrist is above the
# shoulder (smaller image y; y grows downward) within ±this many frames.
SWING_OVERHEAD_WINDOW_FRAMES = 3

WARNING_CONTACT_AMBIGUOUS_PEAKS = "CONTACT_AMBIGUOUS_PEAKS"
WARNING_CONTACT_SPIKE_PEAK = "CONTACT_SPIKE_PEAK"
WARNING_CONTACT_UNSTABLE_TRACKING = "CONTACT_UNSTABLE_TRACKING"
WARNING_MULTIPLE_SWINGS_DETECTED = "MULTIPLE_SWINGS_DETECTED"
CONTACT_PEAK_WARNINGS = (
    WARNING_CONTACT_AMBIGUOUS_PEAKS,
    WARNING_CONTACT_SPIKE_PEAK,
    WARNING_CONTACT_UNSTABLE_TRACKING,
    WARNING_MULTIPLE_SWINGS_DETECTED,
)

# contact_peak_confidence = weighted mean of separation / width / tracking.
CONFIDENCE_WEIGHT_SEPARATION = 0.4  # unvalidated prior
CONFIDENCE_WEIGHT_WIDTH = 0.3  # unvalidated prior
CONFIDENCE_WEIGHT_TRACKING = 0.3  # unvalidated prior
_FULL_WIDTH_FRAMES = 5  # unvalidated prior: width at which the width score saturates
_WRIST_CONF_FLOOR = 0.3  # unvalidated prior: wrist score is 0 at or below this
_WRIST_CONF_FULL = 0.7  # unvalidated prior: wrist score is 1 at or above this


@dataclass(slots=True)
class PeakCandidate:
    frame_index: int
    timestamp: float
    speed: float
    prominence: float
    width_frames: int
    box_area_change: float | None
    mean_wrist_confidence: float
    wrist_above_shoulder: bool = False

    @property
    def spike(self) -> bool:
        return self.width_frames < SPIKE_MAX_WIDTH_FRAMES

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "speed": self.speed,
            "prominence": self.prominence,
            "width_frames": self.width_frames,
            "box_area_change": self.box_area_change,
            "mean_wrist_confidence": self.mean_wrist_confidence,
            "wrist_above_shoulder": self.wrist_above_shoulder,
        }


@dataclass(slots=True)
class SwingCandidate:
    frame_index: int
    timestamp: float
    speed: float
    confidence: float
    chosen: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "speed": self.speed,
            "confidence": self.confidence,
            "chosen": self.chosen,
        }


@dataclass(slots=True)
class ContactPeakAnalysis:
    chosen: PeakCandidate | None
    candidates: list[PeakCandidate] = field(default_factory=list)
    competitor_ratio: float | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    # Distinct swings in time order; only the chosen one is analysed.
    swings: list[SwingCandidate] = field(default_factory=list)


def analyze_contact_peaks(
    motion: MotionSequence,
    raw_pose: PoseSequence,
    *,
    confidence_threshold: float = 0.5,
    joint: str = "right_wrist",
) -> ContactPeakAnalysis:
    """Find wrist-speed peaks and choose the contact peak.

    The chosen peak is the highest one that is neither a spike nor next to a
    box jump (signs of a person-tracking glitch); if every peak is flagged,
    the highest overall. Low wrist confidence lowers confidence and warns but
    does not disqualify a peak: the racket arm is often occluded at contact.
    """
    frames = list(motion.frames)
    if not frames:
        return ContactPeakAnalysis(chosen=None)
    speeds = _filled_series([f.right_wrist_speed for f in frames])
    if speeds is None:
        return ContactPeakAnalysis(chosen=None)

    top = float(np.max(speeds))
    if top <= 0.0:
        return ContactPeakAnalysis(chosen=None)
    indices, props = find_peaks(
        speeds, prominence=MIN_PEAK_PROMINENCE_FRACTION * top
    )
    prominences = list(props.get("prominences", []))
    if len(indices) == 0:
        # Monotonic or edge-only maximum: fall back to the global argmax.
        indices = np.array([int(np.argmax(speeds))])
        prominences = [top - float(np.min(speeds))]

    raw_by = {f.frame_index: f for f in raw_pose.frames}
    candidates = [
        _candidate(
            frames,
            speeds,
            int(i),
            float(prom),
            raw_by,
            confidence_threshold=confidence_threshold,
            joint=joint,
        )
        for i, prom in zip(indices, prominences)
    ]
    candidates.sort(key=lambda c: c.speed, reverse=True)

    clean = [c for c in candidates if not c.spike and not _box_jump(c)]
    chosen = clean[0] if clean else candidates[0]

    ratio = _competitor_ratio(chosen, candidates)

    warnings: list[str] = []
    if ratio is not None and ratio >= AMBIGUOUS_PEAK_RATIO:
        warnings.append(WARNING_CONTACT_AMBIGUOUS_PEAKS)
    if chosen.spike:
        warnings.append(WARNING_CONTACT_SPIKE_PEAK)
    if _box_jump(chosen) or chosen.mean_wrist_confidence < confidence_threshold:
        warnings.append(WARNING_CONTACT_UNSTABLE_TRACKING)
    swings = _identify_swings(candidates, chosen)
    if len(swings) > 1:
        warnings.append(WARNING_MULTIPLE_SWINGS_DETECTED)

    return ContactPeakAnalysis(
        chosen=chosen,
        candidates=candidates,
        competitor_ratio=ratio,
        confidence=peak_confidence(chosen, ratio),
        warnings=warnings,
        swings=swings,
    )


def _identify_swings(
    candidates: list[PeakCandidate], chosen: PeakCandidate
) -> list[SwingCandidate]:
    """Greedy by speed (chosen first): keep peaks at least
    ``SWING_MIN_SEPARATION_SECONDS`` from every kept peak. Spikes and box-jump
    peaks are tracking glitches, and peaks without the wrist above the
    shoulder are not overhead swings; both are skipped. The chosen peak is
    always listed because it is the swing being analysed."""
    pool = [chosen] + [
        c
        for c in candidates
        if c is not chosen
        and not c.spike
        and not _box_jump(c)
        and c.wrist_above_shoulder
    ]
    kept: list[PeakCandidate] = []
    for c in pool:
        if all(abs(c.timestamp - k.timestamp) >= SWING_MIN_SEPARATION_SECONDS for k in kept):
            kept.append(c)
    swings = [
        SwingCandidate(
            frame_index=c.frame_index,
            timestamp=c.timestamp,
            speed=c.speed,
            confidence=peak_confidence(c, _competitor_ratio(c, candidates)),
            chosen=c is chosen,
        )
        for c in kept
    ]
    return sorted(swings, key=lambda s: s.frame_index)


def _competitor_ratio(
    peak: PeakCandidate, candidates: list[PeakCandidate]
) -> float | None:
    """Strongest competing peak within the same swing (closer than
    ``SWING_MIN_SEPARATION_SECONDS``) relative to ``peak``; peaks further
    away belong to other swings and do not compete."""
    rivals = [
        c.speed
        for c in candidates
        if c is not peak
        and abs(c.timestamp - peak.timestamp) < SWING_MIN_SEPARATION_SECONDS
    ]
    if not rivals or peak.speed <= 0:
        return None
    return max(rivals) / peak.speed


def peak_confidence(candidate: PeakCandidate, competitor_ratio: float | None) -> float:
    """Unvalidated prior combining separation, width and tracking scores."""
    if competitor_ratio is None:
        separation = 1.0
    else:
        separation = _clamp((1.0 - competitor_ratio) / 0.5)
    width = _clamp((candidate.width_frames - 1) / (_FULL_WIDTH_FRAMES - 1))
    box = 1.0 if candidate.box_area_change is None else _clamp(1.0 - candidate.box_area_change)
    wrist = _clamp(
        (candidate.mean_wrist_confidence - _WRIST_CONF_FLOOR)
        / (_WRIST_CONF_FULL - _WRIST_CONF_FLOOR)
    )
    tracking = min(box, wrist)
    return _clamp(
        CONFIDENCE_WEIGHT_SEPARATION * separation
        + CONFIDENCE_WEIGHT_WIDTH * width
        + CONFIDENCE_WEIGHT_TRACKING * tracking
    )


def _box_jump(candidate: PeakCandidate) -> bool:
    return (
        candidate.box_area_change is not None
        and candidate.box_area_change > CONTACT_BOX_JUMP_RATIO
    )


def _candidate(
    frames,
    speeds: np.ndarray,
    i: int,
    prominence: float,
    raw_by: dict[int, PoseFrame],
    *,
    confidence_threshold: float,
    joint: str,
) -> PeakCandidate:
    height = float(speeds[i])
    half = height / 2.0
    lo = i
    while lo - 1 >= 0 and speeds[lo - 1] >= half:
        lo -= 1
    hi = i
    while hi + 1 < len(speeds) and speeds[hi + 1] >= half:
        hi += 1

    center = frames[i].frame_index
    window = range(
        center - CONTACT_PEAK_WINDOW_FRAMES, center + CONTACT_PEAK_WINDOW_FRAMES + 1
    )
    wrist_confs: list[float] = []
    areas: list[float | None] = []
    for idx in window:
        raw = raw_by.get(idx)
        kp = raw.keypoints.get(joint) if raw is not None else None
        wrist_confs.append(
            float(kp.confidence) if kp is not None and math.isfinite(kp.confidence) else 0.0
        )
        areas.append(_keypoint_box_area(raw, confidence_threshold) if raw is not None else None)

    changes = [
        abs(b - a) / max(a, b)
        for a, b in zip(areas, areas[1:])
        if a is not None and b is not None and max(a, b) > 0
    ]
    shoulder = joint.replace("wrist", "shoulder")
    overhead = any(
        _visible_pair_above(raw_by.get(idx), joint, shoulder, confidence_threshold)
        for idx in range(
            center - SWING_OVERHEAD_WINDOW_FRAMES,
            center + SWING_OVERHEAD_WINDOW_FRAMES + 1,
        )
    )
    return PeakCandidate(
        frame_index=int(center),
        timestamp=float(frames[i].timestamp),
        speed=height,
        prominence=float(prominence),
        width_frames=int(hi - lo + 1),
        box_area_change=float(max(changes)) if changes else None,
        mean_wrist_confidence=float(sum(wrist_confs) / len(wrist_confs)),
        wrist_above_shoulder=overhead,
    )


def _visible_pair_above(
    frame: PoseFrame | None, upper: str, lower: str, threshold: float
) -> bool:
    if frame is None:
        return False
    a = frame.keypoints.get(upper)
    b = frame.keypoints.get(lower)
    if a is None or b is None or a.confidence < threshold or b.confidence < threshold:
        return False
    return a.y < b.y


def _keypoint_box_area(frame: PoseFrame, threshold: float) -> float | None:
    pts = [
        (kp.x, kp.y)
        for kp in frame.keypoints.values()
        if kp.confidence >= threshold and math.isfinite(kp.x) and math.isfinite(kp.y)
    ]
    if len(pts) < 4:
        return None
    xs, ys = zip(*pts)
    return float((max(xs) - min(xs)) * (max(ys) - min(ys)))


def _filled_series(values: list[float | None]) -> np.ndarray | None:
    arr = np.array(
        [v if v is not None and math.isfinite(v) else np.nan for v in values],
        dtype=np.float64,
    )
    valid = ~np.isnan(arr)
    if not valid.any():
        return None
    idx = np.arange(len(arr))
    return np.interp(idx, idx[valid], arr[valid])


def _clamp(value: float) -> float:
    return float(max(0.0, min(1.0, value)))
