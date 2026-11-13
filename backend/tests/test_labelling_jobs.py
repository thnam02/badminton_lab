"""Dataset uploads from the website, analysed in the background."""

from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.config import settings
from app.labelling import jobs as jobs_module
from app.labelling.batches import Batch, BatchStore
from app.labelling.jobs import (
    JobStore,
    UploadError,
    create_upload_job,
    job_view,
    run_job,
)
from app.routes import labelling as routes

DUE = (date.today() + timedelta(days=10)).isoformat()


def _uploads(*clips: tuple[str, str, str]) -> list[tuple[str, io.BytesIO, str, str]]:
    return [(n, io.BytesIO(f"video:{n}".encode()), hand, view) for n, hand, view in clips]


def _job(tmp_path: Path, *clips: tuple[str, str, str]) -> dict:
    BatchStore(tmp_path).save(Batch(batch_id="set-2", name="Set 2"))
    return create_upload_job(
        _uploads(*clips),
        batch_id="set-2",
        batch_name="Set 2",
        stroke="FOREHAND_CLEAR",
        output_dir=tmp_path,
    )


def test_upload_stages_clips_with_their_own_capture_context(tmp_path: Path) -> None:
    job = _job(tmp_path, ("a.mp4", "RIGHT", "SIDE"), ("b one.MOV", "LEFT", "SIDE"))
    assert (job["handedness"], job["camera_view"]) == ("MIXED", "SIDE")
    saved = JobStore(tmp_path).get(job["job_id"])
    assert [(c["source_file"], c["handedness"], c["camera_view"]) for c in saved["clips"]] == [
        ("a.mp4", "RIGHT", "SIDE"),
        ("b one.MOV", "LEFT", "SIDE"),
    ]
    assert all(c["status"] == "queued" for c in job["clips"])
    staged = sorted(p.name for p in JobStore(tmp_path).staging_dir(job["job_id"]).iterdir())
    assert staged == ["000_a.mp4", "001_b_one.MOV"]
    assert [j["job_id"] for j in JobStore(tmp_path).for_batch("set-2")] == [job["job_id"]]


@pytest.mark.parametrize(
    ("clips", "message"),
    [((), "at least one clip"), ((("notes.txt", "RIGHT", "SIDE"),), "not an .mp4 or .mov")],
)
def test_bad_uploads_are_refused(tmp_path: Path, clips: tuple, message: str) -> None:
    with pytest.raises(UploadError, match=message):
        create_upload_job(
            _uploads(*clips), batch_id="x", batch_name="x", stroke="FOREHAND_CLEAR", output_dir=tmp_path
        )


def test_clips_are_analysed_one_by_one_and_added_to_the_dataset(tmp_path: Path) -> None:
    job = _job(
        tmp_path, ("a.mp4", "RIGHT", "SIDE"), ("bad.mp4", "RIGHT", "SIDE"), ("c.mov", "LEFT", "REAR")
    )
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
        ("002_c.mov", "FOREHAND_CLEAR", "LEFT", "REAR"),
    ]
    assert done["status"] == "done"
    assert [(c["status"], c["analysis_id"], c["error"]) for c in done["clips"]] == [
        ("done", "id1", None),
        ("failed", None, "Processing produced no output for "),
        ("done", "id3", None),
    ]
    batch = BatchStore(tmp_path).get("set-2")
    assert [(c.analysis_id, c.source_file, c.raw_video) for c in batch.clips] == [
        ("id1", "a.mp4", "labelling/videos/id1.mp4"),
        ("id3", "c.mov", "labelling/videos/id3.mov"),
    ]
    assert (tmp_path / "labelling/videos/id3.mov").read_bytes() == b"video:c.mov"
    assert not JobStore(tmp_path).staging_dir(job["job_id"]).exists()
    view = job_view(JobStore(tmp_path).get(job["job_id"]))
    assert (view["total"], view["done_count"], view["failed_count"], view["remaining_count"]) == (3, 2, 1, 0)


def test_running_job_without_a_worker_is_reported_interrupted(tmp_path: Path) -> None:
    job = _job(tmp_path, ("a.mp4", "RIGHT", "SIDE"))
    assert job_view(job)["status"] == "interrupted"
    jobs_module._active.add(job["job_id"])
    try:
        assert job_view(job)["status"] == "running"
    finally:
        jobs_module._active.discard(job["job_id"])


def _files(n: int, suffix: str = ".mp4") -> list[UploadFile]:
    return [UploadFile(file=io.BytesIO(b"x"), filename=f"clip{i}{suffix}") for i in range(n)]


def _post(n: int = 5, **overrides) -> dict:
    args = {
        "technique": "forehand_smash",
        "due_date": DUE,
        "note": "  Watch the elbow  ",
        "files": _files(n),
        "handedness": ["left"] * n,
        "camera_view": ["side"] * n,
        "existing_ids": [],
        **overrides,
    }
    return routes.post_dataset(**args)


def test_dataset_route_starts_the_upload_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    submitted = []

    def submit(job_id: str) -> None:
        submitted.append(job_id)
        jobs_module._active.add(job_id)

    monkeypatch.setattr(routes, "submit_job", submit)
    try:
        result = _post()
    finally:
        jobs_module._active.difference_update(submitted)
    dataset, job = result["dataset"], result["job"]
    assert submitted == [job["job_id"]]
    assert (dataset["technique"], dataset["number"], dataset["title"]) == (
        "FOREHAND_SMASH",
        1,
        "Dataset 1",
    )
    assert (dataset["due_date"], dataset["note"]) == (DUE, "Watch the elbow")
    assert (dataset["video_count"], dataset["processing_count"], dataset["status"]) == (
        5,
        5,
        "not_started",
    )
    assert (job["stroke_type"], job["handedness"], job["camera_view"], job["total"]) == (
        "FOREHAND_SMASH",
        "LEFT",
        "SIDE",
        5,
    )
    assert routes.get_job(job["job_id"])["batch_id"] == dataset["dataset_id"]
    detail = routes.get_dataset(dataset["dataset_id"])
    assert [u["job_id"] for u in detail["uploads"]] == [job["job_id"]]
    assert _post()["dataset"]["number"] == 2


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"files": _files(4), "handedness": ["RIGHT"] * 4, "camera_view": ["SIDE"] * 4}, "5 to 10"),
        ({"files": _files(11), "handedness": ["RIGHT"] * 11, "camera_view": ["SIDE"] * 11}, "5 to 10"),
        ({"handedness": ["RIGHT"] * 4}, "needs a handedness"),
        ({"technique": "backhand_drop"}, ""),
        ({"handedness": ["both"] * 5}, ""),
        ({"files": _files(5, ".avi")}, "not an .mp4 or .mov"),
        ({"due_date": "2020-01-01"}, "in the past"),
        ({"due_date": "soon"}, "not a date"),
        ({"existing_ids": ["missing"]}, ""),
    ],
)
def test_dataset_route_rejects_bad_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overrides: dict, message: str
) -> None:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    monkeypatch.setattr(routes, "submit_job", lambda _job_id: None)
    with pytest.raises(HTTPException) as exc:
        _post(**overrides)
    assert exc.value.status_code == 422
    assert message in exc.value.detail
    assert BatchStore().list() == []


def test_unknown_job_is_404() -> None:
    with pytest.raises(HTTPException) as exc:
        routes.get_job("nope")
    assert exc.value.status_code == 404
