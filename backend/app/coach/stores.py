"""File-backed stores for coach clip labels and coach draft rules."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

ANSWER_YES = "yes"
ANSWER_NO = "no"
ANSWER_CANT_TELL = "cant_tell"
ANSWERS = (ANSWER_YES, ANSWER_NO, ANSWER_CANT_TELL)

_LOCK = threading.Lock()


def coach_dir(output_dir: Path | None = None) -> Path:
    return Path(output_dir or settings.output_dir) / "coach"


def coach_key(name: str) -> str:
    return " ".join(str(name).split()).casefold()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _write_list(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2), encoding="utf-8")
    tmp.replace(path)


@dataclass(slots=True)
class ClipLabel:
    """One coach's review of one analysed clip."""

    coach: str
    analysis_id: str
    stroke_type: str
    # Coach-marked frame where the racket meets the shuttle (analysis video frames).
    hit_frame_index: int | None = None
    no_shuttle: bool = False
    answers: dict[str, str] = field(default_factory=dict)
    overall: int | None = None
    notes: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClipLabel:
        return cls(
            coach=str(d.get("coach") or ""),
            analysis_id=str(d.get("analysis_id") or ""),
            stroke_type=str(d.get("stroke_type") or ""),
            hit_frame_index=(
                int(d["hit_frame_index"]) if d.get("hit_frame_index") is not None else None
            ),
            no_shuttle=bool(d.get("no_shuttle", False)),
            answers={str(k): str(v) for k, v in (d.get("answers") or {}).items()},
            overall=int(d["overall"]) if d.get("overall") is not None else None,
            notes=str(d.get("notes") or ""),
            updated_at=str(d.get("updated_at") or ""),
        )


class ClipLabelStore:
    def __init__(self, output_dir: Path | None = None) -> None:
        self.path = coach_dir(output_dir) / "clip_labels.json"

    def all(self) -> list[ClipLabel]:
        return [ClipLabel.from_dict(d) for d in _read_list(self.path)]

    def for_coach(self, coach: str, stroke_type: str | None = None) -> list[ClipLabel]:
        key = coach_key(coach)
        return [
            label
            for label in self.all()
            if coach_key(label.coach) == key
            and (stroke_type is None or label.stroke_type == stroke_type)
        ]

    def upsert(self, label: ClipLabel) -> ClipLabel:
        for answer in label.answers.values():
            if answer not in ANSWERS:
                raise ValueError(f"Unknown answer {answer!r}; expected one of {ANSWERS}")
        label.updated_at = _now()
        with _LOCK:
            items = [
                d
                for d in _read_list(self.path)
                if not (
                    coach_key(d.get("coach", "")) == coach_key(label.coach)
                    and d.get("analysis_id") == label.analysis_id
                )
            ]
            items.append(label.to_dict())
            _write_list(self.path, items)
        return label


DRAFT_STATUS = "draft"


class RuleDraftStore:
    """Coach rules waiting for the dev team. Never read by live analysis."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.path = coach_dir(output_dir) / "rule_drafts.json"

    def all(self) -> list[dict[str, Any]]:
        return sorted(_read_list(self.path), key=lambda d: d.get("created_at", ""), reverse=True)

    def add(self, draft: dict[str, Any]) -> dict[str, Any]:
        record = {
            **draft,
            "id": uuid.uuid4().hex[:12],
            "status": DRAFT_STATUS,
            "promoted_rule_version": None,
            "created_at": _now(),
        }
        with _LOCK:
            items = _read_list(self.path)
            items.append(record)
            _write_list(self.path, items)
        return record
