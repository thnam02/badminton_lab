"""Coach rule builder: picture boundaries, metric mapping, label agreement, drafts."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.coach.matching import hand_height
from app.coach.rule_builder_config import (
    AGREEMENT_NOT_ENOUGH_DATA,
    AGREEMENT_SEPARATES_WELL,
    BOUNDARY_SETS,
    LABEL_QUESTIONS,
    RULE_TARGETS,
)
from app.coach.rules import (
    CoachRule,
    CoachRuleError,
    check_coach_rule,
    save_coach_rule,
    severity_cap,
)
from app.coach.stores import ClipLabel, ClipLabelStore, RuleDraftStore
from app.config import settings
from app.routes import coach as coach_routes

FPS = 30.0
CLEAR = "FOREHAND_CLEAR"
HIT = 40


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _kp(y: float, conf: float = 0.9) -> dict:
    return {"x": 0.5, "y": y, "confidence": conf}


def _seed_clip(
    root: Path,
    analysis_id: str,
    *,
    elbow_at_hit: float = 150.0,
    wrist_y_at: dict[int, float] | None = None,
    prep_knee: float | None = 150.0,
    n: int = 60,
) -> None:
    """Saved analysis files: shoulder y 0.4, hip y 0.6 (torso 0.2), wrist y 0.3."""
    angle_frames, pose_frames = [], []
    for i in range(n):
        ts = i / FPS
        angle_frames.append(
            {
                "frame_index": i,
                "timestamp": ts,
                "angles": {"right_elbow": elbow_at_hit if i == HIT else 90.0},
            }
        )
        wrist = (wrist_y_at or {}).get(i, 0.5)
        pose_frames.append(
            {
                "frame_index": i,
                "timestamp": ts,
                "keypoints": {
                    "right_wrist": _kp(wrist),
                    "right_shoulder": _kp(0.4),
                    "right_hip": _kp(0.6),
                },
            }
        )
    _write(root / f"{analysis_id}_pose_angles.json", {"frames": angle_frames})
    _write(root / f"{analysis_id}_pose_smoothed.json", {"frames": pose_frames})
    _write(
        root / f"{analysis_id}_pose_phases.json",
        {
            "segments": [
                {"phase": "PREPARATION", "start_frame_index": 0, "end_frame_index": 10},
                {"phase": "BACKSWING", "start_frame_index": 11, "end_frame_index": 30},
            ]
        },
    )
    _write(
        root / f"{analysis_id}_pose_stroke_metrics.json",
        {"preparation_knee_angle_deg": prep_knee},
    )


def _label(
    root: Path,
    analysis_id: str,
    question: str,
    answer: str,
    *,
    coach: str = "Linh",
    stroke: str = CLEAR,
    hit: int | None = HIT,
) -> None:
    ClipLabelStore(root).upsert(
        ClipLabel(
            coach=coach,
            analysis_id=analysis_id,
            stroke_type=stroke,
            hit_frame_index=hit,
            answers={question: answer},
        )
    )


FAULT_ELBOWS = (110.0, 115.0, 118.0, 122.0, 125.0, 138.0)
FINE_ELBOWS = (135.0, 145.0, 150.0, 155.0, 165.0, 170.0)


def _seed_elbow_reviews(root: Path) -> None:
    for i, angle in enumerate(FAULT_ELBOWS):
        _seed_clip(root, f"fault{i}", elbow_at_hit=angle)
        _label(root, f"fault{i}", "bent_elbow", "yes")
    for i, angle in enumerate(FINE_ELBOWS):
        _seed_clip(root, f"fine{i}", elbow_at_hit=angle)
        _label(root, f"fine{i}", "bent_elbow", "no")


def _elbow_rule(boundary: str = "slightly_bent", **kw) -> CoachRule:
    return CoachRule(
        coach="Linh",
        stroke_type=CLEAR,
        moment="contact",
        body_part="elbow",
        boundary_id=boundary,
        **kw,
    )


def test_elbow_pictures_are_the_configured_angles() -> None:
    pictures = BOUNDARY_SETS["elbow_angle"].pictures
    assert [(p.label, p.value) for p in pictures] == [
        ("Very bent", 100.0),
        ("Bent", 120.0),
        ("Slightly bent", 140.0),
        ("Nearly straight", 160.0),
        ("Straight", 180.0),
    ]
    for target in RULE_TARGETS.values():
        assert target.boundary_set in BOUNDARY_SETS
        assert target.label_question in LABEL_QUESTIONS


def test_picture_values_are_tagged_unvalidated_priors() -> None:
    source = Path("app/coach/rule_builder_config.py").read_text(encoding="utf-8")
    picture_lines = [ln for ln in source.splitlines() if "BoundaryPicture(\"" in ln]
    assert len(picture_lines) == 15
    assert all("# unvalidated prior" in ln for ln in picture_lines)


@pytest.mark.parametrize(
    ("part", "moment", "expected"),
    [
        ("shoulder", "contact", "We don't measure shoulder yet"),
        ("elbow", "preparation", "For this body part, pick: the hit"),
        ("knees", "contact", "pick: getting ready"),
    ],
)
def test_rule_without_a_matching_metric_says_so_and_cannot_be_saved(
    tmp_path: Path, part: str, moment: str, expected: str
) -> None:
    rule = CoachRule(
        coach="Linh",
        stroke_type=CLEAR,
        moment=moment,
        body_part=part,
        boundary_id="bent",
        importance="tip",
    )
    with pytest.raises(CoachRuleError, match=expected):
        check_coach_rule(rule, tmp_path)
    with pytest.raises(CoachRuleError, match=expected):
        save_coach_rule(rule, tmp_path)
    assert RuleDraftStore(tmp_path).all() == []


def test_rule_is_checked_at_the_coach_marked_hit_frame(tmp_path: Path) -> None:
    _seed_elbow_reviews(tmp_path)
    result = check_coach_rule(_elbow_rule(), tmp_path)
    match = result["match"]
    assert result["target"]["metric_id"] == "contact_elbow_angle_deg"
    assert (match["fault_clips"], match["fine_clips"]) == (6, 6)
    # Flag below 140°: every fault caught; the 135° fine clip is a false flag.
    assert (match["caught"], match["missed"], match["false_flags"]) == (6, 0, 1)
    assert match["balanced_accuracy"] == pytest.approx(0.5 * (1 + 5 / 6))
    assert match["agreement_status"] == AGREEMENT_SEPARATES_WELL
    assert match["disagreements"] == [
        {
            "analysis_id": "fine0",
            "kind": "false_flag",
            "value": 135.0,
            "frame_index": HIT,
            "timestamp": pytest.approx(HIT / FPS),
        }
    ]
    assert match["suggested"]["picture_id"] == "slightly_bent"
    assert match["suggested"]["steps_from_choice"] == 0


def test_suggestion_is_the_picture_with_the_best_balanced_accuracy(tmp_path: Path) -> None:
    _seed_elbow_reviews(tmp_path)
    match = check_coach_rule(_elbow_rule("nearly_straight"), tmp_path)["match"]
    # Flag below 160°: 6 caught, 4 fine clips flagged.
    assert (match["caught"], match["false_flags"]) == (6, 4)
    assert match["suggested"]["picture_id"] == "slightly_bent"
    assert match["suggested"]["steps_from_choice"] == -1
    assert (match["suggested"]["caught"], match["suggested"]["false_flags"]) == (6, 1)
    kinds = sorted(d["kind"] for d in match["disagreements"])
    assert kinds == ["false_flag"] * 4


def test_only_this_coach_same_stroke_certain_answers_count(tmp_path: Path) -> None:
    _seed_elbow_reviews(tmp_path)
    _seed_clip(tmp_path, "other", elbow_at_hit=100.0)
    _label(tmp_path, "other", "bent_elbow", "yes", coach="Minh")
    _seed_clip(tmp_path, "smash", elbow_at_hit=100.0)
    _label(tmp_path, "smash", "bent_elbow", "yes", stroke="FOREHAND_SMASH")
    _seed_clip(tmp_path, "unsure", elbow_at_hit=100.0)
    _label(tmp_path, "unsure", "bent_elbow", "cant_tell")
    _seed_clip(tmp_path, "nohit", elbow_at_hit=100.0)
    _label(tmp_path, "nohit", "bent_elbow", "yes", hit=None)
    match = check_coach_rule(_elbow_rule(), tmp_path)["match"]
    assert match["reviewed_clips"] == 14
    assert match["unanswered_clips"] == 1
    assert match["unmeasured"] == [{"analysis_id": "nohit", "reason": "no hit frame marked"}]
    assert (match["fault_clips"], match["fine_clips"]) == (6, 6)


def test_coach_name_matching_ignores_case_and_spacing(tmp_path: Path) -> None:
    _seed_elbow_reviews(tmp_path)
    rule = _elbow_rule()
    rule.coach = "  linh "
    assert check_coach_rule(rule, tmp_path)["match"]["fault_clips"] == 6


def test_hand_height_uses_highest_wrist_near_the_hit_in_torso_lengths(tmp_path: Path) -> None:
    # Shoulder 0.4, hip 0.6: wrist at 0.33 is 0.35 torso lengths above the shoulder.
    _seed_clip(tmp_path, "c", wrist_y_at={HIT - 2: 0.33, HIT: 0.36, HIT + 3: 0.1})
    _label(tmp_path, "c", "low_contact", "yes")
    rule = CoachRule(
        coach="Linh",
        stroke_type=CLEAR,
        moment="contact",
        body_part="hand_height",
        boundary_id="head",
    )
    match = check_coach_rule(rule, tmp_path)["match"]
    # 0.35 is not below the "head height" boundary (0.35), so the coach's fault is missed;
    # the higher wrist 3 frames after the hit is outside the window.
    assert match["missed"] == 1
    assert match["disagreements"][0]["value"] == pytest.approx(0.35)
    frame = {"keypoints": {"right_wrist": _kp(0.33), "right_shoulder": _kp(0.4), "right_hip": _kp(0.6)}}
    assert hand_height(frame, 0.5) == pytest.approx(0.35)
    frame["keypoints"]["right_wrist"] = _kp(0.33, conf=0.2)
    assert hand_height(frame, 0.5) is None


def test_preparation_knee_flags_straighter_than_the_choice(tmp_path: Path) -> None:
    _seed_clip(tmp_path, "stiff", prep_knee=172.0)
    _label(tmp_path, "stiff", "stiff_knee", "yes")
    _seed_clip(tmp_path, "ok", prep_knee=150.0)
    _label(tmp_path, "ok", "stiff_knee", "no")
    rule = CoachRule(
        coach="Linh",
        stroke_type=CLEAR,
        moment="preparation",
        body_part="knees",
        boundary_id="nearly_straight",
    )
    match = check_coach_rule(rule, tmp_path)["match"]
    assert (match["caught"], match["false_flags"]) == (1, 0)
    assert match["agreement_status"] == AGREEMENT_NOT_ENOUGH_DATA


def test_importance_maps_to_severity_caps() -> None:
    assert severity_cap("tip", AGREEMENT_NOT_ENOUGH_DATA) == "MINOR"
    assert severity_cap("worth_fixing", AGREEMENT_NOT_ENOUGH_DATA) == "MODERATE"
    assert severity_cap("must_fix_first", AGREEMENT_SEPARATES_WELL) == "MAJOR"
    for status in ("overlaps", AGREEMENT_NOT_ENOUGH_DATA):
        with pytest.raises(CoachRuleError, match="separates well"):
            severity_cap("must_fix_first", status)


def test_must_fix_first_is_refused_without_enough_agreement(tmp_path: Path) -> None:
    with pytest.raises(CoachRuleError, match="not enough data"):
        save_coach_rule(_elbow_rule(importance="must_fix_first"), tmp_path)
    assert RuleDraftStore(tmp_path).all() == []


def test_saved_rule_is_a_draft_labelled_with_the_coach(tmp_path: Path) -> None:
    _seed_elbow_reviews(tmp_path)
    draft = save_coach_rule(
        _elbow_rule(importance="must_fix_first", message="  Reach up at the hit. "),
        tmp_path,
    )
    assert draft["coach"] == "Linh"
    assert draft["status"] == "draft"
    assert draft["promoted_rule_version"] is None
    assert draft["severity_cap"] == "MAJOR"
    assert draft["message"] == "Reach up at the hit."
    assert draft["metric_id"] == "contact_elbow_angle_deg"
    assert draft["boundary"] == {
        "id": "slightly_bent",
        "label": "Slightly bent",
        "value": 140.0,
        "unit": "deg",
    }
    assert draft["agreement"]["status"] == AGREEMENT_SEPARATES_WELL
    assert RuleDraftStore(tmp_path).all() == [draft]
    assert (tmp_path / "coach" / "rule_drafts.json").is_file()


def test_saving_needs_a_coach_name(tmp_path: Path) -> None:
    rule = _elbow_rule(importance="tip")
    rule.coach = "  "
    with pytest.raises(CoachRuleError, match="Add your name"):
        save_coach_rule(rule, tmp_path)


def test_live_analysis_never_imports_coach_rules() -> None:
    """Drafts and coach labels only change analysis after the dev team promotes them."""
    app_dir = Path("app")
    allowed = {app_dir / "routes" / "coach.py", app_dir / "routes" / "labelling.py", app_dir / "main.py"}
    offenders = []
    for path in app_dir.rglob("*.py"):
        if (
            path.is_relative_to(app_dir / "coach")
            or path.is_relative_to(app_dir / "labelling")
            or path in allowed
        ):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(
                n == pkg or n.startswith(f"{pkg}.")
                for n in names
                for pkg in ("app.coach", "app.labelling")
            ):
                offenders.append(str(path))
    assert offenders == []


def test_routes_report_unsupported_rules_and_refuse_bad_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    body = coach_routes.CoachRuleIn(
        coach="Linh",
        stroke_type="forehand_clear",
        moment="contact",
        body_part="shoulder",
        boundary_id="bent",
        importance="tip",
    )
    checked = coach_routes.post_rule_check(body)
    assert checked["supported"] is False
    assert "shoulder" in checked["reason"]
    with pytest.raises(HTTPException) as exc:
        coach_routes.post_rule_draft(body)
    assert exc.value.status_code == 422

    saved = coach_routes.put_label(
        coach_routes.ClipLabelIn(
            coach="Linh",
            analysis_id="a1",
            stroke_type="forehand_clear",
            hit_frame_index=12,
            answers={"bent_elbow": "yes"},
        )
    )
    assert saved["stroke_type"] == CLEAR
    assert coach_routes.get_labels(coach="LINH", stroke_type="forehand_clear")["count"] == 1
    with pytest.raises(HTTPException):
        coach_routes.put_label(
            coach_routes.ClipLabelIn(
                coach="Linh",
                analysis_id="a1",
                stroke_type=CLEAR,
                answers={"bent_elbow": "maybe"},
            )
        )
    options = coach_routes.get_rule_options()
    assert {(t["body_part"], t["moment"]) for t in options["targets"]} == set(RULE_TARGETS)
