"""Labelling clip view, question config, label format and endpoints."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.config import settings
from app.labelling import clips as clips_module
from app.labelling.batches import Batch, BatchClip, BatchStore
from app.labelling.clips import (
    KEYPOINT_NAMES,
    clip_pose,
    clip_view,
    hand_height,
    load_stats_config,
)
from app.labelling.labels import LabelError, LabelStore, label_status
from app.routes import labelling as routes

FPS = 30.0
CONTACT = 20
N_FRAMES = 40
PHASES = [
    {"phase": "PREPARATION", "start_frame_index": 0, "end_frame_index": 8},
    {"phase": "BACKSWING", "start_frame_index": 9, "end_frame_index": 15},
    {"phase": "ACCELERATION", "start_frame_index": 16, "end_frame_index": 19},
    {"phase": "ESTIMATED_CONTACT", "start_frame_index": 20, "end_frame_index": 20},
    {"phase": "FOLLOW_THROUGH", "start_frame_index": 21, "end_frame_index": 30},
]
CLEAR_IDS = ["sideon", "freearm", "prep", "knee", "height", "elbow", "infront", "rotate", "follow", "legs"]


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _kp(y: float, x: float = 0.5) -> dict:
    return {"x": x, "y": y, "confidence": 0.9}


def seed_analysis(
    root: Path,
    analysis_id: str,
    *,
    elbow: float | None = 150.0,
    stroke: str = "FOREHAND_CLEAR",
) -> None:
    """Saved artifacts: shoulder y 0.4, hip y 0.6, wrist y 0.33 at the hit (0.35 torso up)."""
    (root / f"{analysis_id}_pose.mp4").write_bytes(b"")
    metrics = {
        "stroke_type": stroke,
        "contact_knee_angle_deg": 150.0,
        "preparation_knee_angle_deg": 165.0,
        "knee_contribution_deg": 4.0,
        "follow_through_speed_ratio": 0.5,
        "backswing_end_wrist_y_normalized": 0.3,
        "backswing_end_shoulder_y_normalized": 0.4,
    }
    if elbow is not None:
        metrics["contact_elbow_angle_deg"] = elbow
    _write(root / f"{analysis_id}_pose_stroke_metrics.json", metrics)
    _write(
        root / f"{analysis_id}_pose_evidence.json",
        {"stroke_type": stroke, "handedness": "RIGHT", "camera_view": "SIDE"},
    )
    _write(root / f"{analysis_id}_contact.json", {"frame_index": CONTACT, "timestamp": CONTACT / FPS})
    _write(
        root / f"{analysis_id}_pose_phases.json",
        {"estimated_contact_frame_index": CONTACT, "segments": PHASES},
    )
    frames = [
        {
            "frame_index": i,
            "timestamp": i / FPS,
            "keypoints": {
                "right_wrist": _kp(0.33 if i == CONTACT else 0.5, x=0.6 + i / 1000),
                "right_shoulder": _kp(0.4),
                "right_hip": _kp(0.6),
            },
        }
        for i in range(N_FRAMES)
    ]
    _write(root / f"{analysis_id}_pose_smoothed.json", {"frame_count": N_FRAMES, "frames": frames})
    _write(
        root / f"{analysis_id}_pose_angles.json",
        {
            "frames": [
                {"frame_index": i, "timestamp": i / FPS, "angles": {"right_elbow": 100.0 + i, "right_knee": 140.0 + i, "right_hip": 170.0}}
                for i in range(N_FRAMES)
            ]
        },
    )


@pytest.fixture
def outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    return tmp_path


def _q(view: dict, qid: str) -> dict:
    return next(q for q in view["questions"] if q["id"] == qid)


def test_clear_clip_has_the_ten_review_questions(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    view = clip_view("a1")
    assert view["stroke_type"] == "FOREHAND_CLEAR"
    assert (view["handedness"], view["camera_view"]) == ("RIGHT", "SIDE")
    assert view["system_contact_frame"] == CONTACT
    assert view["fps"] == pytest.approx(FPS)
    assert [q["id"] for q in view["questions"]] == CLEAR_IDS
    assert [q["moment"] for q in view["questions"]] == [
        "preparation", "preparation", "preparation", "preparation",
        "contact", "contact", "contact", "contact",
        "follow_through", "follow_through",
    ]
    elbow = _q(view, "elbow")
    assert (elbow["title"], elbow["kind"], elbow["value"], elbow["unit"]) == (
        "Arm straight at the hit", "measured", 150.0, "deg"
    )
    assert elbow["measured_at"] == {"label": "At the hit", "frame": CONTACT}
    assert [o["id"] for o in elbow["rating_options"]] == ["good", "needs_work", "looks_wrong"]
    assert _q(view, "height")["value"] == pytest.approx(0.35)
    assert _q(view, "prep")["value"] == 1.0
    assert _q(view, "prep")["measured_at"] == {"label": "End of the racket-back", "frame": 15}
    assert _q(view, "knee")["measured_at"]["frame"] == 8
    assert _q(view, "legs")["value"] == 4.0
    sideon = _q(view, "sideon")
    assert (sideon["kind"], sideon["value"], sideon["available"], sideon["measured_at"]) == (
        "coach_only", None, True, None
    )
    assert [o["id"] for o in sideon["rating_options"]] == ["good", "needs_work", "cant_see"]
    assert sideon["joints"] == ["left_shoulder", "right_shoulder"]


def test_moments_seek_to_frames_from_saved_phases(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    view = clip_view("a1")
    assert [(m["id"], m["title"], m["frame"]) for m in view["moments"]] == [
        ("preparation", "Getting ready", 8),
        ("contact", "The hit", CONTACT),
        ("follow_through", "After the hit", 30),
    ]


def test_other_strokes_keep_the_original_stats(outputs: Path) -> None:
    seed_analysis(outputs, "s1", stroke="FOREHAND_SMASH")
    view = clip_view("s1")
    ids = [q["id"] for q in view["questions"]]
    assert ids[0] == "contact_elbow_angle" and "follow_through" in ids
    assert all(q["kind"] == "measured" for q in view["questions"])
    assert view["legacy_ids"] == {}


def test_measured_question_without_a_value_is_not_required(outputs: Path) -> None:
    seed_analysis(outputs, "a2", elbow=None)
    elbow = _q(clip_view("a2"), "elbow")
    assert (elbow["value"], elbow["available"]) == (None, False)


def test_pose_feed_has_points_and_angles_per_frame(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    pose = clip_pose("a1")
    assert pose["keypoint_names"] == list(KEYPOINT_NAMES)
    assert len(pose["frames"]) == N_FRAMES
    frame = pose["frames"][CONTACT]
    assert frame["frame_index"] == CONTACT
    wrist = frame["points"][KEYPOINT_NAMES.index("right_wrist")]
    assert wrist == [pytest.approx(0.62), pytest.approx(0.33), 0.9]
    assert frame["points"][KEYPOINT_NAMES.index("nose")] is None
    assert frame["angles"] == {"right_elbow": 120.0, "right_knee": 160.0}
    assert routes.get_clip_pose("a1")["fps"] == pytest.approx(FPS)
    with pytest.raises(HTTPException):
        routes.get_clip_pose("nope")


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


def test_question_wording_comes_from_the_config_file(
    outputs: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_analysis(outputs, "a1")
    config = load_stats_config()
    config["question_sets"]["FOREHAND_CLEAR"][0]["title"] = "Side-on (edited)"
    edited = tmp_path_factory.mktemp("cfg") / "labelling_stats.json"
    edited.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(clips_module, "STATS_CONFIG_PATH", edited)
    assert clip_view("a1")["questions"][0]["title"] == "Side-on (edited)"


def test_question_config_is_well_formed() -> None:
    config = load_stats_config()
    moments = {m["id"] for m in config["moments"]}
    assert moments == {"preparation", "contact", "follow_through"}
    for name, questions in config["question_sets"].items():
        ids = [q["id"] for q in questions]
        assert len(ids) == len(set(ids)), name
        for q in questions:
            assert {"id", "title", "hint", "moment", "kind"} <= set(q)
            assert q["moment"] in moments
            assert q["kind"] in {"measured", "coach_only"}
            if q["kind"] == "measured":
                assert q["metric"]["measured_at"] in config["measure_points"]
                assert q["metric"]["source"]["kind"] in {
                    "metric",
                    "hand_height_at_contact",
                    "wrist_above_shoulder_at_backswing_end",
                }
            else:
                assert "metric" not in q
            assert set(q.get("joints") or []) <= set(KEYPOINT_NAMES)
    clear = config["question_sets"]["FOREHAND_CLEAR"]
    assert len(clear) == 10
    replaced = {old for q in clear for old in q.get("replaces") or []}
    assert replaced <= {q["id"] for q in config["question_sets"]["default"]}
    assert [r["value"] for r in config["overall_ratings"]] == [1, 2, 3, 4, 5]


def test_unknown_analysis_is_not_found(outputs: Path) -> None:
    with pytest.raises(FileNotFoundError):
        clip_view("nope")
    with pytest.raises(FileNotFoundError):
        clip_view("../etc")


ALLOWED = {
    "elbow": {"good", "needs_work", "looks_wrong"},
    "legs": {"good", "needs_work", "looks_wrong"},
    "sideon": {"good", "needs_work", "cant_see"},
}


def _save(store: LabelStore, body: dict) -> dict:
    return store.save(
        "a1",
        body,
        allowed_ratings=ALLOWED,
        system_contact_frame=CONTACT,
        frame_count=N_FRAMES,
        batch_id="b1",
    )


def test_label_format(tmp_path: Path) -> None:
    BatchStore(tmp_path).save(Batch(batch_id="b1", name="B1"))
    store = LabelStore(tmp_path)
    label = _save(
        store,
        {
            "coach": "  Linh  Tran ",
            "corrected_hit_frame": 22,
            "stats": {
                "elbow": {"rating": "needs_work", "comment": " too bent "},
                "sideon": {"rating": "cant_see", "comment": ""},
            },
            "overall_rating": 3,
            "most_important_fix": "elbow",
            "feedback": "Reach higher.",
            "general_comment": " Camera a bit far away. ",
        },
    )
    assert label["label_format_version"] == "2.0.0"
    assert (label["most_important_fix"], label["feedback"], label["general_comment"]) == (
        "elbow",
        "Reach higher.",
        "Camera a bit far away.",
    )
    assert label["coach"] == "Linh Tran"
    assert label["batch_id"] == "b1"
    assert label["system_contact_frame"] == CONTACT
    assert label["corrected_hit_frame"] == 22
    assert label["stats"] == {
        "elbow": {"rating": "needs_work", "comment": "too bent"},
        "sideon": {"rating": "cant_see", "comment": ""},
    }
    assert label["overall_rating"] == 3
    assert label["created_at"] and label["updated_at"]
    again = _save(store, {"coach": "linh tran", "overall_rating": 4})
    assert again["created_at"] == label["created_at"]
    assert store.get("a1", "LINH TRAN")["overall_rating"] == 4


def test_most_important_fix_can_be_something_not_listed(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    options = clip_view("a1")["fix_options"]
    assert [o["id"] for o in options] == CLEAR_IDS + ["not_listed"]
    assert options[-1]["title"] == "Something not listed"
    saved = routes.put_clip_label(
        "a1", routes.ClipLabelIn(coach="Linh", most_important_fix="not_listed", general_comment="ok")
    )
    assert saved["label"]["most_important_fix"] == "not_listed"
    assert routes.get_clip_label("a1", coach="Linh")["label"]["general_comment"] == "ok"


def test_label_for_an_unknown_batch_is_kept_without_the_batch_link(tmp_path: Path) -> None:
    label = _save(LabelStore(tmp_path), {"coach": "Linh", "overall_rating": 2})
    assert label["batch_id"] is None
    assert label["overall_rating"] == 2


def test_hit_frame_equal_to_the_systems_is_stored_as_null(tmp_path: Path) -> None:
    assert _save(LabelStore(tmp_path), {"coach": "Linh", "corrected_hit_frame": CONTACT})[
        "corrected_hit_frame"
    ] is None


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"coach": "Linh", "corrected_hit_frame": N_FRAMES}, "outside this clip"),
        ({"coach": "Linh", "stats": {"made_up": {"rating": "good"}}}, "Unknown question"),
        ({"coach": "Linh", "stats": {"legs": {"rating": "great"}}}, "not an answer"),
        ({"coach": "Linh", "stats": {"elbow": {"rating": "cant_see"}}}, "not an answer"),
        ({"coach": "Linh", "stats": {"sideon": {"rating": "looks_wrong"}}}, "not an answer"),
        ({"coach": "Linh", "overall_rating": 6}, "1 to 5"),
        ({"coach": "Linh", "most_important_fix": "made_up"}, "most important thing to fix"),
        ({"coach": "  "}, "Add your name"),
    ],
)
def test_invalid_labels_are_refused(tmp_path: Path, body: dict, message: str) -> None:
    with pytest.raises(LabelError, match=message):
        _save(LabelStore(tmp_path), body)


def test_answers_under_older_ids_survive_a_new_save(tmp_path: Path) -> None:
    store = LabelStore(tmp_path)
    store.write(
        {
            "analysis_id": "a1",
            "coach": "Linh",
            "stats": {"contact_shoulder_angle": {"rating": "good", "comment": "old"}},
        }
    )
    saved = _save(store, {"coach": "Linh", "stats": {"elbow": {"rating": "good"}}})
    assert saved["stats"]["contact_shoulder_angle"] == {"rating": "good", "comment": "old"}
    assert saved["stats"]["elbow"]["rating"] == "good"


def test_label_status() -> None:
    available = ["elbow", "legs"]
    assert label_status(None, available) == "not_started"
    partial = {"overall_rating": 4, "stats": {"elbow": {"rating": "good"}}}
    assert label_status(partial, available) == "in_progress"
    partial["stats"]["legs"] = {"rating": "looks_wrong"}
    assert label_status(partial, available) == "done"


def _all_answers(view: dict) -> dict:
    return {
        q["id"]: routes.StatLabelIn(rating=q["rating_options"][0]["id"])
        for q in view["questions"]
        if q["available"]
    }


def test_coach_only_questions_save_cant_see(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    answers = _all_answers(clip_view("a1"))
    answers["sideon"] = routes.StatLabelIn(rating="cant_see", comment="camera is behind")
    saved = routes.put_clip_label(
        "a1", routes.ClipLabelIn(coach="Linh", stats=answers, overall_rating=3)
    )
    assert saved["status"] == "done"
    stored = LabelStore().get("a1", "Linh")
    assert stored["stats"]["sideon"] == {"rating": "cant_see", "comment": "camera is behind"}
    with pytest.raises(HTTPException) as exc:
        routes.put_clip_label(
            "a1",
            routes.ClipLabelIn(coach="Linh", stats={"elbow": routes.StatLabelIn(rating="cant_see")}),
        )
    assert exc.value.status_code == 422


def test_labels_saved_under_older_stat_ids_stay_readable(outputs: Path) -> None:
    seed_analysis(outputs, "a1")
    LabelStore().write(
        {
            "analysis_id": "a1",
            "coach": "Linh",
            "overall_rating": 4,
            "stats": {
                "contact_elbow_angle": {"rating": "needs_work", "comment": "bent"},
                "contact_shoulder_angle": {"rating": "good", "comment": ""},
            },
        }
    )
    label = routes.get_clip_label("a1", coach="Linh")["label"]
    assert label["stats"]["elbow"] == {"rating": "needs_work", "comment": "bent"}
    assert "contact_elbow_angle" not in label["stats"]
    assert label["stats"]["contact_shoulder_angle"]["rating"] == "good"


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
    routes.put_clip_label(
        "a1",
        routes.ClipLabelIn(
            coach="Linh", batch_id="set-1", stats=_all_answers(clip_view("a1")), overall_rating=4
        ),
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
    listed = routes.get_batches(coach="LINH")["batches"]
    assert [(b["batch_id"], b["name"], b["clip_count"], b["labelled_count"]) for b in listed] == [
        ("set-1", "Set 1", 3, 1)
    ]
    assert routes.get_batches(coach="Minh")["batches"][0]["labelled_count"] == 0
    assert routes.get_batches(coach=None)["batches"][0]["labelled_count"] == 1


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
