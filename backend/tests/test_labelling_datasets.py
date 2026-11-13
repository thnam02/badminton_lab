"""Labelling datasets: size limits, numbering, status (including overdue), coach order,
due-date edits and the migration of older batches."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from alembic import command
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.config import settings
from app.labelling.batches import Batch, BatchClip, BatchStore
from app.labelling.database_setup import alembic_config
from app.labelling.datasets import (
    DatasetError,
    coach_sort_key,
    create_dataset,
    dataset_status,
    dataset_summary,
    days_left,
    list_datasets,
    update_dataset,
)
from app.labelling.labels import LabelStore
from app.routes import labelling as routes
from tests.test_labelling_clips import _all_answers, seed_analysis

TODAY = date(2026, 11, 10)


@pytest.fixture
def outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    return tmp_path


def _seed(root: Path, n: int, stroke: str = "FOREHAND_CLEAR", prefix: str = "a") -> list[BatchClip]:
    ids = [f"{prefix}{i}" for i in range(n)]
    for analysis_id in ids:
        seed_analysis(root, analysis_id, stroke=stroke)
    return [BatchClip(analysis_id=a, source_file=f"{a}.mp4") for a in ids]


def _create(clips: list[BatchClip], technique: str = "FOREHAND_CLEAR", due: str = "2026-11-20", **kw):
    batch, _job = create_dataset(technique=technique, due_date=due, existing=clips, today=TODAY, **kw)
    return batch


# Status


@pytest.mark.parametrize(
    ("videos", "labelled", "started", "due", "expected"),
    [
        (5, 0, 0, date(2026, 11, 20), "not_started"),
        (5, 0, 1, date(2026, 11, 20), "in_progress"),
        (5, 2, 2, date(2026, 11, 20), "in_progress"),
        (5, 5, 5, date(2026, 11, 20), "done"),
        (5, 0, 0, None, "not_started"),
        (5, 4, 5, date(2026, 11, 10), "in_progress"),  # due today is not overdue yet
        (5, 4, 5, date(2026, 11, 9), "overdue"),
        (5, 0, 0, date(2026, 11, 9), "overdue"),
        (5, 5, 5, date(2026, 11, 1), "done"),  # finished late is still done
        (0, 0, 0, None, "not_started"),
    ],
)
def test_status(videos: int, labelled: int, started: int, due: date | None, expected: str) -> None:
    assert dataset_status(videos, labelled, started, due, TODAY) == expected


def test_days_left() -> None:
    assert days_left(date(2026, 11, 20), TODAY) == 10
    assert days_left(date(2026, 11, 10), TODAY) == 0
    assert days_left(date(2026, 11, 7), TODAY) == -3
    assert days_left(None, TODAY) is None


def test_summary_counts_the_coachs_labels_and_turns_overdue(outputs: Path) -> None:
    batch = _create(_seed(outputs, 5), due="2026-11-12")
    routes.put_clip_label(
        "a0", routes.ClipLabelIn(stats=_all_answers(routes.get_clip("a0")), overall_rating=4)
    )
    routes.put_clip_label("a1", routes.ClipLabelIn(overall_rating=2))
    # Labels from anyone other than the coach don't count towards progress.
    LabelStore().write({"analysis_id": "a2", "coach": "Minh", "overall_rating": 4, "stats": {}})

    summary = dataset_summary(batch, today=TODAY)
    assert (summary["video_count"], summary["labelled_count"], summary["status"]) == (5, 1, "in_progress")
    assert summary["days_left"] == 2
    late = dataset_summary(batch, today=date(2026, 11, 13))
    assert (late["status"], late["days_left"]) == ("overdue", -1)


# Creating datasets


def test_datasets_are_numbered_per_technique(outputs: Path) -> None:
    clears = _seed(outputs, 10)
    smashes = _seed(outputs, 5, stroke="FOREHAND_SMASH", prefix="s")
    first = _create(clears[:5])
    smash = _create(smashes, technique="FOREHAND_SMASH")
    second = _create(clears[5:], note="  Club players  ")
    assert (first.number, smash.number, second.number) == (1, 1, 2)
    assert second.name == "Forehand clear · Dataset 2"
    assert smash.name == "Forehand smash · Dataset 1"
    assert (second.due_date, second.note) == ("2026-11-20", "Club players")
    assert second.created_at


@pytest.mark.parametrize("n", [0, 4, 11])
def test_a_dataset_needs_5_to_10_videos(outputs: Path, n: int) -> None:
    with pytest.raises(DatasetError, match=f"needs 5 to 10 videos; you chose {n}"):
        _create(_seed(outputs, n))
    assert BatchStore().list() == []


@pytest.mark.parametrize("n", [5, 10])
def test_5_and_10_videos_are_allowed(outputs: Path, n: int) -> None:
    assert len(_create(_seed(outputs, n)).clips) == n


def test_uploads_and_existing_videos_count_together(outputs: Path) -> None:
    import io

    uploads = [(f"u{i}.mp4", io.BytesIO(b"x"), "right", "side") for i in range(2)]
    batch, job = create_dataset(
        technique="FOREHAND_CLEAR",
        due_date="2026-11-20",
        uploads=uploads,
        existing=_seed(outputs, 3),
        today=TODAY,
    )
    assert len(batch.clips) == 3
    assert job is not None and job["batch_id"] == batch.batch_id
    assert [(c["handedness"], c["camera_view"]) for c in job["clips"]] == [("RIGHT", "SIDE")] * 2
    with pytest.raises(DatasetError, match="you chose 11"):
        create_dataset(
            technique="FOREHAND_CLEAR",
            due_date="2026-11-20",
            uploads=[(f"u{i}.mp4", io.BytesIO(b"x"), "RIGHT", "SIDE") for i in range(6)],
            existing=_seed(outputs, 5, prefix="b"),
            today=TODAY,
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"technique": "BACKHAND_DROP"}, "Unknown technique"),
        ({"due": ""}, "Choose a due date"),
        ({"due": "2026-11-09"}, "in the past"),
        ({"due": "20 Nov"}, "not a date"),
    ],
)
def test_bad_dataset_details_are_refused(outputs: Path, kwargs: dict, message: str) -> None:
    with pytest.raises(DatasetError, match=message):
        _create(_seed(outputs, 5), **kwargs)


def test_picked_videos_must_exist_match_the_technique_and_be_distinct(outputs: Path) -> None:
    clips = _seed(outputs, 4)
    smash = _seed(outputs, 1, stroke="FOREHAND_SMASH", prefix="s")
    with pytest.raises(DatasetError, match="s0 is a forehand smash, not a forehand clear"):
        _create(clips + smash)
    with pytest.raises(DatasetError, match="missing was not found"):
        _create(clips + [BatchClip("missing")])
    with pytest.raises(DatasetError, match="picked twice"):
        _create(clips + clips[:1])
    assert BatchStore().list() == []


def test_admin_can_move_the_due_date_and_change_the_note(outputs: Path) -> None:
    batch = _create(_seed(outputs, 5))
    updated = update_dataset(batch.batch_id, due_date="2026-12-01", note="Take your time", today=TODAY)
    assert (updated.due_date, updated.note) == ("2026-12-01", "Take your time")
    assert update_dataset(batch.batch_id, note="", today=TODAY).due_date == "2026-12-01"
    with pytest.raises(DatasetError, match="in the past"):
        update_dataset(batch.batch_id, due_date="2026-11-01", today=TODAY)


def test_patch_route(outputs: Path) -> None:
    batch = _create(_seed(outputs, 5))
    later = (date.today() + timedelta(days=30)).isoformat()
    result = routes.patch_dataset(batch.batch_id, routes.DatasetUpdateIn(due_date=later))
    assert result["due_date"] == later
    for dataset_id, body, status in (
        ("nope", routes.DatasetUpdateIn(note="x"), 404),
        (batch.batch_id, routes.DatasetUpdateIn(due_date="2001-01-01"), 422),
    ):
        with pytest.raises(HTTPException) as exc:
            routes.patch_dataset(dataset_id, body)
        assert exc.value.status_code == status


# Coach order


def _summary(number: int, status: str, due: str | None) -> dict:
    return {"number": number, "status": status, "due_date": due}


def test_coach_sees_overdue_first_then_nearest_due_date() -> None:
    summaries = [
        _summary(1, "done", "2026-11-01"),
        _summary(2, "in_progress", "2026-11-25"),
        _summary(3, "not_started", None),
        _summary(4, "overdue", "2026-11-05"),
        _summary(5, "not_started", "2026-11-12"),
        _summary(6, "overdue", "2026-11-08"),
        _summary(7, "done", None),
    ]
    ordered = [s["number"] for s in sorted(summaries, key=coach_sort_key)]
    assert ordered == [4, 6, 5, 2, 3, 1, 7]


def test_dataset_list_is_in_coach_order(outputs: Path) -> None:
    today = date.today()
    clips = _seed(outputs, 10)
    later, _ = create_dataset(
        technique="FOREHAND_CLEAR", due_date=today + timedelta(days=9), existing=clips[:5]
    )
    sooner, _ = create_dataset(
        technique="FOREHAND_CLEAR", due_date=today + timedelta(days=2), existing=clips[5:]
    )
    BatchStore().save(Batch(batch_id="old", name="Old set", technique="FOREHAND_CLEAR", number=3))
    assert [d["dataset_id"] for d in list_datasets()] == [sooner.batch_id, later.batch_id, "old"]


# Older batches


def test_migration_turns_old_batches_into_numbered_datasets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    seed_analysis(tmp_path, "c1")
    seed_analysis(tmp_path, "c2")
    seed_analysis(tmp_path, "s1", stroke="FOREHAND_SMASH")
    url = f"sqlite:///{tmp_path / 'old.db'}"
    command.upgrade(alembic_config(url), "0003")
    engine = create_engine(url)
    with engine.begin() as conn:
        for batch_id, name, created in (
            ("first", "Nam", "2026-09-01 10:00:00"),
            ("smash", "Smashes", "2026-09-02 10:00:00"),
            ("by-job", "For Jeff", "2026-09-03 10:00:00"),
            ("second", "Later clears", "2026-09-04 10:00:00"),
        ):
            conn.execute(
                text(
                    "INSERT INTO labelling_batches (batch_id, name, batch_format_version, created_at) "
                    "VALUES (:id, :name, '1.0.0', :created)"
                ),
                {"id": batch_id, "name": name, "created": created},
            )
        for batch_id, position, analysis_id in (
            ("first", 1, "c1"),
            ("first", 2, "gone"),
            ("smash", 1, "s1"),
            ("second", 1, "c2"),
        ):
            conn.execute(
                text(
                    "INSERT INTO labelling_batch_clips (batch_id, position, analysis_id, source_file) "
                    "VALUES (:b, :p, :a, '')"
                ),
                {"b": batch_id, "p": position, "a": analysis_id},
            )
        conn.execute(
            text(
                "INSERT INTO labelling_upload_jobs (job_id, batch_id, batch_name, stroke_type, "
                "handedness, camera_view, status, job_format_version, created_at, updated_at) "
                "VALUES ('j1', 'by-job', 'For Jeff', 'FOREHAND_SMASH', 'RIGHT', 'SIDE', 'done', "
                "'1.0.0', '2026-09-03 10:00:00', '2026-09-03 10:00:00')"
            )
        )

    command.upgrade(alembic_config(url), "head")

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT batch_id, name, technique, number, due_date, note FROM labelling_batches")
        ).all()
    assert sorted(tuple(r) for r in rows) == [
        ("by-job", "For Jeff", "FOREHAND_SMASH", 2, None, ""),
        ("first", "Nam", "FOREHAND_CLEAR", 1, None, ""),
        ("second", "Later clears", "FOREHAND_CLEAR", 2, None, ""),
        ("smash", "Smashes", "FOREHAND_SMASH", 1, None, ""),
    ]
    store = BatchStore(engine=engine)
    old = store.get("first")
    assert ([c.analysis_id for c in old.clips], old.due_date) == (["c1", "gone"], None)
    assert dataset_summary(old, today=TODAY)["status"] == "not_started"
    command.downgrade(alembic_config(url), "0003")
    engine.dispose()


def test_admin_can_pick_analysed_videos_of_the_technique(outputs: Path) -> None:
    clears = _seed(outputs, 5)
    _seed(outputs, 1, stroke="FOREHAND_SMASH", prefix="s")
    _create(clears[:5])
    picked = routes.get_pickable_analyses(technique="forehand_clear")["analyses"]
    assert sorted(a["analysis_id"] for a in picked) == [c.analysis_id for c in clears]
    assert {tuple(a["datasets"]) for a in picked} == {("Dataset 1",)}
    assert (picked[0]["handedness"], picked[0]["camera_view"]) == ("RIGHT", "SIDE")
    smashes = routes.get_pickable_analyses(technique="FOREHAND_SMASH")["analyses"]
    assert [(a["analysis_id"], a["datasets"]) for a in smashes] == [("s0", [])]
    with pytest.raises(HTTPException) as exc:
        routes.get_pickable_analyses(technique="backhand_drop")
    assert exc.value.status_code == 422
