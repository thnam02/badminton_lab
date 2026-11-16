"""Filter analysed MultiSense clips using existing quality / swing signals only."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REASON_NO_SWING = "no_swing"
REASON_PLAYER_CUTOFF_OR_SMALL = "player_cutoff_or_small"
REASON_RACKET_ARM_HIDDEN = "racket_arm_not_visible"
REASON_WRONG_PERSON = "wrong_person"

_PLAYER_WARNINGS = frozenset({"SMALL_PLAYER_SIZE", "LOW_FULL_BODY_COVERAGE"})
_ARM_WARNINGS = frozenset({"LOW_RACKET_ARM_AT_CONTACT", "LOW_RACKET_ARM_VISIBILITY"})
_PERSON_WARNINGS = frozenset({"WRONG_PLAYER_POSSIBLE"})


@dataclass
class FilterResult:
    kept: list[str] = field(default_factory=list)
    dropped: dict[str, list[str]] = field(default_factory=dict)  # reason -> clip ids

    def counts(self) -> dict[str, int]:
        return {reason: len(ids) for reason, ids in sorted(self.dropped.items())}


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def analysis_artifacts(analysis_id: str, output_dir: Path) -> dict[str, Any]:
    """Collect quality + evidence + contact payloads for one analysis id."""
    root = Path(output_dir)
    quality = (
        _load_json(root / f"{analysis_id}_pose_video_quality.json")
        or _load_json(root / f"{analysis_id}_video_quality.json")
        or _load_json(root / analysis_id / "video_quality.json")
    )
    evidence = (
        _load_json(root / f"{analysis_id}_pose_evidence.json")
        or _load_json(root / f"{analysis_id}_evidence.json")
        or _load_json(root / analysis_id / "evidence.json")
    )
    contact = (
        _load_json(root / f"{analysis_id}_contact.json")
        or _load_json(root / analysis_id / "contact.json")
        or (evidence or {}).get("contact")
        or {}
    )
    return {"quality": quality or {}, "evidence": evidence or {}, "contact": contact or {}}


def drop_reason(artifacts: dict[str, Any]) -> str | None:
    """Return the first matching drop reason, or None to keep."""
    quality = artifacts.get("quality") or {}
    evidence = artifacts.get("evidence") or {}
    contact = artifacts.get("contact") or evidence.get("contact") or {}
    warnings = set(quality.get("warnings") or []) | set(
        evidence.get("measurement_warnings") or []
    ) | set(contact.get("warnings") or [])

    swing_count = evidence.get("swing_count")
    if swing_count is None:
        candidates = evidence.get("swing_candidates") or contact.get("swing_candidates") or []
        swing_count = len(candidates) if candidates else None
    if swing_count is None and contact.get("swing_count") is not None:
        swing_count = contact.get("swing_count")
    has_contact = contact.get("frame_index") is not None or contact.get("timestamp") is not None
    if swing_count == 0 or (not swing_count and not has_contact):
        return REASON_NO_SWING

    if warnings & _PERSON_WARNINGS:
        return REASON_WRONG_PERSON
    if warnings & _PLAYER_WARNINGS:
        return REASON_PLAYER_CUTOFF_OR_SMALL
    if warnings & _ARM_WARNINGS:
        return REASON_RACKET_ARM_HIDDEN

    metrics = (quality.get("metrics") or {}) if quality else {}
    # Mirror the same thresholds the pipeline already used to raise warnings,
    # in case older artifacts omitted the warning string.
    size = metrics.get("player_size_ratio")
    if size is not None and float(size) < 0.25:
        return REASON_PLAYER_CUTOFF_OR_SMALL
    coverage = metrics.get("full_body_coverage")
    if coverage is not None and float(coverage) < 0.60:
        return REASON_PLAYER_CUTOFF_OR_SMALL
    arm = metrics.get("racket_arm_visibility_at_contact")
    if arm is not None and float(arm) < 0.70:
        return REASON_RACKET_ARM_HIDDEN
    return None


def filter_analyses(
    analysis_ids: list[str],
    *,
    output_dir: Path,
) -> FilterResult:
    result = FilterResult()
    for aid in analysis_ids:
        reason = drop_reason(analysis_artifacts(aid, output_dir))
        if reason is None:
            result.kept.append(aid)
        else:
            result.dropped.setdefault(reason, []).append(aid)
    return result
