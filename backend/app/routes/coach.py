"""Coach workspace: clip labels, rule builder checks and draft rules."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.coach.rules import (
    CoachRule,
    CoachRuleError,
    check_coach_rule,
    rule_options,
    save_coach_rule,
)
from app.coach.stores import ClipLabel, ClipLabelStore, RuleDraftStore
from app.schemas.stroke_types import normalize_stroke_type

router = APIRouter(prefix="/coach", tags=["coach"])


class ClipLabelIn(BaseModel):
    coach: str = Field(min_length=1)
    analysis_id: str = Field(min_length=1)
    stroke_type: str
    hit_frame_index: int | None = Field(default=None, ge=0)
    no_shuttle: bool = False
    answers: dict[str, str] = Field(default_factory=dict)
    overall: int | None = Field(default=None, ge=1, le=5)
    notes: str = ""


class CoachRuleIn(BaseModel):
    coach: str = ""
    stroke_type: str
    moment: str
    body_part: str
    boundary_id: str
    importance: str | None = None
    message: str = ""


def _rule(body: CoachRuleIn) -> CoachRule:
    return CoachRule(**body.model_dump())


@router.get("/rule-options")
def get_rule_options() -> dict:
    return rule_options()


@router.get("/labels")
def get_labels(coach: str = Query(..., min_length=1), stroke_type: str | None = None) -> dict:
    try:
        stroke = normalize_stroke_type(stroke_type).value if stroke_type else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    labels = ClipLabelStore().for_coach(coach, stroke)
    return {"count": len(labels), "labels": [lb.to_dict() for lb in labels]}


@router.put("/labels")
def put_label(body: ClipLabelIn) -> dict:
    try:
        stroke = normalize_stroke_type(body.stroke_type).value
        label = ClipLabelStore().upsert(
            ClipLabel(**{**body.model_dump(), "stroke_type": stroke})
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return label.to_dict()


@router.post("/rules/check")
def post_rule_check(body: CoachRuleIn) -> dict:
    try:
        return {"supported": True, **check_coach_rule(_rule(body))}
    except CoachRuleError as exc:
        return {"supported": False, "reason": str(exc)}


@router.get("/rules/drafts")
def get_rule_drafts() -> dict:
    drafts = RuleDraftStore().all()
    return {"count": len(drafts), "drafts": drafts}


@router.post("/rules/drafts")
def post_rule_draft(body: CoachRuleIn) -> dict:
    try:
        return save_coach_rule(_rule(body))
    except CoachRuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
