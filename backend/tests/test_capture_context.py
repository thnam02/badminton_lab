"""User-declared handedness / camera view and the LEFT label-swap convention."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.processing.capture_context import (
    WARNING_CAMERA_VIEW_FRONT,
    WARNING_CAMERA_VIEW_REAR,
    WARNING_HANDEDNESS_UNKNOWN,
    InvalidCaptureContextError,
    normalize_camera_view,
    normalize_handedness,
    swap_left_right,
)
from app.processing.strokes import get_stroke_analyzer
from app.schemas.keyframes import KeyframeSet
from app.schemas.pose import Keypoint, PoseFrame, PoseSequence
from app.services.analysis_aggregator import get_analysis_result
from app.services.evidence_packager import EvidencePackager
from app.services.pose_service import pose_service

FIXTURE = Path(__file__).parent / "fixtures" / "raw_pose_right_handed_clear.json"
_PROVENANCE_KEYS = {
    "video",
    "analysis_id",
    "snapshot_id",
    "fingerprint",
    "snapshot_schema_version",
    "artifact_schema_version",
    "artifact_role",
}


def _load_fixture() -> tuple[PoseSequence, dict]:
    data = json.loads(FIXTURE.read_text())
    frames = [
        PoseFrame(
            frame_index=f["frame_index"],
            timestamp=f["timestamp"],
            keypoints={
                n: Keypoint(x=v[0], y=v[1], confidence=v[2])
                for n, v in f["keypoints"].items()
            },
        )
        for f in data["frames"]
    ]
    return PoseSequence(video="clip_pose.mp4", frames=frames), data


def _run(raw: PoseSequence, meta: dict, tmp_path: Path, *, stroke: str, handedness: str,
         camera_view: str = "SIDE", name: str = "clip"):
    kin = pose_service.kinematics_from_raw_pose(
        raw,
        input_path=tmp_path / f"{name}.mp4",
        output_path=tmp_path / f"{name}_pose.mp4",
        stroke_type=stroke,
        handedness=handedness,
        camera_view=camera_view,
        video_fps=meta["fps"],
        video_width=meta["width"],
        video_height=meta["height"],
    )
    state = pose_service.build_final_state(kin)
    analyzer = get_stroke_analyzer(stroke)
    metrics = analyzer.extract_metrics(state)
    technique = analyzer.evaluate(
        state,
        metrics,
        quality_confidence=float(state.video_quality.analysis_confidence),
        handedness=handedness if handedness != "UNKNOWN" else None,
        camera_view=camera_view if camera_view != "UNKNOWN" else None,
    )
    return kin, state, metrics, technique


def _assert_same(a, b, path: str = "") -> None:
    if isinstance(a, dict):
        assert set(a) == set(b), path
        for k in a:
            if k in _PROVENANCE_KEYS:
                continue
            _assert_same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _assert_same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        if math.isnan(a):
            assert math.isnan(b), path
        else:
            assert a == pytest.approx(b, rel=1e-9, abs=1e-9), path
    else:
        assert a == b, path


@pytest.mark.parametrize("stroke", ["FOREHAND_CLEAR", "FOREHAND_SMASH"])
def test_left_handed_swap_reproduces_right_handed_metrics(tmp_path: Path, stroke: str):
    raw, meta = _load_fixture()
    # Simulate a left-handed player: the racket arm now carries left_* labels.
    left_handed_raw = swap_left_right(raw)

    kin_r, state_r, metrics_r, tech_r = _run(
        raw, meta, tmp_path, stroke=stroke, handedness="RIGHT", name="r"
    )
    kin_l, state_l, metrics_l, tech_l = _run(
        left_handed_raw, meta, tmp_path, stroke=stroke, handedness="LEFT", name="l"
    )

    assert metrics_r.estimated_contact_frame_index is not None
    assert metrics_l.estimated_contact_frame_index == metrics_r.estimated_contact_frame_index
    _assert_same(metrics_r.to_dict(), metrics_l.to_dict())
    assert state_l.video_quality.warnings == state_r.video_quality.warnings
    assert state_l.video_quality.analysis_confidence == pytest.approx(
        state_r.video_quality.analysis_confidence
    )
    assert [i.code for i in tech_l.issues] == [i.code for i in tech_r.issues]
    # After the swap, right_* in the pipeline is the declared racket arm.
    first = next(f for f in kin_l.raw_sequence.frames if f.keypoints)
    orig = next(f for f in left_handed_raw.frames if f.frame_index == first.frame_index)
    assert first.keypoints["right_wrist"] == orig.keypoints["left_wrist"]


def test_unknown_handedness_warns_and_lowers_quality(tmp_path: Path):
    raw, meta = _load_fixture()
    _, state_r, _, _ = _run(raw, meta, tmp_path, stroke="FOREHAND_CLEAR", handedness="RIGHT")
    _, state_u, _, _ = _run(raw, meta, tmp_path, stroke="FOREHAND_CLEAR", handedness="UNKNOWN")
    assert WARNING_HANDEDNESS_UNKNOWN in state_u.video_quality.warnings
    assert WARNING_HANDEDNESS_UNKNOWN not in state_r.video_quality.warnings
    assert (
        state_u.video_quality.analysis_confidence
        < state_r.video_quality.analysis_confidence
    )


@pytest.mark.parametrize(
    ("view", "warning"),
    [("FRONT", WARNING_CAMERA_VIEW_FRONT), ("REAR", WARNING_CAMERA_VIEW_REAR)],
)
def test_front_or_rear_view_warns_and_lowers_quality(tmp_path: Path, view: str, warning: str):
    raw, meta = _load_fixture()
    _, side, _, _ = _run(raw, meta, tmp_path, stroke="FOREHAND_CLEAR", handedness="RIGHT")
    _, other, _, _ = _run(
        raw, meta, tmp_path, stroke="FOREHAND_CLEAR", handedness="RIGHT", camera_view=view
    )
    assert warning in other.video_quality.warnings
    assert other.video_quality.analysis_confidence < side.video_quality.analysis_confidence


def test_unknown_camera_view_has_no_view_warning(tmp_path: Path):
    raw, meta = _load_fixture()
    _, state, _, _ = _run(
        raw, meta, tmp_path, stroke="FOREHAND_CLEAR", handedness="RIGHT", camera_view="UNKNOWN"
    )
    assert not any(w.startswith("CAMERA_VIEW_") for w in state.video_quality.warnings)


def test_normalizers_reject_unknown_values():
    assert normalize_handedness(None) == "UNKNOWN"
    assert normalize_handedness("left") == "LEFT"
    assert normalize_camera_view("rear") == "REAR"
    with pytest.raises(InvalidCaptureContextError):
        normalize_handedness("AMBIDEXTROUS")
    with pytest.raises(InvalidCaptureContextError):
        normalize_camera_view("OVERHEAD")


def test_evidence_carries_camera_view_and_racket_arm_note(tmp_path: Path):
    raw, meta = _load_fixture()
    _, state, metrics, technique = _run(
        swap_left_right(raw), meta, tmp_path, stroke="FOREHAND_CLEAR", handedness="LEFT"
    )
    package = EvidencePackager().package(
        video_quality=state.video_quality,
        phases=state.phases,
        metrics=metrics,
        technique=technique,
        keyframes=KeyframeSet(video="clip_pose.mp4", output_dir=""),
        stroke_type="FOREHAND_CLEAR",
        handedness="LEFT",
        camera_view="SIDE",
        contact=state.contact,
    )
    payload = package.to_dict()
    assert payload["handedness"] == "LEFT"
    assert payload["camera_view"] == "SIDE"
    assert "racket arm" in payload["notes"]

    right = EvidencePackager().package(
        video_quality=state.video_quality,
        phases=state.phases,
        metrics=metrics,
        technique=technique,
        keyframes=KeyframeSet(video="clip_pose.mp4", output_dir=""),
        handedness="RIGHT",
    )
    assert "racket arm" not in right.to_dict()["notes"]


def test_aggregator_reads_camera_view_from_evidence(tmp_path: Path):
    (tmp_path / "cv001_pose_evidence.json").write_text(
        json.dumps(
            {
                "evidence_version": "1.2.0",
                "stroke_type": "FOREHAND_CLEAR",
                "handedness": "LEFT",
                "camera_view": "REAR",
            }
        )
    )
    result = get_analysis_result("cv001", output_dir=tmp_path)
    assert result["camera_view"] == "REAR"
    assert result["handedness"] == "Left-handed"
