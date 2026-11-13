"""Labelling datasets: numbered sets of 5-10 videos of one technique for the coach.

A dataset is stored as a labelling batch with a technique, a number per
technique ("Dataset 1, 2, 3..."), an optional due date and an admin note.
Its status is computed, never stored.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import Connection, func, select, update

from app.config import settings
from app.labelling import db
from app.labelling.batches import Batch, BatchClip, BatchStore, new_batch_id
from app.labelling.clips import ClipArtifacts, answerable_ids, clip_view, normalize_label
from app.labelling.jobs import (
    CLIP_PROCESSING,
    CLIP_QUEUED,
    JOB_RUNNING,
    JobStore,
    check_video_names,
    create_upload_job,
    job_view,
)
from app.labelling.labels import STATUS_DONE, STATUS_NOT_STARTED, LabelStore, label_status
from app.processing.capture_context import normalize_camera_view, normalize_handedness
from app.schemas.stroke_types import stroke_type_label

TECHNIQUES = ("FOREHAND_CLEAR", "FOREHAND_SMASH")
MIN_VIDEOS = 5
MAX_VIDEOS = 10
# Used when an old batch's clips and upload job say nothing about the stroke.
FALLBACK_TECHNIQUE = "FOREHAND_CLEAR"

STATUS_IN_PROGRESS = "in_progress"
STATUS_OVERDUE = "overdue"


class DatasetError(ValueError):
    """A dataset that cannot be created or changed; the message is user-facing."""


def dataset_status(
    video_count: int,
    labelled_count: int,
    started_count: int,
    due_date: date | None,
    today: date,
) -> str:
    """not_started / in_progress / done, or overdue once the due date has passed
    (the due day itself still counts) and it isn't done."""
    if video_count > 0 and labelled_count >= video_count:
        return STATUS_DONE
    if due_date is not None and today > due_date:
        return STATUS_OVERDUE
    if labelled_count > 0 or started_count > 0:
        return STATUS_IN_PROGRESS
    return STATUS_NOT_STARTED


def days_left(due_date: date | None, today: date) -> int | None:
    return (due_date - today).days if due_date is not None else None


def coach_sort_key(summary: dict[str, Any]) -> tuple:
    """Overdue first, then nearest due date (no date last), finished datasets at the end."""
    due = summary.get("due_date")
    return (
        summary["status"] != STATUS_OVERDUE,
        summary["status"] == STATUS_DONE,
        due is None,
        due or "",
        summary.get("number") or 0,
    )


def technique_label(technique: str | None) -> str:
    """"Forehand clear", as the coach screens write it."""
    return stroke_type_label(technique).capitalize() if technique else ""


def dataset_title(number: int | None) -> str:
    return f"Dataset {number}" if number is not None else "Dataset"


def clip_statuses(batch: Batch, coach: str) -> list[dict[str, Any]]:
    """Each video's label status for this coach."""
    store = LabelStore()
    out = []
    for position, entry in enumerate(batch.clips, start=1):
        base = {
            "position": position,
            "analysis_id": entry.analysis_id,
            "source_file": entry.source_file,
        }
        try:
            clip = clip_view(entry.analysis_id)
        except FileNotFoundError:
            out.append({**base, "missing": True, "status": STATUS_NOT_STARTED, "labelled": False})
            continue
        label = store.get(entry.analysis_id, coach)
        status = label_status(normalize_label(label, clip), answerable_ids(clip))
        out.append(
            {
                **base,
                "stroke_type": clip["stroke_type"],
                "handedness": clip["handedness"],
                "camera_view": clip["camera_view"],
                "missing": False,
                "status": status,
                "labelled": status == STATUS_DONE,
            }
        )
    return out


def _pending_uploads(batch_id: str) -> list[dict[str, Any]]:
    """Uploaded videos still waiting for or going through analysis."""
    pending = []
    for job in JobStore().for_batch(batch_id):
        view = job_view(job)
        if view["status"] != JOB_RUNNING:
            continue
        pending += [c for c in view["clips"] if c["status"] in (CLIP_QUEUED, CLIP_PROCESSING)]
    return pending


