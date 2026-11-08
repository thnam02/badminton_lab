"""Coach labels for one clip, one JSON file per coach per clip.

Stored at outputs/labelling/labels/{analysis_id}/{coach-slug}.json.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.labelling.batches import is_safe_id, labelling_dir

LABEL_FORMAT_VERSION = "1.0.0"
RATING_GOOD = "good"
RATING_NEEDS_WORK = "needs_work"
RATING_LOOKS_WRONG = "looks_wrong"
RATINGS = (RATING_GOOD, RATING_NEEDS_WORK, RATING_LOOKS_WRONG)
MAX_COMMENT_CHARS = 1000
MAX_FEEDBACK_CHARS = 4000

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"

_LOCK = threading.Lock()


class LabelError(ValueError):
    """A label that cannot be saved; the message is user-facing."""


def coach_slug(coach: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", " ".join(coach.split()).casefold()).strip("-")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LabelStore:
    def __init__(self, output_dir: Path | None = None) -> None:
        self.root = labelling_dir(output_dir) / "labels"

    def _path(self, analysis_id: str, coach: str) -> Path:
        slug = coach_slug(coach)
        if not slug:
            raise LabelError("Add your name before labelling.")
        if not is_safe_id(analysis_id):
            raise LabelError(f"Invalid analysis id {analysis_id!r}")
        return self.root / analysis_id / f"{slug}.json"

    def get(self, analysis_id: str, coach: str) -> dict[str, Any] | None:
        path = self._path(analysis_id, coach)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def for_clip(self, analysis_id: str) -> list[dict[str, Any]]:
        folder = self.root / analysis_id
        if not is_safe_id(analysis_id) or not folder.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]

    def save(
        self,
        analysis_id: str,
        body: dict[str, Any],
        *,
        stat_ids: set[str],
        system_contact_frame: int | None,
        frame_count: int | None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        coach = " ".join(str(body.get("coach") or "").split())
        path = self._path(analysis_id, coach)
        label = {
            "label_format_version": LABEL_FORMAT_VERSION,
            "analysis_id": analysis_id,
            "batch_id": batch_id,
            "coach": coach,
            "system_contact_frame": system_contact_frame,
            "corrected_hit_frame": _hit_frame(
                body.get("corrected_hit_frame"), system_contact_frame, frame_count
            ),
            "stats": _stats(body.get("stats") or {}, stat_ids),
            "overall_rating": _overall(body.get("overall_rating")),
            "feedback": _text(body.get("feedback"), MAX_FEEDBACK_CHARS, "Feedback"),
        }
        with _LOCK:
            previous = (
                json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
            )
            now = _now()
            label["created_at"] = (previous or {}).get("created_at") or now
            label["updated_at"] = now
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(label, indent=2), encoding="utf-8")
            tmp.replace(path)
        return label


def _hit_frame(value: Any, system: int | None, frame_count: int | None) -> int | None:
    if value is None:
        return None
    frame = int(value)
    if frame < 0 or (frame_count is not None and frame >= frame_count):
        raise LabelError(f"Hit frame {frame} is outside this clip.")
    # Same as the system's frame means the system was right.
    return None if frame == system else frame


def _stats(stats: dict[str, Any], stat_ids: set[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for stat_id, entry in stats.items():
        if stat_id not in stat_ids:
            raise LabelError(f"Unknown stat {stat_id!r}.")
        rating = (entry or {}).get("rating")
        if rating is not None and rating not in RATINGS:
            raise LabelError(f"Unknown rating {rating!r}; expected one of {', '.join(RATINGS)}.")
        out[stat_id] = {
            "rating": rating,
            "comment": _text((entry or {}).get("comment"), MAX_COMMENT_CHARS, "Comment"),
        }
    return out


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
    """Done = overall rating given and every measured stat rated."""
    if label is None:
        return STATUS_NOT_STARTED
    stats = label.get("stats") or {}
    rated = all((stats.get(s) or {}).get("rating") for s in available_stat_ids)
    if label.get("overall_rating") is not None and rated:
        return STATUS_DONE
    return STATUS_IN_PROGRESS
