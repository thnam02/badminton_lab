"""Coach labelling workspace: datasets, clip views and coach labels."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import ROLE_COACH, Session, require_admin, require_coach, require_signed_in
from app.config import settings
from app.labelling.batches import Batch, BatchClip, BatchStore
from app.labelling.datasets import (
    DatasetError,
    clip_statuses,
    create_dataset,
    dataset_summary,
    list_datasets,
    pickable_analyses,
    update_dataset,
)
from app.labelling.clips import answerable_ids, clip_pose, clip_view, normalize_label
from app.labelling.export import export_batch, rows_to_csv
from app.labelling.jobs import JobStore, UploadError, job_view, submit_job
from app.processing.capture_context import InvalidCaptureContextError
from app.schemas.stroke_types import UnsupportedStrokeError, normalize_stroke_type
from app.labelling.labels import LabelError, LabelStore, label_status

# Everything here needs a signed-in admin or coach; some routes narrow that further.
router = APIRouter(
    prefix="/labelling", tags=["labelling"], dependencies=[Depends(require_signed_in)]
)


class StatLabelIn(BaseModel):
    rating: Literal["good", "needs_work", "looks_wrong", "cant_see"] | None = None
    comment: str = ""


class ClipLabelIn(BaseModel):
    # Ignored: labels are saved under the signed-in coach's name.
    coach: str = ""
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


class DatasetUpdateIn(BaseModel):
    due_date: str | None = None
    note: str | None = None


def _dataset(dataset_id: str) -> Batch:
    try:
        return BatchStore().get(dataset_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/datasets")
def get_datasets() -> dict:
    """Every dataset with the coach's progress and its status, in the coach's order."""
    items = list_datasets(coach=settings.coach_name)
    return {"count": len(items), "coach": settings.coach_name, "datasets": items}


@router.post("/datasets", status_code=202)
def post_dataset(
    technique: str = Form(...),
    due_date: str = Form(...),
    note: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
    handedness: list[str] = Form(default=[]),
    camera_view: list[str] = Form(default=[]),
    existing_ids: list[str] = Form(default=[]),
    _admin: Session = Depends(require_admin),
) -> dict:
    """Create Dataset N: upload 5-10 videos (each with its own handedness and camera
    view; analysed in the background) and/or pick analyses that already exist."""
    if len(handedness) != len(files) or len(camera_view) != len(files):
        raise HTTPException(
            status_code=422, detail="Each uploaded video needs a handedness and a camera view."
        )
    try:
        batch, job = create_dataset(
            technique=normalize_stroke_type(technique).value,
            due_date=due_date,
            note=note,
            uploads=[
                (f.filename or "", f.file, hand, view)
                for f, hand, view in zip(files, handedness, camera_view)
            ],
            existing=[BatchClip(analysis_id=aid) for aid in existing_ids if aid],
        )
    except (DatasetError, UploadError, UnsupportedStrokeError, InvalidCaptureContextError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if job is not None:
        submit_job(job["job_id"])
    return {
        "dataset": dataset_summary(batch),
        "job": job_view(job) if job is not None else None,
    }


@router.get("/analyses")
def get_pickable_analyses(
    technique: str = Query(...), _admin: Session = Depends(require_admin)
) -> dict:
    """Analyses of this technique the admin can add to a dataset without uploading again."""
    try:
        items = pickable_analyses(normalize_stroke_type(technique).value)
    except (DatasetError, UnsupportedStrokeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(items), "analyses": items}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _admin: Session = Depends(require_admin)) -> dict:
    """Upload job progress, clip by clip."""
    try:
        return job_view(JobStore().get(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    """The dataset, its videos with the coach's label status, and upload progress."""
    batch = _dataset(dataset_id)
    clips = clip_statuses(batch, settings.coach_name)
    summary = dataset_summary(batch, clips=clips)
    return {
        **summary,
        "clips": clips,
        "uploads": [job_view(job) for job in JobStore().for_batch(dataset_id)],
        # Older field names, still read by earlier screens.
        "total": len(clips),
        "coach": settings.coach_name,
    }


@router.patch("/datasets/{dataset_id}")
def patch_dataset(
    dataset_id: str, body: DatasetUpdateIn, _admin: Session = Depends(require_admin)
) -> dict:
    _dataset(dataset_id)
    try:
        batch = update_dataset(dataset_id, due_date=body.due_date, note=body.note)
    except DatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return dataset_summary(batch)


@router.get("/datasets/{dataset_id}/export", response_model=None)
def get_dataset_export(
    dataset_id: str,
    format: Literal["csv", "json"] = Query(default="csv"),
    coach: str | None = Query(default=None),
    _admin: Session = Depends(require_admin),
) -> Response | dict:
    """One row per video per question (per coach who labelled it), as CSV or JSON."""
    try:
        export = export_batch(dataset_id, coach=coach)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if format == "json":
        return export
    return Response(
        content=rows_to_csv(export["rows"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{dataset_id}_labels.csv"'},
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
def get_clip_label(
    analysis_id: str,
    coach: str | None = Query(default=None),
    session: Session = Depends(require_signed_in),
) -> dict:
    """The coach sees their own label; the admin can read any coach's (default: the coach)."""
    is_coach = isinstance(session, Session) and session.role == ROLE_COACH
    if is_coach or not coach:
        coach = settings.coach_name
    clip = _clip(analysis_id)
    try:
        label = LabelStore().get(analysis_id, coach)
    except LabelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"label": normalize_label(label, clip), "status": _status(label, clip)}


@router.put("/clips/{analysis_id}/label")
def put_clip_label(
    analysis_id: str, body: ClipLabelIn, _coach: Session = Depends(require_coach)
) -> dict:
    """Only the coach labels; the label is saved under the coach's fixed name."""
    clip = _clip(analysis_id)
    try:
        label = LabelStore().save(
            analysis_id,
            {**body.model_dump(exclude={"batch_id"}), "coach": settings.coach_name},
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