def dataset_summary(
    batch: Batch,
    *,
    coach: str | None = None,
    today: date | None = None,
    clips: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    coach = coach or settings.coach_name
    clips = clips if clips is not None else clip_statuses(batch, coach)
    pending = len(_pending_uploads(batch.batch_id))
    labelled = sum(1 for c in clips if c["labelled"])
    started = sum(1 for c in clips if c["status"] != STATUS_NOT_STARTED)
    due = date.fromisoformat(batch.due_date) if batch.due_date else None
    video_count = len(batch.clips) + pending
    return {
        "dataset_id": batch.batch_id,
        "technique": batch.technique,
        "technique_label": technique_label(batch.technique),
        "number": batch.number,
        "title": dataset_title(batch.number),
        "note": batch.note,
        "created_at": batch.created_at,
        "due_date": batch.due_date,
        "days_left": days_left(due, today),
        "video_count": video_count,
        "processing_count": pending,
        "labelled_count": labelled,
        "status": dataset_status(video_count, labelled, started, due, today),
        # Older field names, still read by earlier screens.
        "batch_id": batch.batch_id,
        "name": batch.name,
        "clip_count": len(batch.clips),
    }


def list_datasets(*, coach: str | None = None, today: date | None = None) -> list[dict[str, Any]]:
    summaries = [dataset_summary(b, coach=coach, today=today) for b in BatchStore().list()]
    return sorted(summaries, key=coach_sort_key)


def _next_number(conn: Connection, technique: str) -> int:
    current = conn.execute(
        select(func.max(db.batches.c.number)).where(db.batches.c.technique == technique)
    ).scalar()
    return (current or 0) + 1


def _parse_due(value: str | date | None, today: date) -> date:
    if not value:
        raise DatasetError("Choose a due date.")
    try:
        due = value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError as exc:
        raise DatasetError(f"'{value}' is not a date (use YYYY-MM-DD).") from exc
    if due < today:
        raise DatasetError("The due date can't be in the past.")
    return due


def create_dataset(
    *,
    technique: str,
    due_date: str | date | None,
    note: str = "",
    uploads: Iterable[tuple[str, BinaryIO, str, str]] = (),
    existing: Iterable[BatchClip] = (),
    output_dir: Path | None = None,
    today: date | None = None,
) -> tuple[Batch, dict[str, Any] | None]:
    """Create Dataset N for this technique from uploaded clips (filename, file,
    handedness, camera view; analysed in the background) and/or analyses that
    already exist. Returns the dataset and the upload job, if any."""
    today = today or date.today()
    if technique not in TECHNIQUES:
        raise DatasetError(f"Unknown technique {technique!r}.")
    uploads = [
        (name, fh, normalize_handedness(hand), normalize_camera_view(view))
        for name, fh, hand, view in uploads
    ]
    existing = list(existing)
    total = len(uploads) + len(existing)
    if not MIN_VIDEOS <= total <= MAX_VIDEOS:
        raise DatasetError(
            f"A dataset needs {MIN_VIDEOS} to {MAX_VIDEOS} videos; you chose {total}."
        )
    due = _parse_due(due_date, today)
    check_video_names(name for name, _fh, _hand, _view in uploads)
    ids = [c.analysis_id for c in existing]
    if len(set(ids)) != len(ids):
        raise DatasetError("The same video was picked twice.")
    label = technique_label(technique).lower()
    for clip in existing:
        try:
            stroke = ClipArtifacts(clip.analysis_id, output_dir).stroke_type()
        except FileNotFoundError as exc:
            raise DatasetError(f"Video {clip.analysis_id} was not found.") from exc
        if stroke != technique:
            raise DatasetError(
                f"Video {clip.analysis_id} is a {technique_label(stroke).lower()}, not a {label}."
            )

    store = BatchStore(output_dir)
    with store.engine.connect() as conn:
        number = _next_number(conn, technique)
    name = f"{technique_label(technique)} · {dataset_title(number)}"
    batch = Batch(
        batch_id=new_batch_id(f"{technique}-{number}"),
        name=name,
        clips=existing,
        technique=technique,
        number=number,
        due_date=due.isoformat(),
        note=(note or "").strip(),
    )
    store.save(batch)
    job = (
        create_upload_job(
            uploads, batch_id=batch.batch_id, batch_name=name, stroke=technique, output_dir=output_dir
        )
        if uploads
        else None
    )
    return store.get(batch.batch_id), job


def update_dataset(
    dataset_id: str,
    *,
    due_date: str | None = None,
    note: str | None = None,
    today: date | None = None,
) -> Batch:
    store = BatchStore()
    batch = store.get(dataset_id)
    if due_date is not None:
        batch.due_date = _parse_due(due_date, today or date.today()).isoformat()
    if note is not None:
        batch.note = note.strip()
    store.save(batch)
    return store.get(dataset_id)


def pickable_analyses(
    technique: str, *, output_dir: Path | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    """Saved analyses of this technique, newest first, with the datasets already using them."""
    from app.services.analysis_aggregator import list_analyses

    if technique not in TECHNIQUES:
        raise DatasetError(f"Unknown technique {technique!r}.")
    used: dict[str, list[str]] = {}
    for batch in BatchStore(output_dir).list():
        for clip in batch.clips:
            used.setdefault(clip.analysis_id, []).append(
                dataset_title(batch.number) if batch.number else batch.name
            )
    out = []
    for item in list_analyses(output_dir=output_dir, limit=limit):
        analysis_id = item["analysis_id"]
        try:
            art = ClipArtifacts(analysis_id, output_dir)
        except FileNotFoundError:
            continue
        if art.stroke_type() != technique:
            continue
        out.append(
            {
                "analysis_id": analysis_id,
                "created_at": item.get("created_at"),
                "handedness": art.evidence.get("handedness") or item.get("handedness"),
                "camera_view": art.evidence.get("camera_view") or item.get("camera_view"),
                "datasets": used.get(analysis_id, []),
            }
        )
    return out


def backfill_datasets(conn: Connection, output_dir: Path | None = None) -> int:
    """Give older batches a technique (from their clips, else their upload job) and
    a number per technique in creation order; due dates stay empty."""
    rows = conn.execute(
        select(db.batches.c.batch_id, db.batches.c.technique, db.batches.c.number)
        .order_by(db.batches.c.created_at, db.batches.c.batch_id)
    ).all()
    changed = 0
    for row in rows:
        technique = row.technique or _technique_of(conn, row.batch_id, output_dir)
        number = row.number or _next_number(conn, technique)
        if (technique, number) != (row.technique, row.number):
            conn.execute(
                update(db.batches)
                .where(db.batches.c.batch_id == row.batch_id)
                .values(technique=technique, number=number)
            )
            changed += 1
    return changed


def _technique_of(conn: Connection, batch_id: str, output_dir: Path | None) -> str:
    ids = conn.execute(
        select(db.batch_clips.c.analysis_id).where(db.batch_clips.c.batch_id == batch_id)
    ).scalars().all()
    votes: Counter[str] = Counter()
    for aid in ids:
        try:
            art = ClipArtifacts(aid, output_dir)
        except FileNotFoundError:
            continue
        stroke = art.evidence.get("stroke_type") or art.metrics.get("stroke_type")
        if stroke in TECHNIQUES:
            votes[stroke] += 1
    if votes:
        return votes.most_common(1)[0][0]
    job_stroke = conn.execute(
        select(db.upload_jobs.c.stroke_type).where(db.upload_jobs.c.batch_id == batch_id)
    ).scalars().first()
    return job_stroke if job_stroke in TECHNIQUES else FALLBACK_TECHNIQUE
