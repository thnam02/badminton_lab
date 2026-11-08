"""Coach labelling workspace: batches, clip views and coach labels."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.labelling.batches import Batch, BatchStore
from app.labelling.clips import clip_view
from app.labelling.export import export_batch, rows_to_csv
from app.labelling.labels import (
    STATUS_DONE,
    STATUS_NOT_STARTED,
    LabelError,
    LabelStore,
    label_status,
)

router = APIRouter(prefix="/labelling", tags=["labelling"])


class StatLabelIn(BaseModel):
    rating: Literal["good", "needs_work", "looks_wrong"] | None = None
    comment: str = ""


class ClipLabelIn(BaseModel):
    coach: str = Field(min_length=1)
    batch_id: str | None = None
    corrected_hit_frame: int | None = Field(default=None, ge=0)
    stats: dict[str, StatLabelIn] = Field(default_factory=dict)
    overall_rating: int | None = Field(default=None, ge=1, le=5)
    feedback: str = ""


def _clip(analysis_id: str) -> dict:
    try:
        return clip_view(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _available(clip: dict) -> list[str]:
    return [s["id"] for s in clip["stats"] if s["available"]]


def _clip_statuses(batch: Batch, coach: str | None) -> list[dict]:
    """Each clip's label status: this coach's if given, otherwise any coach's."""
    store = LabelStore()
    clips = []
    for position, entry in enumerate(batch.clips, start=1):
        try:
            clip = clip_view(entry.analysis_id)
        except FileNotFoundError:
            clips.append(
                {
                    "position": position,
                    "analysis_id": entry.analysis_id,
                    "source_file": entry.source_file,
                    "missing": True,
                    "status": STATUS_NOT_STARTED,
                    "labelled": False,
                    "coach_count": 0,
                }
            )
            continue
        available = _available(clip)
        labels = store.for_clip(entry.analysis_id)
        if coach and coach.strip():
            mine = store.get(entry.analysis_id, coach)
            status = label_status(mine, available)
        else:
            statuses = [label_status(lb, available) for lb in labels]
            status = (
                STATUS_DONE
                if STATUS_DONE in statuses
                else statuses[0] if statuses else STATUS_NOT_STARTED
            )
        clips.append(
            {
                "position": position,
                "analysis_id": entry.analysis_id,
                "source_file": entry.source_file,
                "stroke_type": clip["stroke_type"],
                "missing": False,
                "status": status,
                "labelled": status == STATUS_DONE,
                "coach_count": len(labels),
            }
        )
    return clips


@router.get("/batches")
def get_batches(coach: str | None = Query(default=None)) -> dict:
    """All batches with clip counts and labelled counts (for this coach, if given)."""
    batches = BatchStore().list()
    items = []
    for b in batches:
        clips = _clip_statuses(b, coach)
        items.append(
            {
                "batch_id": b.batch_id,
                "name": b.name,
                "clip_count": len(b.clips),
                "labelled_count": sum(1 for c in clips if c["labelled"]),
                "created_at": b.created_at,
            }
        )
    return {"count": len(items), "coach": coach, "batches": items}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, coach: str | None = Query(default=None)) -> dict:
    """Clips in the batch and whether each is labelled (by this coach, if given)."""
    try:
        batch = BatchStore().get(batch_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    clips = _clip_statuses(batch, coach)
    return {
        "batch_id": batch.batch_id,
        "name": batch.name,
        "created_at": batch.created_at,
        "coach": coach,
        "total": len(clips),
        "labelled_count": sum(1 for c in clips if c["labelled"]),
        "clips": clips,
    }


@router.get("/batches/{batch_id}/export", response_model=None)
def get_batch_export(
    batch_id: str,
    format: Literal["csv", "json"] = Query(default="csv"),
    coach: str | None = Query(default=None),
) -> Response | dict:
    """One row per clip per stat (per coach who labelled it), as CSV or JSON."""
    try:
        export = export_batch(batch_id, coach=coach)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if format == "json":
        return export
    return Response(
        content=rows_to_csv(export["rows"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{batch_id}_labels.csv"'},
    )


@router.get("/clips/{analysis_id}")
def get_clip(analysis_id: str) -> dict:
    """Video, capture context, system hit frame and stats, from saved artifacts only."""
    return _clip(analysis_id)


@router.get("/clips/{analysis_id}/label")
def get_clip_label(analysis_id: str, coach: str = Query(..., min_length=1)) -> dict:
    clip = _clip(analysis_id)
    try:
        label = LabelStore().get(analysis_id, coach)
    except LabelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"label": label, "status": label_status(label, _available(clip))}


@router.put("/clips/{analysis_id}/label")
def put_clip_label(analysis_id: str, body: ClipLabelIn) -> dict:
    clip = _clip(analysis_id)
    try:
        label = LabelStore().save(
            analysis_id,
            body.model_dump(exclude={"batch_id"}),
            stat_ids={s["id"] for s in clip["stats"]},
            system_contact_frame=clip["system_contact_frame"],
            frame_count=clip["frame_count"],
            batch_id=body.batch_id,
        )
    except LabelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"label": label, "status": label_status(label, _available(clip))}
