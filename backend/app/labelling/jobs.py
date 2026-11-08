"""Batch upload jobs: clips uploaded from the website, analysed in the background.

The batch is created as soon as the clips are uploaded; each clip is added to
it once its analysis finishes. Clips run one at a time on a single worker
because each analysis is heavy.
"""

from __future__ import annotations

import re
import shutil
import threading
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import Engine, delete, insert, select, update

from app.labelling import db
from app.labelling.batches import Batch, BatchClip, BatchStore, is_safe_id, labelling_dir, new_batch_id
from app.labelling.db import get_engine, iso, parse_ts, utcnow
from app.labelling.cli import VIDEO_SUFFIXES, Analyzer, analyze_clip

JOB_FORMAT_VERSION = "1.0.0"
CLIP_QUEUED = "queued"
CLIP_PROCESSING = "processing"
CLIP_DONE = "done"
CLIP_FAILED = "failed"
JOB_RUNNING = "running"
JOB_DONE = "done"
# Server restarted before the job finished; its remaining clips never ran.
JOB_INTERRUPTED = "interrupted"

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labelling-batch")
_active: set[str] = set()
_lock = threading.Lock()


class UploadError(ValueError):
    """An upload that cannot start; the message is user-facing."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_error(exc: Exception) -> str:
    """Failure reason for the page, without server folder paths."""
    message = str(getattr(exc, "detail", None) or exc)
    return re.sub(r"(?:[A-Za-z]:)?[/\\]\S*[/\\]", "", message)


def _safe_filename(name: str) -> str:
    base = Path(name or "clip").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base) or "clip"


class JobStore:
    """Upload jobs in the labelling database; staged clips wait on disk until analysed."""

    def __init__(self, output_dir: Path | None = None, engine: Engine | None = None) -> None:
        self.output_dir = output_dir
        self.root = labelling_dir(output_dir) / "jobs"
        self.engine = engine or get_engine()

    def staging_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def get(self, job_id: str) -> dict[str, Any]:
        if not is_safe_id(job_id):
            raise FileNotFoundError(f"Upload job '{job_id}' not found")
        with self.engine.connect() as conn:
            row = conn.execute(select(db.upload_jobs).where(db.upload_jobs.c.job_id == job_id)).first()
            if row is None:
                raise FileNotFoundError(f"Upload job '{job_id}' not found")
            clips = conn.execute(
                select(db.upload_job_clips)
                .where(db.upload_job_clips.c.job_id == job_id)
                .order_by(db.upload_job_clips.c.position)
            ).all()
        return {
            "job_format_version": row.job_format_version,
            "job_id": row.job_id,
            "batch_id": row.batch_id,
            "batch_name": row.batch_name,
            "stroke_type": row.stroke_type,
            "handedness": row.handedness,
            "camera_view": row.camera_view,
            "status": row.status,
            "created_at": iso(row.created_at),
            "updated_at": iso(row.updated_at),
            "clips": [
                {
                    "source_file": c.source_file,
                    "staged_file": c.staged_file,
                    "status": c.status,
                    "analysis_id": c.analysis_id,
                    "error": c.error,
                }
                for c in clips
            ],
        }

    def save(self, job: dict[str, Any]) -> None:
        """Create or replace the job and its clip progress."""
        now = utcnow()
        job["updated_at"] = iso(now)
        values = {
            "batch_id": job["batch_id"],
            "batch_name": job["batch_name"],
            "stroke_type": job["stroke_type"],
            "handedness": job["handedness"],
            "camera_view": job["camera_view"],
            "status": job["status"],
            "job_format_version": job.get("job_format_version") or JOB_FORMAT_VERSION,
            "updated_at": now,
        }
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(db.upload_jobs.c.job_id).where(db.upload_jobs.c.job_id == job["job_id"])
            ).first()
            if exists:
                conn.execute(
                    update(db.upload_jobs).where(db.upload_jobs.c.job_id == job["job_id"]).values(**values)
                )
            else:
                conn.execute(
                    insert(db.upload_jobs).values(
                        job_id=job["job_id"], created_at=parse_ts(job.get("created_at")), **values
                    )
                )
            conn.execute(delete(db.upload_job_clips).where(db.upload_job_clips.c.job_id == job["job_id"]))
            conn.execute(
                insert(db.upload_job_clips),
                [
                    {
                        "job_id": job["job_id"],
                        "position": i,
                        "source_file": c["source_file"],
                        "staged_file": c["staged_file"],
                        "status": c["status"],
                        "analysis_id": c.get("analysis_id"),
                        "error": c.get("error"),
                    }
                    for i, c in enumerate(job["clips"], start=1)
                ],
            )


def create_upload_job(
    files: Iterable[tuple[str, BinaryIO]],
    *,
    name: str,
    stroke: str,
    handedness: str,
    camera_view: str,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Stage the uploaded clips, create the (empty) batch and the job record."""
    name = " ".join(name.split())
    if not name:
        raise UploadError("Give the batch a name.")
    files = list(files)
    if not files:
        raise UploadError("Choose at least one clip.")
    for filename, _ in files:
        if Path(filename or "").suffix.lower() not in VIDEO_SUFFIXES:
            raise UploadError(f"'{filename}' is not an .mp4 or .mov video.")

    jobs = JobStore(output_dir)
    job_id = uuid.uuid4().hex[:12]
    staging = jobs.staging_dir(job_id)
    staging.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, (filename, fh) in enumerate(files):
        staged = staging / f"{i:03d}_{_safe_filename(filename)}"
        with staged.open("wb") as out:
            shutil.copyfileobj(fh, out)
        clips.append(
            {
                "source_file": Path(filename).name,
                "staged_file": staged.name,
                "status": CLIP_QUEUED,
                "analysis_id": None,
                "error": None,
            }
        )

    batch = Batch(batch_id=new_batch_id(name), name=name)
    BatchStore(output_dir).save(batch)
    job = {
        "job_format_version": JOB_FORMAT_VERSION,
        "job_id": job_id,
        "batch_id": batch.batch_id,
        "batch_name": name,
        "stroke_type": stroke,
        "handedness": handedness,
        "camera_view": camera_view,
        "status": JOB_RUNNING,
        "created_at": _now(),
        "clips": clips,
    }
    jobs.save(job)
    return job


