"""Coach rules: resolve to a metric, check against labels, save as drafts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.coach.matching import check_rule
from app.coach.rule_builder_config import (
    AGREEMENT_LABELS,
    AGREEMENT_SEPARATES_WELL,
    BODY_PARTS,
    BOUNDARY_SETS,
    IMPORTANCE_LABELS,
    IMPORTANCE_MUST_FIX_FIRST,
    LABEL_QUESTIONS,
    MOMENTS,
    RULE_TARGETS,
    SEVERITY_CAP_BY_IMPORTANCE,
    BoundaryPicture,
    RuleTarget,
    rule_target,
    unsupported_reason,
)
from app.coach.stores import ClipLabelStore, RuleDraftStore
from app.schemas.stroke_types import normalize_stroke_type, stroke_type_label

MAX_MESSAGE_CHARS = 500


class CoachRuleError(ValueError):
    """A coach rule that cannot be checked or saved; the message is user-facing."""


@dataclass(slots=True)
class CoachRule:
    coach: str
    stroke_type: str
    moment: str
    body_part: str
    boundary_id: str
    importance: str | None = None
    message: str = ""


def rule_options() -> dict[str, Any]:
    return {
        "moments": [{"id": k, "label": v} for k, v in MOMENTS.items()],
        "body_parts": [{"id": k, "label": v} for k, v in BODY_PARTS.items()],
        "boundary_sets": {
            sid: {
                "unit": s.unit,
                "pictures": [asdict(p) for p in s.pictures],
            }
            for sid, s in BOUNDARY_SETS.items()
        },
        "targets": [
            {"body_part": part, "moment": moment, **_target_view(t)}
            for (part, moment), t in RULE_TARGETS.items()
        ],
        "importance": [
            {"id": k, "label": v, "severity_cap": SEVERITY_CAP_BY_IMPORTANCE[k]}
            for k, v in IMPORTANCE_LABELS.items()
        ],
        "agreement_labels": AGREEMENT_LABELS,
    }


def _target_view(t: RuleTarget) -> dict[str, Any]:
    return {
        "metric_id": t.metric_id,
        "metric_label": t.metric_label,
        "boundary_set": t.boundary_set,
        "direction": t.direction,
        "label_question": t.label_question,
        "label_question_title": LABEL_QUESTIONS[t.label_question],
        "prompt": t.prompt,
        "flag_hint": t.flag_hint,
        "problem_noun": t.problem_noun,
    }


def _resolve(rule: CoachRule) -> tuple[str, RuleTarget, BoundaryPicture]:
    try:
        stroke = normalize_stroke_type(rule.stroke_type).value
    except ValueError as exc:
        raise CoachRuleError(str(exc)) from exc
    if rule.moment not in MOMENTS:
        raise CoachRuleError(f"Unknown moment {rule.moment!r}.")
    if rule.body_part not in BODY_PARTS:
        raise CoachRuleError(f"Unknown body part {rule.body_part!r}.")
    target = rule_target(rule.body_part, rule.moment)
    if target is None:
        raise CoachRuleError(unsupported_reason(rule.body_part, rule.moment))
    picture = BOUNDARY_SETS[target.boundary_set].picture(rule.boundary_id)
    if picture is None:
        raise CoachRuleError(f"Unknown picture {rule.boundary_id!r} for this body part.")
    return stroke, target, picture


def check_coach_rule(rule: CoachRule, output_dir: Path | None = None) -> dict[str, Any]:
    stroke, target, picture = _resolve(rule)
    labels = (
        ClipLabelStore(output_dir).for_coach(rule.coach, stroke) if rule.coach.strip() else []
    )
    return {
        "stroke_type": stroke,
        "target": _target_view(target),
        "boundary": asdict(picture),
        "match": check_rule(target, picture, labels, output_dir),
    }


def severity_cap(importance: str, agreement_status: str) -> str:
    if importance not in SEVERITY_CAP_BY_IMPORTANCE:
        raise CoachRuleError(f"Unknown importance {importance!r}.")
    if (
        importance == IMPORTANCE_MUST_FIX_FIRST
        and agreement_status != AGREEMENT_SEPARATES_WELL
    ):
        raise CoachRuleError(
            '"Must fix first" needs a rule that separates well on your reviewed clips '
            f"(currently: {AGREEMENT_LABELS[agreement_status].lower()}). "
            'Choose "Worth fixing" or review more clips.'
        )
    return SEVERITY_CAP_BY_IMPORTANCE[importance]


def save_coach_rule(rule: CoachRule, output_dir: Path | None = None) -> dict[str, Any]:
    coach = " ".join(rule.coach.split())
    if not coach:
        raise CoachRuleError("Add your name so the team knows whose rule this is.")
    if rule.importance is None:
        raise CoachRuleError("Choose how important this is.")
    message = rule.message.strip()
    if len(message) > MAX_MESSAGE_CHARS:
        raise CoachRuleError(f"Keep the message under {MAX_MESSAGE_CHARS} characters.")
    checked = check_coach_rule(rule, output_dir)
    match = checked["match"]
    cap = severity_cap(rule.importance, match["agreement_status"])
    stroke = checked["stroke_type"]
    target = checked["target"]
    boundary = checked["boundary"]
    title = f"{BODY_PARTS[rule.body_part]} · {MOMENTS[rule.moment]}"
    return RuleDraftStore(output_dir).add(
        {
            "coach": coach,
            "title": title,
            "stroke_type": stroke,
            "stroke_label": stroke_type_label(stroke),
            "moment": rule.moment,
            "body_part": rule.body_part,
            "metric_id": target["metric_id"],
            "metric_label": target["metric_label"],
            "direction": target["direction"],
            "boundary": {**boundary, "unit": BOUNDARY_SETS[target["boundary_set"]].unit},
            "importance": rule.importance,
            "severity_cap": cap,
            "message": message,
            "agreement": {
                "status": match["agreement_status"],
                "fault_clips": match["fault_clips"],
                "fine_clips": match["fine_clips"],
                "caught": match["caught"],
                "missed": match["missed"],
                "false_flags": match["false_flags"],
                "balanced_accuracy": match["balanced_accuracy"],
            },
        }
    )
