"""Every emitted warning code needs a user-facing sentence or an internal-only entry."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from app.services.pose_service import pose_service
from app.services.warning_messages import (
    INTERNAL_ONLY_WARNING_CODES,
    WARNING_SENTENCES,
    unmapped_warning_codes,
    warning_sentences,
)
from tests.test_capture_context import _load_fixture

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _emitted_codes(source: str) -> set[str]:
    """String literals the pipeline uses as warning codes: ``WARNING_* = "..."``
    constants, ``<...warnings>.append("...")`` and ``warnings=["..."]``."""
    codes: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str) and any(
                isinstance(t, ast.Name) and t.id.startswith("WARNING_") for t in node.targets
            ):
                codes.add(node.value.value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"append", "add"}
        ):
            target = node.func.value
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            if "warning" in name.lower():
                codes.update(
                    a.value
                    for a in node.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                )
        elif (
            isinstance(node, ast.keyword)
            and node.arg
            and "warning" in node.arg.lower()
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            codes.update(
                e.value
                for e in node.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            )
    return codes


def _all_emitted_codes() -> set[str]:
    codes: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        codes |= _emitted_codes(path.read_text(encoding="utf-8"))
    return codes


def test_scanner_finds_each_emission_form() -> None:
    source = (
        'WARNING_A = "CODE_A"\n'
        'warnings.append("CODE_B")\n'
        'report.warnings.append("CODE_C")\n'
        'Report(warnings=["CODE_D"])\n'
        'other.append("NOT_A_WARNING")\n'
    )
    assert _emitted_codes(source) == {"CODE_A", "CODE_B", "CODE_C", "CODE_D"}


def test_every_emitted_warning_code_is_mapped_or_internal_only() -> None:
    emitted = _all_emitted_codes()
    # Guard against the scanner silently going blind.
    assert {
        "LOW_FPS",
        "NO_POSE_DETECTED",
        "WRONG_PLAYER_POSSIBLE",
        "CONTACT_PEAK_NOT_OVERHEAD",
        "CONTACT_NOT_VERIFIED_BY_SHUTTLE",
    } <= emitted
    missing = unmapped_warning_codes(sorted(emitted))
    assert missing == [], (
        f"Warning codes without a user-facing sentence: {missing}. Add each to "
        "WARNING_SENTENCES or INTERNAL_ONLY_WARNING_CODES in "
        "app/services/warning_messages.py."
    )


def test_sentences_and_internal_only_do_not_overlap() -> None:
    assert not set(WARNING_SENTENCES) & INTERNAL_ONLY_WARNING_CODES
    assert all("_" not in s or "{" in s for s in WARNING_SENTENCES.values())


def test_internal_only_and_unknown_codes_are_never_shown() -> None:
    contact = {"swing_count": 2, "chosen_swing_timestamp": 4.5}
    assert warning_sentences(
        ["CONTACT_NOT_VERIFIED_BY_SHUTTLE", "SOME_FUTURE_CODE"], contact
    ) == []
    assert unmapped_warning_codes(
        ["CONTACT_NOT_VERIFIED_BY_SHUTTLE", "SOME_FUTURE_CODE", "SOME_FUTURE_CODE"]
    ) == ["SOME_FUTURE_CODE"]


def _kinematics(tmp_path):
    raw, meta = _load_fixture()
    return pose_service.kinematics_from_raw_pose(
        raw,
        input_path=tmp_path / "clip.mp4",
        output_path=tmp_path / "clip_pose.mp4",
        stroke_type="FOREHAND_CLEAR",
        handedness="RIGHT",
        video_fps=meta["fps"],
        video_width=meta["width"],
        video_height=meta["height"],
    )


def _unmapped_records(caplog) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == "app.services.warning_messages" and r.levelno == logging.WARNING
    ]


def test_unmapped_code_is_logged_once_per_analysis(tmp_path, caplog) -> None:
    kin = _kinematics(tmp_path)
    kin.quality_report.warnings.extend(["SOME_FUTURE_CODE", "ANOTHER_NEW_CODE"])
    with caplog.at_level(logging.WARNING, logger="app.services.warning_messages"):
        pose_service.build_final_state(kin)
    records = _unmapped_records(caplog)
    assert len(records) == 1
    assert "SOME_FUTURE_CODE" in records[0].getMessage()
    assert "ANOTHER_NEW_CODE" in records[0].getMessage()
    assert "clip_pose" in records[0].getMessage()


def test_mapped_codes_are_not_logged(tmp_path, caplog) -> None:
    kin = _kinematics(tmp_path)
    with caplog.at_level(logging.WARNING, logger="app.services.warning_messages"):
        state = pose_service.build_final_state(kin)
    assert state.video_quality.warnings
    assert _unmapped_records(caplog) == []
