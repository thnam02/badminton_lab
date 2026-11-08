"""Labelling clip view, stats config, label format and endpoints."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.config import settings
from app.labelling import clips as clips_module
from app.labelling.batches import Batch, BatchClip, BatchStore
from app.labelling.clips import clip_view, hand_height, load_stats_config
from app.labelling.labels import RATINGS, LabelError, LabelStore, label_status
from app.routes import labelling as routes

FPS = 30.0
CONTACT = 20
N_FRAMES = 40


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _kp(y: float) -> dict:
    return {"x": 0.5, "y": y, "confidence": 0.9}


def seed_analysis(root: Path, analysis_id: str, *, elbow: float | None = 150.0) -> None:
    """Saved artifacts: shoulder y 0.4, hip y 0.6, wrist y 0.33 at the hit (0.35 torso up)."""
    (root / f"{analysis_id}_pose.mp4").write_bytes(b"")
    metrics = {
        "stroke_type": "FOREHAND_CLEAR",
        "contact_knee_angle_deg": 150.0,
        "preparation_knee_angle_deg": 165.0,
        "follow_through_speed_ratio": 0.5,
    }
    if elbow is not None:
        metrics["contact_elbow_angle_deg"] = elbow
    _write(root / f"{analysis_id}_pose_stroke_metrics.json", metrics)
    _write(
        root / f"{analysis_id}_pose_evidence.json",
        {"stroke_type": "FOREHAND_CLEAR", "handedness": "RIGHT", "camera_view": "SIDE"},
    )
    _write(root / f"{analysis_id}_contact.json", {"frame_index": CONTACT, "timestamp": CONTACT / FPS})
    _write(root / f"{analysis_id}_pose_phases.json", {"estimated_contact_frame_index": CONTACT})
    frames = [
        {
            "frame_index": i,
            "timestamp": i / FPS,
            "keypoints": {
                "right_wrist": _kp(0.33 if i == CONTACT else 0.5),
                "right_shoulder": _kp(0.4),
                "right_hip": _kp(0.6),
            },
        }
        for i in range(N_FRAMES)
    ]
    _write(root / f"{analysis_id}_pose_smoothed.json", {"frame_count": N_FRAMES, "frames": frames})


@pytest.fixture
def outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    return tmp_path


def _stat(view: dict, stat_id: str) -> dict:
    return next(s for s in view["stats"] if s["id"] == stat_id)


def test_clip_view_reads_saved_artifacts(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    view = clip_view("a1")
    assert view["stroke_type"] == "FOREHAND_CLEAR"
    assert view["stroke_label"] == "Forehand Clear"
    assert (view["handedness"], view["camera_view"]) == ("RIGHT", "SIDE")
    assert view["system_contact_frame"] == CONTACT
    assert view["fps"] == pytest.approx(FPS)
    assert view["frame_count"] == N_FRAMES
    assert view["video_url"] == "/outputs/a1_pose.mp4"
    elbow = _stat(view, "contact_elbow_angle")
    assert elbow == {
        "id": "contact_elbow_angle",
        "name": "Arm straightness at the hit",
        "description": elbow["description"],
        "when": "At the hit",
        "unit": "deg",
        "value": 150.0,
        "available": True,
    }
    assert _stat(view, "contact_hand_height")["value"] == pytest.approx(0.35)
    assert _stat(view, "hand_speed")["available"] is False
    assert [o["id"] for o in view["rating_options"]] == list(RATINGS)


def test_hand_height_is_in_torso_lengths_above_the_shoulder() -> None:
    frame = {"keypoints": {"right_wrist": _kp(0.33), "right_shoulder": _kp(0.4), "right_hip": _kp(0.6)}}
    assert hand_height(frame, 0.5) == pytest.approx(0.35)
    frame["keypoints"]["right_wrist"] = {"x": 0.5, "y": 0.33, "confidence": 0.2}
    assert hand_height(frame, 0.5) is None
    assert hand_height(None, 0.5) is None


def test_live_analysis_never_imports_labelling() -> None:
    """Coach labels never change analysis results."""
    app_dir = Path("app")
    allowed = {app_dir / "routes" / "labelling.py", app_dir / "main.py"}
    offenders = []
    for path in app_dir.rglob("*.py"):
        if path.is_relative_to(app_dir / "labelling") or path in allowed:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(n == "app.labelling" or n.startswith("app.labelling.") for n in names):
                offenders.append(str(path))
    assert offenders == []


def test_kept_raw_video_is_preferred(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    videos = outputs / "labelling" / "videos"
    videos.mkdir(parents=True)
    (videos / "a1.mov").write_bytes(b"raw")
    view = clip_view("a1")
    assert view["video_url"] == "/outputs/labelling/videos/a1.mov"
    assert view["overlay_video_url"] == "/outputs/a1_pose.mp4"


def test_stat_wording_comes_from_the_config_file(
    outputs: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_analysis(outputs, "a1")
    config = load_stats_config()
    config["stats"][0]["name"] = "Elbow at the hit (edited)"
    edited = tmp_path_factory.mktemp("cfg") / "labelling_stats.json"
    edited.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(clips_module, "STATS_CONFIG_PATH", edited)
    assert clip_view("a1")["stats"][0]["name"] == "Elbow at the hit (edited)"


def test_stats_config_is_well_formed() -> None:
    config = load_stats_config()
    ids = [s["id"] for s in config["stats"]]
    assert len(ids) == len(set(ids))
    for stat in config["stats"]:
        assert {"id", "name", "description", "when", "unit", "source"} <= set(stat)
        assert stat["source"]["kind"] in {"metric", "hand_height_at_contact"}
    assert [o["id"] for o in config["rating_options"]] == list(RATINGS)
    assert [r["value"] for r in config["overall_ratings"]] == [1, 2, 3, 4, 5]


def test_unknown_analysis_is_not_found(outputs: Path) -> None:
    with pytest.raises(FileNotFoundError):
        clip_view("nope")
    with pytest.raises(FileNotFoundError):
        clip_view("../etc")


def _save(store: LabelStore, body: dict) -> dict:
    return store.save(
        "a1",
        body,
        stat_ids={"contact_elbow_angle", "leg_drive"},
        system_contact_frame=CONTACT,
        frame_count=N_FRAMES,
        batch_id="b1",
    )


def test_label_format(tmp_path: Path) -> None:
    store = LabelStore(tmp_path)
    label = _save(
        store,
        {
            "coach": "  Linh  Tran ",
            "corrected_hit_frame": 22,
            "stats": {"contact_elbow_angle": {"rating": "needs_work", "comment": " too bent "}},
            "overall_rating": 3,
            "feedback": "Reach higher.",
        },
    )
    assert label["label_format_version"] == "1.0.0"
    assert label["coach"] == "Linh Tran"
    assert label["batch_id"] == "b1"
    assert label["system_contact_frame"] == CONTACT
    assert label["corrected_hit_frame"] == 22
    assert label["stats"] == {"contact_elbow_angle": {"rating": "needs_work", "comment": "too bent"}}
    assert label["overall_rating"] == 3
    assert label["created_at"] and label["updated_at"]
    assert (tmp_path / "labelling/labels/a1/linh-tran.json").is_file()
    again = _save(store, {"coach": "linh tran", "overall_rating": 4})
    assert again["created_at"] == label["created_at"]
    assert store.get("a1", "LINH TRAN")["overall_rating"] == 4


def test_hit_frame_equal_to_the_systems_is_stored_as_null(tmp_path: Path) -> None:
    assert _save(LabelStore(tmp_path), {"coach": "Linh", "corrected_hit_frame": CONTACT})[
        "corrected_hit_frame"
    ] is None


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"coach": "Linh", "corrected_hit_frame": N_FRAMES}, "outside this clip"),
        ({"coach": "Linh", "stats": {"made_up": {"rating": "good"}}}, "Unknown stat"),
        ({"coach": "Linh", "stats": {"leg_drive": {"rating": "great"}}}, "Unknown rating"),
        ({"coach": "Linh", "overall_rating": 6}, "1 to 5"),
        ({"coach": "  "}, "Add your name"),
    ],
)
def test_invalid_labels_are_refused(tmp_path: Path, body: dict, message: str) -> None:
    with pytest.raises(LabelError, match=message):
        _save(LabelStore(tmp_path), body)


def test_label_status() -> None:
    available = ["contact_elbow_angle", "leg_drive"]
    assert label_status(None, available) == "not_started"
    partial = {"overall_rating": 4, "stats": {"contact_elbow_angle": {"rating": "good"}}}
    assert label_status(partial, available) == "in_progress"
    partial["stats"]["leg_drive"] = {"rating": "looks_wrong"}
    assert label_status(partial, available) == "done"


def test_batch_endpoint_reports_labelled_clips(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    seed_analysis(outputs, "a2", elbow=None)
    BatchStore().save(
        Batch(
            batch_id="set-1",
            name="Set 1",
            clips=[BatchClip("a1", "one.mp4"), BatchClip("a2", "two.mp4"), BatchClip("gone")],
        )
    )
    view = clip_view("a1")
    stats = {s["id"]: {"rating": "good"} for s in view["stats"] if s["available"]}
    routes.put_clip_label(
        "a1", routes.ClipLabelIn(coach="Linh", batch_id="set-1", stats=stats, overall_rating=4)
    )
    routes.put_clip_label("a2", routes.ClipLabelIn(coach="Linh", overall_rating=2))

    batch = routes.get_batch("set-1", coach="linh")
    assert (batch["total"], batch["labelled_count"]) == (3, 1)
    assert [(c["analysis_id"], c["status"]) for c in batch["clips"]] == [
        ("a1", "done"),
        ("a2", "in_progress"),
        ("gone", "not_started"),
    ]
    assert batch["clips"][2]["missing"] is True
    assert routes.get_batch("set-1", coach="Minh")["labelled_count"] == 0
    assert routes.get_batch("set-1", coach=None)["labelled_count"] == 1
    assert routes.get_batches()["batches"][0]["clip_count"] == 3


def test_label_endpoints_round_trip_and_reject_bad_input(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    saved = routes.put_clip_label(
        "a1", routes.ClipLabelIn(coach="Linh", corrected_hit_frame=25, feedback="ok")
    )
    assert saved["status"] == "in_progress"
    got = routes.get_clip_label("a1", coach="Linh")
    assert got["label"]["corrected_hit_frame"] == 25
    assert routes.get_clip_label("a1", coach="Minh")["label"] is None
    with pytest.raises(HTTPException) as exc:
        routes.put_clip_label(
            "a1", routes.ClipLabelIn(coach="Linh", stats={"nope": routes.StatLabelIn(rating="good")})
        )
    assert exc.value.status_code == 422
    for call in (lambda: routes.get_clip("zzz"), lambda: routes.get_batch("missing-batch")):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 404