def run_job(
    job_id: str, *, output_dir: Path | None = None, analyzer: Analyzer = analyze_clip
) -> dict[str, Any]:
    jobs = JobStore(output_dir)
    batches = BatchStore(output_dir)
    job = jobs.get(job_id)
    staging = jobs.staging_dir(job_id)
    for clip in job["clips"]:
        if clip["status"] != CLIP_QUEUED:
            continue
        clip["status"] = CLIP_PROCESSING
        jobs.save(job)
        path = staging / clip["staged_file"]
        try:
            analysis_id = analyzer(path, job["stroke_type"], job["handedness"], job["camera_view"])
            raw = batches.keep_raw_video(path, analysis_id)
            batches.add_clip(
                job["batch_id"],
                BatchClip(analysis_id=analysis_id, source_file=clip["source_file"], raw_video=raw),
            )
            clip.update(status=CLIP_DONE, analysis_id=analysis_id)
        except Exception as exc:  # noqa: BLE001 — one bad clip must not stop the batch
            clip.update(status=CLIP_FAILED, error=_public_error(exc))
        finally:
            path.unlink(missing_ok=True)
        jobs.save(job)
    job["status"] = JOB_DONE
    jobs.save(job)
    shutil.rmtree(staging, ignore_errors=True)
    return job


def submit_job(job_id: str, *, output_dir: Path | None = None) -> None:
    with _lock:
        _active.add(job_id)

    def work() -> None:
        try:
            run_job(job_id, output_dir=output_dir)
        finally:
            with _lock:
                _active.discard(job_id)

    _executor.submit(work)


def job_view(job: dict[str, Any]) -> dict[str, Any]:
    """Job with progress counts; a running job no worker knows about was interrupted."""
    with _lock:
        active = job["job_id"] in _active
    status = job["status"]
    if status == JOB_RUNNING and not active:
        status = JOB_INTERRUPTED
    counts = {s: sum(1 for c in job["clips"] if c["status"] == s) for s in (CLIP_QUEUED, CLIP_PROCESSING, CLIP_DONE, CLIP_FAILED)}
    return {
        **job,
        "status": status,
        "total": len(job["clips"]),
        "done_count": counts[CLIP_DONE],
        "failed_count": counts[CLIP_FAILED],
        "remaining_count": counts[CLIP_QUEUED] + counts[CLIP_PROCESSING],
    }
