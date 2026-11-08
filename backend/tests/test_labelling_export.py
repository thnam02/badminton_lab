"""Batch export as CSV and JSON: one row per clip per stat."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.config import settings
from app.labelling.batches import Batch, BatchClip, BatchStore
from app.labelling.clips import load_stats_config
from app.labelling.export import COLUMNS
from app.routes import labelling as routes
from tests.test_labelling_clips import CONTACT, seed_analysis

N_STATS = len(load_stats_config()["stats"])


@pytest.fixture
def batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    seed_analysis(tmp_path, "a1")
    seed_analysis(tmp_path, "a2")
    BatchStore().save(
        Batch(
            batch_id="set-1",
            name="Set 1",
            clips=[BatchClip("a1", "one.mp4"), BatchClip("a2", "two.mp4"), BatchClip("gone")],
        )
    )
    routes.put_clip_label(
        "a1",
        routes.ClipLabelIn(
            coach="Linh",
            corrected_hit_frame=22,
            stats={
                "contact_elbow_angle": routes.StatLabelIn(
                    rating="needs_work", comment='bent, "a lot"\nreach up'
                )
            },
            overall_rating=3,
            feedback="Reach higher.",
        ),
    )
    routes.put_clip_label("a1", routes.ClipLabelIn(coach="Minh", overall_rating=4))
    return "set-1"


def test_json_export_has_one_row_per_clip_per_stat(batch: str) -> None:
    export = routes.get_batch_export(batch, format="json", coach=None)
    assert export["export_format_version"] == "1.0.0"
    assert export["columns"] == list(COLUMNS)
    assert export["missing_clips"] == ["gone"]
    rows = export["rows"]
    # a1: two coaches × stats; a2: unlabelled, still one row per stat.
    assert len(rows) == 3 * N_STATS
    assert {(r["analysis_id"], r["coach"]) for r in rows} == {
        ("a1", "Linh"),
        ("a1", "Minh"),
        ("a2", ""),
    }
    elbow = next(
        r for r in rows if r["coach"] == "Linh" and r["stat_id"] == "contact_elbow_angle"
    )
    assert elbow["rating"] == "needs_work"
    assert elbow["system_value"] == 150.0
    assert elbow["unit"] == "deg"
    assert elbow["measured_when"] == "At the hit"
    assert (elbow["system_contact_frame"], elbow["corrected_hit_frame"], elbow["hit_frame_used"]) == (
        CONTACT,
        22,
        22,
    )
    assert elbow["label_status"] == "in_progress"
    unlabelled = [r for r in rows if r["analysis_id"] == "a2"]
    assert all(r["rating"] is None and r["label_status"] == "not_started" for r in unlabelled)
    assert unlabelled[0]["hit_frame_used"] == CONTACT


def test_export_can_be_limited_to_one_coach(batch: str) -> None:
    rows = routes.get_batch_export(batch, format="json", coach="linh")["rows"]
    assert {r["coach"] for r in rows if r["analysis_id"] == "a1"} == {"Linh"}


def test_csv_export_matches_json_and_quotes_free_text(batch: str) -> None:
    response = routes.get_batch_export(batch, format="csv", coach=None)
    assert response.media_type.startswith("text/csv")
    assert 'filename="set-1_labels.csv"' in response.headers["content-disposition"]
    parsed = list(csv.DictReader(io.StringIO(response.body.decode())))
    assert len(parsed) == 3 * N_STATS
    assert list(parsed[0]) == list(COLUMNS)
    elbow = next(
        r for r in parsed if r["coach"] == "Linh" and r["stat_id"] == "contact_elbow_angle"
    )
    assert elbow["comment"] == 'bent, "a lot"\nreach up'
    assert elbow["overall_rating"] == "3"
    unlabelled = next(r for r in parsed if r["analysis_id"] == "a2")
    assert unlabelled["rating"] == "" and unlabelled["coach"] == ""


def test_unknown_batch_export_is_not_found(batch: str) -> None:
    with pytest.raises(HTTPException) as exc:
        routes.get_batch_export("nope", format="csv", coach=None)
    assert exc.value.status_code == 404
