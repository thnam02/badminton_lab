"""Batch export: one row per clip per question (per coach who labelled the clip)."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.labelling.batches import BatchStore
from app.labelling.clips import (
    DEFAULT_QUESTION_SET,
    answerable_ids,
    clip_view,
    load_stats_config,
    normalize_label,
)
from app.labelling.labels import LabelStore, coach_slug, label_status

EXPORT_FORMAT_VERSION = "1.1.0"

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
    "moment",
    "question_kind",
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
    # Titles for answers saved under stat ids no current question replaces.
    retired = {
        q["id"]: q["title"] for q in load_stats_config()["question_sets"][DEFAULT_QUESTION_SET]
    }
    for position, entry in enumerate(batch.clips, start=1):
        try:
            clip = clip_view(entry.analysis_id, output_dir)
        except FileNotFoundError:
            missing.append(entry.analysis_id)
            continue
        required = answerable_ids(clip)
        question_ids = {q["id"] for q in clip["questions"]}
        clip_labels = [
            lb
            for lb in labels.for_clip(entry.analysis_id)
            if wanted is None or coach_slug(lb.get("coach", "")) == wanted
        ]
        system = clip["system_contact_frame"]
        for label in clip_labels or [None]:
            lb = normalize_label(label, clip) or {}
            answers = lb.get("stats") or {}
            corrected = lb.get("corrected_hit_frame")
            base = {
                "batch_id": batch.batch_id,
                "clip_position": position,
                "analysis_id": entry.analysis_id,
                "source_file": entry.source_file,
                "stroke_type": clip["stroke_type"],
                "coach": lb.get("coach", ""),
                "label_status": label_status(lb if label is not None else None, required),
                "system_contact_frame": system,
                "corrected_hit_frame": corrected,
                "hit_frame_used": corrected if corrected is not None else system,
                "overall_rating": lb.get("overall_rating"),
                "feedback": lb.get("feedback", ""),
                "label_format_version": lb.get("label_format_version"),
                "label_updated_at": lb.get("updated_at"),
            }
            for q in clip["questions"]:
                answer = answers.get(q["id"]) or {}
                rows.append(
                    {
                        **base,
                        "stat_id": q["id"],
                        "stat_name": q["title"],
                        "moment": q["moment"],
                        "question_kind": q["kind"],
                        "measured_when": (q["measured_at"] or {}).get("label", ""),
                        "system_value": q["value"],
                        "unit": q["unit"],
                        "rating": answer.get("rating"),
                        "comment": answer.get("comment", ""),
                    }
                )
            for stat_id, answer in answers.items():
                if stat_id in question_ids:
                    continue
                rows.append(
                    {
                        **base,
                        "stat_id": stat_id,
                        "stat_name": retired.get(stat_id, stat_id),
                        "moment": "",
                        "question_kind": "retired",
                        "measured_when": "",
                        "system_value": None,
                        "unit": None,
                        "rating": answer.get("rating"),
                        "comment": answer.get("comment", ""),
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
