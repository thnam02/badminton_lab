"""Labelling batches: named lists of already-processed analysis ids."""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, delete, func, insert, select, update

from app.config import settings
from app.labelling import db
from app.labelling.db import get_engine, iso, parse_ts, utcnow

BATCH_FORMAT_VERSION = "1.0.0"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def labelling_dir(output_dir: Path | None = None) -> Path:
    return Path(output_dir or settings.output_dir) / "labelling"


def is_safe_id(value: str) -> bool:
    return bool(_SAFE_ID.match(value or ""))


def _require_safe(value: str, what: str) -> str:
    if not is_safe_id(value):
        raise ValueError(f"Invalid {what} {value!r}")
    return value


@dataclass(slots=True)
class BatchClip:
    analysis_id: str
    source_file: str = ""
    # Original clip kept next to the batch, relative to the outputs folder.
    raw_video: str | None = None


@dataclass(slots=True)
class Batch:
    """A labelling dataset: Dataset {number} of one technique (stroke type)."""

    batch_id: str
    name: str
    clips: list[BatchClip] = field(default_factory=list)
    created_at: str = ""
    batch_format_version: str = BATCH_FORMAT_VERSION
    technique: str | None = None
    number: int | None = None
    # ISO date (YYYY-MM-DD); labelling stays allowed after it.
    due_date: str | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Batch:
        return cls(
            batch_id=str(d["batch_id"]),
            name=str(d.get("name") or d["batch_id"]),
            clips=[
                BatchClip(
                    analysis_id=str(c["analysis_id"]),
                    source_file=str(c.get("source_file") or ""),
                    raw_video=c.get("raw_video"),
                )
                for c in d.get("clips") or []
            ],
            created_at=str(d.get("created_at") or ""),
            batch_format_version=str(d.get("batch_format_version") or BATCH_FORMAT_VERSION),
            technique=d.get("technique"),
            number=d.get("number"),
            due_date=d.get("due_date"),
            note=str(d.get("note") or ""),
        )


def new_batch_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:40] or "batch"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


class BatchStore:
    """Batches in the labelling database; kept videos stay on disk under outputs/."""

    def __init__(self, output_dir: Path | None = None, engine: Engine | None = None) -> None:
        self.output_dir = output_dir
        self.root = labelling_dir(output_dir)
        self.videos_dir = self.root / "videos"
        self.engine = engine or get_engine()

    def get(self, batch_id: str) -> Batch:
        _require_safe(batch_id, "batch id")
        with self.engine.connect() as conn:
            row = conn.execute(select(db.batches).where(db.batches.c.batch_id == batch_id)).first()
            if row is None:
                raise FileNotFoundError(f"Batch '{batch_id}' not found")
            return _batch(conn, row)

    def list(self) -> list[Batch]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(db.batches).order_by(db.batches.c.created_at.desc())
            ).all()
            return [_batch(conn, row) for row in rows]

    def save(self, batch: Batch) -> None:
        """Create or replace the batch and its clip list."""
        _require_safe(batch.batch_id, "batch id")
        for clip in batch.clips:
            _require_safe(clip.analysis_id, "analysis id")
        created = parse_ts(batch.created_at or None)
        batch.created_at = iso(created) or ""
        with self.engine.begin() as conn:
            exists = conn.execute(
                select(db.batches.c.batch_id).where(db.batches.c.batch_id == batch.batch_id)
            ).first()
            values = {
                "name": batch.name,
                "batch_format_version": batch.batch_format_version,
                "created_at": created,
                "technique": batch.technique,
                "number": batch.number,
                "due_date": date.fromisoformat(batch.due_date) if batch.due_date else None,
                "note": batch.note or "",
            }
            if exists:
                conn.execute(
                    update(db.batches).where(db.batches.c.batch_id == batch.batch_id).values(**values)
                )
            else:
                conn.execute(insert(db.batches).values(batch_id=batch.batch_id, **values))
            conn.execute(delete(db.batch_clips).where(db.batch_clips.c.batch_id == batch.batch_id))
            if batch.clips:
                conn.execute(
                    insert(db.batch_clips),
                    [
                        {
                            "batch_id": batch.batch_id,
                            "position": i,
                            "analysis_id": c.analysis_id,
                            "source_file": c.source_file,
                            "raw_video": c.raw_video,
                        }
                        for i, c in enumerate(batch.clips, start=1)
                    ],
                )

    def add_clip(self, batch_id: str, clip: BatchClip) -> None:
        """Append one clip; safe while other clips are being added."""
        _require_safe(clip.analysis_id, "analysis id")
        with self.engine.begin() as conn:
            last = conn.execute(
                select(func.max(db.batch_clips.c.position)).where(
                    db.batch_clips.c.batch_id == batch_id
                )
            ).scalar()
            conn.execute(
                insert(db.batch_clips).values(
                    batch_id=batch_id,
                    position=(last or 0) + 1,
                    analysis_id=clip.analysis_id,
                    source_file=clip.source_file,
                    raw_video=clip.raw_video,
                )
            )

    def keep_raw_video(self, source: Path, analysis_id: str) -> str:
        """Copy the original clip under outputs/ and record it; returns its relative path."""
        _require_safe(analysis_id, "analysis id")
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        dest = self.videos_dir / f"{analysis_id}{source.suffix.lower()}"
        shutil.copy2(source, dest)
        rel = dest.relative_to(self.root.parent).as_posix()
        self.register_video(dest, rel, analysis_id=analysis_id, original_filename=source.name)
        return rel

    def register_video(
        self, path: Path, rel: str, *, analysis_id: str, original_filename: str, kind: str = "raw"
    ) -> None:
        values = {
            "analysis_id": analysis_id,
            "kind": kind,
            "original_filename": original_filename,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        with self.engine.begin() as conn:
            found = conn.execute(select(db.videos.c.video_id).where(db.videos.c.path == rel)).first()
            if found:
                conn.execute(update(db.videos).where(db.videos.c.path == rel).values(**values))
            else:
                conn.execute(insert(db.videos).values(path=rel, created_at=utcnow(), **values))


def _batch(conn: Connection, row: Any) -> Batch:
    clips = conn.execute(
        select(db.batch_clips)
        .where(db.batch_clips.c.batch_id == row.batch_id)
        .order_by(db.batch_clips.c.position)
    ).all()
    return Batch(
        batch_id=row.batch_id,
        name=row.name,
        clips=[
            BatchClip(analysis_id=c.analysis_id, source_file=c.source_file, raw_video=c.raw_video)
            for c in clips
        ],
        created_at=iso(row.created_at) or "",
        batch_format_version=row.batch_format_version,
        technique=row.technique,
        number=row.number,
        due_date=row.due_date.isoformat() if row.due_date else None,
        note=row.note or "",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
