"""Batch uploads from the website, analysed in the background."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.config import settings
from app.labelling import jobs as jobs_module
from app.labelling.batches import BatchStore
from app.labelling.jobs import (
    JobStore,
    UploadError,
    create_upload_job,
    job_view,
    run_job,
)
from app.routes import labelling as routes


def _files(*names: str) -> list[tuple[str, io.BytesIO]]:
    return [(n, io.BytesIO(f"video:{n}".encode())) for n in names]


def _job(tmp_path: Path, *names: str) -> dict:
    return create_upload_job(
        _files(*names),
        name=" Side-view   set 2 ",
        stroke="FOREHAND_CLEAR",
        handedness="RIGHT",
        camera_view="SIDE",
        output_dir=tmp_path,
    )


def test_upload_creates_the_batch_at_once_and_stages_clips(tmp_path: Path) -> None:
    job = _job(tmp_path, "a.mp4", "b one.MOV")
    batch = BatchStore(tmp_path).get(job["batch_id"])
    assert batch.name == "Side-view set 2"
    assert batch.clips == []
    assert [c["source_file"] for c in job["clips"]] == ["a.mp4", "b one.MOV"]
    assert all(c["status"] == "queued" for c in job["clips"])
    staged = sorted(p.name for p in JobStore(tmp_path).staging_dir(job["job_id"]).iterdir())
    assert staged == ["000_a.mp4", "001_b_one.MOV"]


@pytest.mark.parametrize(
    ("names", "name", "message"),
    [
        ((), "x", "at least one clip"),
        (("notes.txt",), "x", "not an .mp4 or .mov"),
        (("a.mp4",), "   ", "Give the batch a name"),
    ],
)
def test_bad_uploads_are_refused(tmp_path: Path, names: tuple, name: str, message: str) -> None:
    with pytest.raises(UploadError, match=message):
        create_upload_job(
            _files(*names),
            name=name,
            stroke="FOREHAND_CLEAR",
            handedness="RIGHT",
            camera_view="SIDE",
            output_dir=tmp_path,
        )
    assert BatchStore(tmp_path).list() == []


def test_clips_are_analysed_one_by_one_and_added_to_the_batch(tmp_path: Path) -> None:
    job = _job(tmp_path, "a.mp4", "bad.mp4", "c.mov")
    calls = []

    def analyzer(path: Path, stroke: str, hand: str, view: str) -> str:
        calls.append((path.name, stroke, hand, view))
        if "bad" in path.name:
            raise RuntimeError("Processing produced no output for /srv/app/uploads/x/")
        return f"id{len(calls)}"

    done = run_job(job["job_id"], output_dir=tmp_path, analyzer=analyzer)
    assert calls == [
        ("000_a.mp4", "FOREHAND_CLEAR", "RIGHT", "SIDE"),
        ("001_bad.mp4", "FOREHAND_CLEAR", "RIGHT", "SIDE"),
        ("002_c.mov", "FOREHAND_CLEAR", "RIGHT", "SIDE"),
    ]
    assert done["status"] == "done"
    assert [(c["status"], c["analysis_id"], c["error"]) for c in done["clips"]] == [
        ("done", "id1", None),
        ("failed", None, "Processing produced no output for "),
        ("done", "id3", None),
    ]
    batch = BatchStore(tmp_path).get(job["batch_id"])
    assert [(c.analysis_id, c.source_file, c.raw_video) for c in batch.clips] == [
        ("id1", "a.mp4", "labelling/videos/id1.mp4"),
        ("id3", "c.mov", "labelling/videos/id3.mov"),
    ]
    assert (tmp_path / "labelling/videos/id3.mov").read_bytes() == b"video:c.mov"
    assert not JobStore(tmp_path).staging_dir(job["job_id"]).exists()
    view = job_view(JobStore(tmp_path).get(job["job_id"]))
    assert (view["total"], view["done_count"], view["failed_count"], view["remaining_count"]) == (3, 2, 1, 0)


def test_running_job_without_a_worker_is_reported_interrupted(tmp_path: Path) -> None:
    job = _job(tmp_path, "a.mp4")
    assert job_view(job)["status"] == "interrupted"
    jobs_module._active.add(job["job_id"])
    try:
        assert job_view(job)["status"] == "running"
    finally:
        jobs_module._active.discard(job["job_id"])


def test_upload_route_starts_the_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    submitted = []
    monkeypatch.setattr(routes, "submit_job", submitted.append)
    result = routes.post_batch(
        files=[UploadFile(file=io.BytesIO(b"x"), filename="clip.mp4")],
        name="Set 3",
        stroke_type="forehand_smash",
        handedness="left",
        camera_view="side",
    )
    assert submitted == [result["job_id"]]
    assert (result["stroke_type"], result["handedness"], result["camera_view"]) == (
        "FOREHAND_SMASH",
        "LEFT",
        "SIDE",
    )
    assert result["total"] == 1
    assert routes.get_job(result["job_id"])["batch_id"] == result["batch_id"]
    assert routes.get_batches(coach=None)["batches"][0]["name"] == "Set 3"


def test_upload_route_rejects_bad_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    monkeypatch.setattr(routes, "submit_job", lambda _job_id: None)
    for kwargs in (
        {"stroke_type": "backhand_drop"},
        {"handedness": "both"},
        {"files": [UploadFile(file=io.BytesIO(b"x"), filename="clip.avi")]},
    ):
        args = {
            "files": [UploadFile(file=io.BytesIO(b"x"), filename="clip.mp4")],
            "name": "Set",
            "stroke_type": "FOREHAND_CLEAR",
            "handedness": "RIGHT",
            "camera_view": "SIDE",
            **kwargs,
        }
        with pytest.raises(HTTPException) as exc:
            routes.post_batch(**args)
        assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        routes.get_job("nope")
    assert exc.value.status_code == 404
