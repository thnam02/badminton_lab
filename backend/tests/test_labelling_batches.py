"""Labelling batches and the create-dataset CLI."""

from __future__ import annotations

import inspect
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.config import settings
from app.labelling import cli
from app.labelling.batches import Batch, BatchClip, BatchStore
from app.labelling.datasets import DatasetError
from app.routes.analyze import analyze
from tests.test_labelling_clips import seed_analysis

DUE = (date.today() + timedelta(days=14)).isoformat()


def _clips(folder: Path, names: list[str]) -> None:
    folder.mkdir()
    for name in names:
        (folder / name).write_bytes(b"video:" + name.encode())


def _seeding_analyzer(root: Path, calls: list, fail: str | None = None):
    """Stands in for /analyze: records the call and saves the analysis artifacts."""

    def analyzer(path: Path, stroke: str, hand: str, view: str) -> str:
        calls.append((path.name, stroke, hand, view))
        if path.name == fail:
            raise RuntimeError("Processing produced no output")
        analysis_id = f"id{len(calls)}"
        seed_analysis(root, analysis_id, stroke=stroke)
        return analysis_id

    return analyzer


def test_folder_dataset_runs_each_clip_and_keeps_raw_videos(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    folder = tmp_path / "clips"
    _clips(folder, ["e.mov", "a.mp4", "b.mp4", "c.mp4", "d.mp4", "notes.txt"])
    store = BatchStore(outputs)
    calls: list = []

    batch, failures = cli.create_dataset_from_folder(
        folder,
        technique="FOREHAND_CLEAR",
        due_date=DUE,
        note="Side view",
        handedness="RIGHT",
        camera_view="SIDE",
        store=store,
        analyzer=_seeding_analyzer(outputs, calls),
        log=lambda _msg: None,
    )
    assert failures == []
    assert [c[0] for c in calls] == ["a.mp4", "b.mp4", "c.mp4", "d.mp4", "e.mov"]
    assert all(c[1:] == ("FOREHAND_CLEAR", "RIGHT", "SIDE") for c in calls)
    assert (batch.technique, batch.number, batch.due_date, batch.note) == (
        "FOREHAND_CLEAR",
        1,
        DUE,
        "Side view",
    )
    assert batch.name == "Forehand clear · Dataset 1"
    assert [(c.analysis_id, c.source_file, c.raw_video) for c in batch.clips][-1] == (
        "id5",
        "e.mov",
        "labelling/videos/id5.mov",
    )
    assert (outputs / "labelling/videos/id5.mov").read_bytes() == b"video:e.mov"
    saved = store.get(batch.batch_id)
    assert saved.clips == batch.clips
    assert saved.created_at


def test_failed_clips_are_reported_and_skipped(tmp_path: Path) -> None:
    outputs = tmp_path / "out"
    outputs.mkdir()
    folder = tmp_path / "clips"
    _clips(folder, [f"{n}.mp4" for n in ("a", "bad", "c", "d", "e", "f")])
    batch, failures = cli.create_dataset_from_folder(
        folder,
        technique="FOREHAND_SMASH",
        due_date=DUE,
        handedness="LEFT",
        camera_view="SIDE",
        store=BatchStore(outputs),
        analyzer=_seeding_analyzer(outputs, [], fail="bad.mp4"),
        log=lambda _msg: None,
    )
    assert len(batch.clips) == 5
    assert batch.technique == "FOREHAND_SMASH"
    assert [(p.name, d) for p, d in failures] == [("bad.mp4", "Processing produced no output")]


def test_too_many_failures_leave_no_dataset(tmp_path: Path) -> None:
    outputs = tmp_path / "out"
    outputs.mkdir()
    folder = tmp_path / "clips"
    _clips(folder, [f"{n}.mp4" for n in ("a", "bad", "c", "d", "e")])
    with pytest.raises(DatasetError, match="Only 4 of 5 clips were analysed"):
        cli.create_dataset_from_folder(
            folder,
            technique="FOREHAND_CLEAR",
            due_date=DUE,
            handedness="RIGHT",
            camera_view="SIDE",
            store=BatchStore(outputs),
            analyzer=_seeding_analyzer(outputs, [], fail="bad.mp4"),
            log=lambda _msg: None,
        )
    assert BatchStore(outputs).list() == []


@pytest.mark.parametrize(
    ("names", "message"),
    [
        (["readme.txt"], "No .mp4 or .mov"),
        ([f"{i}.mp4" for i in range(4)], "needs 5 to 10 videos"),
        ([f"{i}.mp4" for i in range(11)], "needs 5 to 10 videos"),
    ],
)
def test_folder_size_is_checked_before_any_analysis(
    tmp_path: Path, names: list[str], message: str
) -> None:
    folder = tmp_path / "clips"
    _clips(folder, names)
    calls: list = []
    with pytest.raises(ValueError, match=message):
        cli.create_dataset_from_folder(
            folder,
            technique="FOREHAND_CLEAR",
            due_date=DUE,
            handedness="RIGHT",
            camera_view="SIDE",
            store=BatchStore(tmp_path / "out"),
            analyzer=_seeding_analyzer(tmp_path, calls),
        )
    assert calls == []
    assert BatchStore(tmp_path / "out").list() == []


def test_cli_creates_a_dataset_from_existing_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    ids = [f"a{i}" for i in range(5)]
    for analysis_id in ids:
        seed_analysis(tmp_path, analysis_id)
    argv = ["create", "--analysis-ids", *ids, "--technique", "FOREHAND_CLEAR", "--due", DUE]
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    batch_id = out.split("(")[1].split(")")[0]
    assert f"http://localhost:3000/coach/datasets/{batch_id}" in out
    assert [c.analysis_id for c in BatchStore().get(batch_id).clips] == ids

    assert cli.main(["create", "--analysis-ids", *ids[:4], "--due", DUE]) == 1
    assert "needs 5 to 10 videos" in capsys.readouterr().err


def test_unsafe_ids_are_rejected(tmp_path: Path) -> None:
    store = BatchStore(tmp_path)
    with pytest.raises(ValueError):
        store.get("../secrets")
    with pytest.raises(ValueError):
        store.save(Batch(batch_id="ok", name="ok", clips=[BatchClip(analysis_id="../x")]))


def test_cli_passes_every_analyze_parameter_explicitly() -> None:
    """Calling the route directly skips FastAPI defaults, so none may be left out."""
    params = set(inspect.signature(analyze).parameters)
    source = inspect.getsource(cli.analyze_clip)
    assert all(f"{p}=" in source for p in params)
