"""Person selection / tracking: near player beats a more-confident distant player."""

from __future__ import annotations

from app.cv.mmpose_estimator import _candidate_from_instance
from app.cv.person_selection import (
    WARNING_WRONG_PLAYER_POSSIBLE,
    PersonCandidate,
    PersonTracker,
)
from app.cv.skeleton import COCO_KEYPOINT_NAMES
from app.processing.video_quality import assess_video_quality
from app.schemas.pose import PoseFrame, PoseSequence

W, H = 1000, 1000


def _instance(x1: float, y1: float, x2: float, y2: float, score: float) -> dict:
    """MMPose-style instance dict (pixel coords, bbox wrapped in a tuple)."""
    n = len(COCO_KEYPOINT_NAMES)
    keypoints = [
        [x1 + (x2 - x1) * (0.3 + 0.4 * (i % 2)), y1 + (y2 - y1) * (i + 1) / (n + 1)]
        for i in range(n)
    ]
    return {
        "keypoints": keypoints,
        "keypoint_scores": [score] * n,
        "bbox": ([x1, y1, x2, y2],),
        "bbox_score": 0.9,
    }


def _near(dx: float = 0.0) -> PersonCandidate:
    # Large box near frame centre, filmed from behind → lower keypoint confidence.
    cand = _candidate_from_instance(
        _instance(380 + dx, 300, 620 + dx, 950, score=0.55), width=W, height=H
    )
    assert cand is not None
    return cand


def _far() -> PersonCandidate:
    # Small box near the edge, facing camera → higher keypoint confidence.
    cand = _candidate_from_instance(
        _instance(840, 420, 900, 560, score=0.95), width=W, height=H
    )
    assert cand is not None
    return cand


def test_near_player_chosen_over_more_confident_far_player():
    far, near = _far(), _near()
    assert far.mean_confidence > near.mean_confidence
    tracker = PersonTracker()
    chosen = tracker.select([far, near])
    assert chosen is near


def test_tracker_does_not_switch_while_tracked_player_briefly_missing():
    tracker = PersonTracker()
    assert tracker.select([_far(), _near()]) is not None
    # Near player missed by the detector for 3 frames: return nothing, not the far player.
    for _ in range(3):
        assert tracker.select([_far()]) is None
    # Near player reappears (moved slightly) → same track resumes.
    resumed = tracker.select([_far(), _near(dx=20)])
    assert resumed is not None and resumed.area > _far().area
    assert tracker.reselections == 0


def test_tracker_reselects_after_tracked_player_disappears():
    tracker = PersonTracker()
    tracker.select([_far(), _near()])
    chosen = None
    for _ in range(10):
        chosen = tracker.select([_far()])
    assert chosen is not None and chosen.area == _far().area
    assert tracker.reselections == 1


def test_wrong_player_warning_when_tracked_box_is_small():
    tracker = PersonTracker()
    tracker.select([_far()])  # only the far player visible at start → tracked
    for _ in range(5):
        tracker.select([_far(), _near()])
    assert WARNING_WRONG_PLAYER_POSSIBLE in tracker.warnings()


def test_no_wrong_player_warning_when_near_player_tracked():
    tracker = PersonTracker()
    for _ in range(5):
        tracker.select([_far(), _near()])
    assert tracker.warnings() == []


def test_no_wrong_player_warning_when_tracked_box_grows_during_swing():
    """Arms-up frames enlarge the tracked player's own box; that is not a wrong player."""
    tracker = PersonTracker()
    for _ in range(5):
        tracker.select([_far(), _near()])
    swing = _candidate_from_instance(
        _instance(250, 50, 750, 950, score=0.55), width=W, height=H
    )
    assert swing is not None and swing.area > 2 * _near().area
    tracker.select([_far(), swing])
    assert tracker.warnings() == []


def test_full_frame_detector_box_falls_back_to_keypoint_extent():
    inst = _instance(0, 0, W, H, score=0.8)
    inst["keypoints"] = [[400 + i, 300 + 20 * i] for i in range(len(COCO_KEYPOINT_NAMES))]
    cand = _candidate_from_instance(inst, width=W, height=H)
    assert cand is not None
    assert cand.area < 0.5


def test_extra_warnings_reach_video_quality_report():
    frame = PoseFrame(frame_index=0, timestamp=0.0, keypoints=dict(_near().keypoints))
    seq = PoseSequence(video="v.mp4", frames=[frame])
    base = assess_video_quality(seq, fps=30.0, width=W, height=H)
    flagged = assess_video_quality(
        seq,
        fps=30.0,
        width=W,
        height=H,
        extra_warnings=[WARNING_WRONG_PLAYER_POSSIBLE],
    )
    assert WARNING_WRONG_PLAYER_POSSIBLE in flagged.warnings
    assert flagged.analysis_confidence < base.analysis_confidence
