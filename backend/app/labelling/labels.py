"""Coach labels (reviews) for one clip: one row per coach per clip in the
labelling database, with each stat's rating and comment as its own row.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, delete, insert, select, update

from app.labelling import db
from app.labelling.batches import is_safe_id
from app.labelling.db import get_engine, iso, parse_ts, utcnow

# 2.0.0: most_important_fix and general_comment.
LABEL_FORMAT_VERSION = "2.0.0"
FIX_NOT_LISTED = "not_listed"
RATING_GOOD = "good"
RATING_NEEDS_WORK = "needs_work"
RATING_LOOKS_WRONG = "looks_wrong"
RATING_CANT_SEE = "cant_see"
RATINGS = (RATING_GOOD, RATING_NEEDS_WORK, RATING_LOOKS_WRONG, RATING_CANT_SEE)
MAX_COMMENT_CHARS = 1000
MAX_FEEDBACK_CHARS = 4000
MAX_GENERAL_COMMENT_CHARS = 4000

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"


class LabelError(ValueError):
    """A label that cannot be saved; the message is user-facing."""


def coach_slug(coach: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", " ".join(coach.split()).casefold()).strip("-")


class LabelStore:
    def __init__(self, output_dir: Path | None = None, engine: Engine | None = None) -> None:
        del output_dir  # labels live in the database; kept for a uniform store signature
        self.engine = engine or get_engine()

    @staticmethod
    def _key(analysis_id: str, coach: str) -> str:
        slug = coach_slug(coach)
        if not slug:
            raise LabelError("Add your name before labelling.")
        if not is_safe_id(analysis_id):
            raise LabelError(f"Invalid analysis id {analysis_id!r}")
        return slug

    def get(self, analysis_id: str, coach: str) -> dict[str, Any] | None:
        key = self._key(analysis_id, coach)
        with self.engine.connect() as conn:
            row = conn.execute(
                select(db.labels).where(
                    db.labels.c.analysis_id == analysis_id, db.labels.c.coach_key == key
                )
            ).first()
            return _label(conn, row) if row is not None else None

    def for_clip(self, analysis_id: str) -> list[dict[str, Any]]:
        if not is_safe_id(analysis_id):
            return []
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(db.labels)
                .where(db.labels.c.analysis_id == analysis_id)
                .order_by(db.labels.c.coach_key)
            ).all()
            return [_label(conn, row) for row in rows]

    def save(
        self,
        analysis_id: str,
        body: dict[str, Any],
        *,
        allowed_ratings: dict[str, set[str]],
        system_contact_frame: int | None,
        frame_count: int | None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate and save. allowed_ratings maps each question id to the ratings it
        accepts; answers stored under other (older) ids are kept as they were."""
        coach = " ".join(str(body.get("coach") or "").split())
        self._key(analysis_id, coach)
        stats = _stats(body.get("stats") or {}, allowed_ratings)
        previous = self.get(analysis_id, coach)
        for stat_id, entry in ((previous or {}).get("stats") or {}).items():
            if stat_id not in allowed_ratings:
                stats.setdefault(stat_id, entry)
        label = {
            "label_format_version": LABEL_FORMAT_VERSION,
            "analysis_id": analysis_id,
            "batch_id": batch_id,
            "coach": coach,
            "system_contact_frame": system_contact_frame,
            "corrected_hit_frame": _hit_frame(
                body.get("corrected_hit_frame"), system_contact_frame, frame_count
            ),
            "stats": stats,
            "overall_rating": _overall(body.get("overall_rating")),
            "most_important_fix": _fix(body.get("most_important_fix"), allowed_ratings),
            "feedback": _text(body.get("feedback"), MAX_FEEDBACK_CHARS, "Feedback"),
            "general_comment": _text(
                body.get("general_comment"), MAX_GENERAL_COMMENT_CHARS, "General comment"
            ),
        }
        return self.write(label)

    def write(self, label: dict[str, Any]) -> dict[str, Any]:
        """Insert or replace a complete label; keeps the original created_at."""
        key = self._key(label["analysis_id"], label["coach"])
        with self.engine.begin() as conn:
            if label.get("batch_id") and conn.execute(
                select(db.batches.c.batch_id).where(db.batches.c.batch_id == label["batch_id"])
            ).first() is None:
                label["batch_id"] = None
            existing = conn.execute(
                select(db.labels.c.label_id, db.labels.c.created_at).where(
                    db.labels.c.analysis_id == label["analysis_id"],
                    db.labels.c.coach_key == key,
                )
            ).first()
            now = utcnow()
            values = {
                "coach": label["coach"],
                "batch_id": label.get("batch_id"),
                "system_contact_frame": label.get("system_contact_frame"),
                "corrected_hit_frame": label.get("corrected_hit_frame"),
                "overall_rating": label.get("overall_rating"),
                "feedback": label.get("feedback") or "",
                "most_important_fix": label.get("most_important_fix"),
                "general_comment": label.get("general_comment") or "",
                "label_format_version": label.get("label_format_version") or LABEL_FORMAT_VERSION,
                "updated_at": parse_ts(label["updated_at"]) if label.get("updated_at") else now,
            }
            if existing is None:
                created = parse_ts(label["created_at"]) if label.get("created_at") else now
                label_id = conn.execute(
                    insert(db.labels)
                    .values(analysis_id=label["analysis_id"], coach_key=key, created_at=created, **values)
                    .returning(db.labels.c.label_id)
                ).scalar_one()
            else:
                label_id = existing.label_id
                conn.execute(update(db.labels).where(db.labels.c.label_id == label_id).values(**values))
                conn.execute(delete(db.stat_labels).where(db.stat_labels.c.label_id == label_id))
            stats = label.get("stats") or {}
            if stats:
                conn.execute(
                    insert(db.stat_labels),
                    [
                        {
                            "label_id": label_id,
                            "stat_id": stat_id,
                            "rating": entry.get("rating"),
                            "comment": entry.get("comment") or "",
                        }
                        for stat_id, entry in stats.items()
                    ],
                )
            row = conn.execute(select(db.labels).where(db.labels.c.label_id == label_id)).one()
            return _label(conn, row)


