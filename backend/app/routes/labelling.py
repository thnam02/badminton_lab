"""Coach labelling workspace: batches, clip views and coach labels."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.labelling.batches import Batch, BatchStore
from app.labelling.clips import answerable_ids, clip_pose, clip_view, normalize_label
from app.labelling.export import export_batch, rows_to_csv
from app.labelling.jobs import JobStore, UploadError, create_upload_job, job_view, submit_job
from app.processing.capture_context import (
    InvalidCaptureContextError,
    normalize_camera_view,
    normalize_handedness,
)
from app.schemas.stroke_types import UnsupportedStrokeError, normalize_stroke_type
from app.labelling.labels import (
    STATUS_DONE,
    STATUS_NOT_STARTED,
    LabelError,
    LabelStore,
    label_status,
)

router = APIRouter(prefix="/labelling", tags=["labelling"])


class StatLabelIn(BaseModel):
    rating: Literal["good", "needs_work", "looks_wrong", "cant_see"] | None = None
    comment: str = ""


class ClipLabelIn(BaseModel):
    coach: str = Field(min_length=1)
    batch_id: str | None = None
    corrected_hit_frame: int | None = Field(default=None, ge=0)
    stats: dict[str, StatLabelIn] = Field(default_factory=dict)
    overall_rating: int | None = Field(default=None, ge=1, le=5)
    most_important_fix: str | None = None
    feedback: str = ""
    general_comment: str = ""


def _clip(analysis_id: str) -> dict:
    try:
        return clip_view(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _status(label: dict | None, clip: dict) -> str:
    return label_status(normalize_label(label, clip), answerable_ids(clip))


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
        labels = store.for_clip(entry.analysis_id)
        if coach and coach.strip():
            status = _status(store.get(entry.analysis_id, coach), clip)
        else:
            statuses = [_status(lb, clip) for lb in labels]
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


@router.post("/batches", status_code=202)
def post_batch(
    files: list[UploadFile] = File(...),
    name: str = Form(...),
    stroke_type: str = Form(default="FOREHAND_CLEAR"),
    handedness: str = Form(default="RIGHT"),
    camera_view: str = Form(default="SIDE"),
) -> dict:
    """Upload clips as a new batch; they are analysed one by one in the background."""
    try:
        job = create_upload_job(
            [(f.filename or "", f.file) for f in files],
            name=name,
            stroke=normalize_stroke_type(stroke_type).value,
            handedness=normalize_handedness(handedness),
            camera_view=normalize_camera_view(camera_view),
        )
    except (UploadError, UnsupportedStrokeError, InvalidCaptureContextError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    submit_job(job["job_id"])
    return job_view(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    """Upload job progress, clip by clip."""
    try:
        return job_view(JobStore().get(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    """Video, capture context, moments and questions, from saved artifacts only."""
    return _clip(analysis_id)


@router.get("/clips/{analysis_id}/pose")
def get_clip_pose(analysis_id: str) -> dict:
    """Saved smoothed pose and joint angles per frame, for the review overlay."""
    try:
        return clip_pose(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/clips/{analysis_id}/label")
def get_clip_label(analysis_id: str, coach: str = Query(..., min_length=1)) -> dict:
    clip = _clip(analysis_id)
    try:
        label = LabelStore().get(analysis_id, coach)
    except LabelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"label": normalize_label(label, clip), "status": _status(label, clip)}


@router.put("/clips/{analysis_id}/label")
def put_clip_label(analysis_id: str, body: ClipLabelIn) -> dict:
    clip = _clip(analysis_id)
    try:
        label = LabelStore().save(
            analysis_id,
            body.model_dump(exclude={"batch_id"}),
            allowed_ratings={
                q["id"]: {o["id"] for o in q["rating_options"]} for q in clip["questions"]
            },
            system_contact_frame=clip["system_contact_frame"],
            frame_count=clip["frame_count"],
            batch_id=body.batch_id,
        )
    except LabelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"label": normalize_label(label, clip), "status": _status(label, clip)}
