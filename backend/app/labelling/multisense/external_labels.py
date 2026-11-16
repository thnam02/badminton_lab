"""Hidden MultiSense labels stored with a clip for admin export only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.labelling.multisense import SOURCE_NAME
from app.labelling.multisense.cut import ClipMeta

HIDDEN_FIELDS = (
    "skill_level",
    "hitting_position",
    "sound",
    "ball_landing",
    "ball_landing_horizontal",
    "ball_landing_vertical",
    "participant_id",
    "stroke_num",
    "swing_time",
    "source_file",
)


def meta_path(analysis_id: str, output_dir: Path | None = None) -> Path:
    root = Path(output_dir or settings.output_dir)
    return root / f"{analysis_id}_multisense.json"


def save_external_labels(analysis_id: str, clip: ClipMeta, output_dir: Path | None = None) -> Path:
    path = meta_path(analysis_id, output_dir)
    payload = {
        "source": SOURCE_NAME,
        "clip_id": clip.clip_id,
        **{k: getattr(clip, k) for k in HIDDEN_FIELDS},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_external_labels(analysis_id: str, output_dir: Path | None = None) -> dict[str, Any] | None:
    path = meta_path(analysis_id, output_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def coach_safe_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip MultiSense ground-truth fields before anything reaches the coach API."""
    blocked = set(HIDDEN_FIELDS) | {"source", "clip_id", "multisense", "external_labels"}
    return {k: v for k, v in payload.items() if k not in blocked}
