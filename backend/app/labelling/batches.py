"""Labelling batches: named lists of already-processed analysis ids."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

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
    batch_id: str
    name: str
    clips: list[BatchClip] = field(default_factory=list)
    created_at: str = ""
    batch_format_version: str = BATCH_FORMAT_VERSION

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
        )


def new_batch_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:40] or "batch"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


class BatchStore:
    def __init__(self, output_dir: Path | None = None) -> None:
        self.root = labelling_dir(output_dir)
        self.batches_dir = self.root / "batches"
        self.videos_dir = self.root / "videos"

    def path_for(self, batch_id: str) -> Path:
        return self.batches_dir / f"{_require_safe(batch_id, 'batch id')}.json"

    def get(self, batch_id: str) -> Batch:
        path = self.path_for(batch_id)
        if not path.is_file():
            raise FileNotFoundError(f"Batch '{batch_id}' not found")
        return Batch.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[Batch]:
        if not self.batches_dir.is_dir():
            return []
        batches = [
            Batch.from_dict(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self.batches_dir.glob("*.json"))
        ]
        return sorted(batches, key=lambda b: b.created_at, reverse=True)

    def save(self, batch: Batch) -> Path:
        for clip in batch.clips:
            _require_safe(clip.analysis_id, "analysis id")
        if not batch.created_at:
            batch.created_at = datetime.now(timezone.utc).isoformat()
        path = self.path_for(batch.batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(batch.to_dict(), indent=2), encoding="utf-8")
        return path

    def keep_raw_video(self, source: Path, analysis_id: str) -> str:
        """Copy the original clip next to the batch; returns a path under outputs/."""
        _require_safe(analysis_id, "analysis id")
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        dest = self.videos_dir / f"{analysis_id}{source.suffix.lower()}"
        shutil.copy2(source, dest)
        return dest.relative_to(self.root.parent).as_posix()
