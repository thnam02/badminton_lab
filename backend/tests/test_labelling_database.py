"""Labelling database: migrations, constraints, video records and file import."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, func, inspect, insert, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.labelling import db
from app.labelling.batches import Batch, BatchClip, BatchStore
from app.labelling.database_setup import alembic_config, import_files, upgrade_database
from app.labelling.jobs import JobStore
from app.labelling.labels import LabelStore
from app.main import database_unavailable


def _columns(engine) -> dict[str, set[str]]:
    insp = inspect(engine)
    return {
        t: {c["name"] for c in insp.get_columns(t)}
        for t in insp.get_table_names()
        if t.startswith("labelling_")
    }


def test_migrations_build_the_same_schema_as_the_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    upgrade_database(url)
    migrated = create_engine(url)
    models = create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    db.metadata.create_all(models)
    assert _columns(migrated) == _columns(models)
    assert len(_columns(migrated)) == 7
    command.downgrade(alembic_config(url), "base")
    assert _columns(migrated) == {}


def test_database_rejects_invalid_ratings(labelling_database) -> None:
    store = LabelStore()
    label = store.write(
        {"analysis_id": "a1", "coach": "Linh", "overall_rating": 3, "stats": {}}
    )
    with labelling_database.begin() as conn:
        label_id = conn.execute(select(db.labels.c.label_id)).scalar_one()
        with pytest.raises(IntegrityError):
            conn.execute(
                insert(db.stat_labels).values(label_id=label_id, stat_id="x", rating="great", comment="")
            )
    assert label["overall_rating"] == 3


def test_each_stat_comment_is_its_own_row(labelling_database) -> None:
    LabelStore().write(
        {
            "analysis_id": "a1",
            "coach": "Linh",
            "stats": {
                "contact_elbow_angle": {"rating": "needs_work", "comment": "too bent"},
                "follow_through": {"rating": "good", "comment": ""},
            },
        }
    )
    with labelling_database.connect() as conn:
        rows = conn.execute(
            select(db.stat_labels.c.stat_id, db.stat_labels.c.rating, db.stat_labels.c.comment)
            .order_by(db.stat_labels.c.stat_id)
        ).all()
    assert [tuple(r) for r in rows] == [
        ("contact_elbow_angle", "needs_work", "too bent"),
        ("follow_through", "good", ""),
    ]


def test_kept_videos_are_recorded_with_size_and_checksum(tmp_path: Path, labelling_database) -> None:
    clip = tmp_path / "clip.MOV"
    clip.write_bytes(b"raw video bytes")
    rel = BatchStore(tmp_path / "outputs").keep_raw_video(clip, "a1")
    assert rel == "labelling/videos/a1.mov"
    with labelling_database.connect() as conn:
        row = conn.execute(select(db.videos)).one()
    assert (row.analysis_id, row.kind, row.path, row.original_filename) == ("a1", "raw", rel, "clip.MOV")
    assert row.size_bytes == len(b"raw video bytes")
    assert row.sha256 == hashlib.sha256(b"raw video bytes").hexdigest()


def test_clips_added_one_by_one_keep_their_order(tmp_path: Path) -> None:
    store = BatchStore(tmp_path)
    store.save(Batch(batch_id="b1", name="B1"))
    for aid in ("a1", "a2", "a3"):
        store.add_clip("b1", BatchClip(analysis_id=aid, source_file=f"{aid}.mp4"))
    assert [c.analysis_id for c in store.get("b1").clips] == ["a1", "a2", "a3"]


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_import_moves_json_files_into_the_database(tmp_path: Path, labelling_database) -> None:
    root = tmp_path / "labelling"
    _write(
        root / "batches/nam-75c169.json",
        {
            "batch_id": "nam-75c169",
            "name": "Nam",
            "created_at": "2026-11-08T10:20:00+00:00",
            "batch_format_version": "1.0.0",
            "clips": [{"analysis_id": "v1", "source_file": "clip.mp4", "raw_video": "labelling/videos/v1.mp4"}],
        },
    )
    _write(
        root / "labels/v1/linh.json",
        {
            "label_format_version": "1.0.0",
            "analysis_id": "v1",
            "batch_id": "nam-75c169",
            "coach": "Linh",
            "system_contact_frame": 48,
            "corrected_hit_frame": 50,
            "stats": {"contact_elbow_angle": {"rating": "good", "comment": "nice"}},
            "overall_rating": 4,
            "feedback": "Solid.",
            "created_at": "2026-11-08T10:30:00+00:00",
            "updated_at": "2026-11-08T10:31:00+00:00",
        },
    )
    _write(
        root / "jobs/ef54fb109c70.json",
        {
            "job_format_version": "1.0.0",
            "job_id": "ef54fb109c70",
            "batch_id": "nam-75c169",
            "batch_name": "Nam",
            "stroke_type": "FOREHAND_CLEAR",
            "handedness": "RIGHT",
            "camera_view": "SIDE",
            "status": "done",
            "created_at": "2026-11-08T10:20:00+00:00",
            "clips": [{"source_file": "clip.mp4", "staged_file": "000_clip.mp4", "status": "done", "analysis_id": "v1", "error": None}],
        },
    )
    (root / "videos").mkdir()
    (root / "videos/v1.mp4").write_bytes(b"v1 bytes")

    result = import_files(tmp_path)
    assert {k: result[k] for k in ("batches", "labels", "jobs", "videos", "skipped")} == {
        "batches": 1,
        "labels": 1,
        "jobs": 1,
        "videos": 1,
        "skipped": 0,
    }
    batch = BatchStore(tmp_path).get("nam-75c169")
    assert (batch.name, batch.created_at) == ("Nam", "2026-11-08T10:20:00+00:00")
    assert [(c.analysis_id, c.source_file, c.raw_video) for c in batch.clips] == [
        ("v1", "clip.mp4", "labelling/videos/v1.mp4")
    ]
    label = LabelStore().get("v1", "linh")
    assert label["corrected_hit_frame"] == 50
    assert label["stats"] == {"contact_elbow_angle": {"rating": "good", "comment": "nice"}}
    assert (label["created_at"], label["updated_at"]) == (
        "2026-11-08T10:30:00+00:00",
        "2026-11-08T10:31:00+00:00",
    )
    assert JobStore(tmp_path).get("ef54fb109c70")["clips"][0]["analysis_id"] == "v1"
    with labelling_database.connect() as conn:
        video = conn.execute(select(db.videos)).one()
    assert (video.path, video.original_filename) == ("labelling/videos/v1.mp4", "clip.mp4")

    backup = Path(result["backup"])
    assert (backup / "batches/nam-75c169.json").is_file()
    assert (backup / "labels/v1/linh.json").is_file()
    assert not (root / "batches").exists() and not (root / "labels").exists()
    assert (root / "videos/v1.mp4").is_file()

    again = import_files(tmp_path)
    assert (again["batches"], again["labels"], again["videos"], again["backup"]) == (0, 0, 0, None)
    with labelling_database.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.videos)).scalar() == 1


def test_missing_database_gives_a_clear_503() -> None:
    response = asyncio.run(database_unavailable(None, OperationalError("x", {}, Exception("down"))))
    assert response.status_code == 503
    assert b"init-db" in response.body


POSTGRES_URL = os.environ.get("LABELLING_TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="set LABELLING_TEST_POSTGRES_URL to run against Postgres")
def test_postgres_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Migrations and a review round trip on a real (throwaway) Postgres database."""
    from app.config import settings

    monkeypatch.setattr(settings, "database_url", POSTGRES_URL)
    upgrade_database(POSTGRES_URL)
    try:
        store = BatchStore(tmp_path)
        store.save(Batch(batch_id="pg-check", name="PG check", clips=[BatchClip("a1", "a.mp4")]))
        label = LabelStore().write(
            {
                "analysis_id": "a1",
                "coach": "Linh",
                "batch_id": "pg-check",
                "overall_rating": 5,
                "stats": {"follow_through": {"rating": "looks_wrong", "comment": "off"}},
            }
        )
        assert label["batch_id"] == "pg-check"
        assert store.get("pg-check").clips[0].analysis_id == "a1"
        assert label["created_at"].endswith("+00:00")
    finally:
        command.downgrade(alembic_config(POSTGRES_URL), "base")
