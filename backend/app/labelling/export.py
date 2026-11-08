"""Batch export: one row per clip per stat (per coach who labelled the clip)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.labelling.batches import BatchStore
from app.labelling.clips import clip_view
from app.labelling.labels import LabelStore, coach_slug, label_status

EXPORT_FORMAT_VERSION = "1.0.0"

COLUMNS = (
    "batch_id",
    "clip_position",
    "analysis_id",
    "source_file",
    "stroke_type",
    "coach",
    "label_status",
    "system_contact_frame",
    "corrected_hit_frame",
    "hit_frame_used",
    "stat_id",
    "stat_name",
    "measured_when",
    # Measured by the system at its own contact frame, not the corrected one.
    "system_value",
    "unit",
    "rating",
    "comment",
    "overall_rating",
    "feedback",
    "label_format_version",
    "label_updated_at",
)


def export_batch(
    batch_id: str, *, coach: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    batch = BatchStore(output_dir).get(batch_id)
    labels = LabelStore(output_dir)
    wanted = coach_slug(coach) if coach and coach.strip() else None
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for position, entry in enumerate(batch.clips, start=1):
        try:
            clip = clip_view(entry.analysis_id, output_dir)
        except FileNotFoundError:
            missing.append(entry.analysis_id)
            continue
        available = [s["id"] for s in clip["stats"] if s["available"]]
        clip_labels = [
            lb
            for lb in labels.for_clip(entry.analysis_id)
            if wanted is None or coach_slug(lb.get("coach", "")) == wanted
        ]
        system = clip["system_contact_frame"]
        for label in clip_labels or [None]:
            lb = label or {}
            corrected = lb.get("corrected_hit_frame")
            for stat in clip["stats"]:
                stat_label = (lb.get("stats") or {}).get(stat["id"]) or {}
                rows.append(
                    {
                        "batch_id": batch.batch_id,
                        "clip_position": position,
                        "analysis_id": entry.analysis_id,
                        "source_file": entry.source_file,
                        "stroke_type": clip["stroke_type"],
                        "coach": lb.get("coach", ""),
                        "label_status": label_status(label, available),
                        "system_contact_frame": system,
                        "corrected_hit_frame": corrected,
                        "hit_frame_used": corrected if corrected is not None else system,
                        "stat_id": stat["id"],
                        "stat_name": stat["name"],
                        "measured_when": stat["when"],
                        "system_value": stat["value"],
                        "unit": stat["unit"],
                        "rating": stat_label.get("rating"),
                        "comment": stat_label.get("comment", ""),
                        "overall_rating": lb.get("overall_rating"),
                        "feedback": lb.get("feedback", ""),
                        "label_format_version": lb.get("label_format_version"),
                        "label_updated_at": lb.get("updated_at"),
                    }
                )
    return {
        "export_format_version": EXPORT_FORMAT_VERSION,
        "batch_id": batch.batch_id,
        "name": batch.name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "coach": coach,
        "columns": list(COLUMNS),
        "missing_clips": missing,
        "rows": rows,
    }


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in COLUMNS})
    return buf.getvalue()