def _label(conn: Connection, row: Any) -> dict[str, Any]:
    stats = conn.execute(
        select(db.stat_labels)
        .where(db.stat_labels.c.label_id == row.label_id)
        .order_by(db.stat_labels.c.stat_id)
    ).all()
    return {
        "label_format_version": row.label_format_version,
        "analysis_id": row.analysis_id,
        "batch_id": row.batch_id,
        "coach": row.coach,
        "system_contact_frame": row.system_contact_frame,
        "corrected_hit_frame": row.corrected_hit_frame,
        "stats": {s.stat_id: {"rating": s.rating, "comment": s.comment} for s in stats},
        "overall_rating": row.overall_rating,
        "most_important_fix": row.most_important_fix,
        "feedback": row.feedback,
        "general_comment": row.general_comment,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def _hit_frame(value: Any, system: int | None, frame_count: int | None) -> int | None:
    if value is None:
        return None
    frame = int(value)
    if frame < 0 or (frame_count is not None and frame >= frame_count):
        raise LabelError(f"Hit frame {frame} is outside this clip.")
    # Same as the system's frame means the system was right.
    return None if frame == system else frame


def _stats(
    stats: dict[str, Any], allowed_ratings: dict[str, set[str]]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for stat_id, entry in stats.items():
        if stat_id not in allowed_ratings:
            raise LabelError(f"Unknown question {stat_id!r}.")
        rating = (entry or {}).get("rating")
        allowed = allowed_ratings[stat_id]
        if rating is not None and rating not in allowed:
            raise LabelError(
                f"{rating!r} is not an answer for {stat_id!r}; expected one of "
                f"{', '.join(sorted(allowed))}."
            )
        out[stat_id] = {
            "rating": rating,
            "comment": _text((entry or {}).get("comment"), MAX_COMMENT_CHARS, "Comment"),
        }
    return out


def _fix(value: Any, questions: dict[str, Any]) -> str | None:
    if value in (None, ""):
        return None
    fix = str(value)
    if fix != FIX_NOT_LISTED and fix not in questions:
        raise LabelError(f"Unknown 'most important thing to fix' {fix!r}.")
    return fix


def _overall(value: Any) -> int | None:
    if value is None:
        return None
    rating = int(value)
    if not 1 <= rating <= 5:
        raise LabelError("Overall rating must be 1 to 5.")
    return rating


def _text(value: Any, limit: int, what: str) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise LabelError(f"{what} is too long (max {limit} characters).")
    return text


def label_status(label: dict[str, Any] | None, available_stat_ids: list[str]) -> str:
    """Done = overall rating given and every answerable question rated (pass labels
    through clips.normalize_stats first so older stat ids count)."""
    if label is None:
        return STATUS_NOT_STARTED
    stats = label.get("stats") or {}
    rated = all((stats.get(s) or {}).get("rating") for s in available_stat_ids)
    if label.get("overall_rating") is not None and rated:
        return STATUS_DONE
    return STATUS_IN_PROGRESS
