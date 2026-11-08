"""Labelling batches and the create-batch CLI."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from app.labelling import cli
from app.labelling.batches import Batch, BatchClip, BatchStore
from app.routes.analyze import analyze


def _clips(folder: Path, names: list[str]) -> None:
    folder.mkdir()
    for name in names:
        (folder / name).write_bytes(b"video:" + name.encode())


def test_folder_batch_runs_each_clip_and_keeps_raw_videos(tmp_path: Path) -> None:
    folder = tmp_path / "clips"
    _clips(folder, ["b.mov", "a.mp4", "notes.txt"])
    store = BatchStore(tmp_path / "outputs")
    calls = []

    def fake_analyzer(path: Path, stroke: str, hand: str, view: str) -> str:
        calls.append((path.name, stroke, hand, view))
        return f"id{len(calls)}"

    batch, failures = cli.create_batch_from_folder(
        folder,
        name="Side-view set 1",
        stroke="FOREHAND_CLEAR",
        handedness="RIGHT",
        camera_view="SIDE",
        store=store,
        analyzer=fake_analyzer,
        log=lambda _msg: None,
    )
    assert failures == []
    assert calls == [
        ("a.mp4", "FOREHAND_CLEAR", "RIGHT", "SIDE"),
        ("b.mov", "FOREHAND_CLEAR", "RIGHT", "SIDE"),
    ]
    assert batch.batch_id.startswith("side-view-set-1-")
    assert [(c.analysis_id, c.source_file, c.raw_video) for c in batch.clips] == [
        ("id1", "a.mp4", "labelling/videos/id1.mp4"),
        ("id2", "b.mov", "labelling/videos/id2.mov"),
    ]
    assert (tmp_path / "outputs/labelling/videos/id2.mov").read_bytes() == b"video:b.mov"
    saved = json.loads(store.path_for(batch.batch_id).read_text())
    assert saved["batch_format_version"] == "1.0.0"
    assert store.get(batch.batch_id).clips == batch.clips


def test_failed_clips_are_reported_and_skipped(tmp_path: Path) -> None:
    folder = tmp_path / "clips"
    _clips(folder, ["bad.mp4", "good.mp4"])

    def analyzer(path: Path, *_args) -> str:
        if path.name == "bad.mp4":
            raise RuntimeError("Processing produced no output")
        return "good1"

    batch, failures = cli.create_batch_from_folder(
        folder,
        name="x",
        stroke="FOREHAND_SMASH",
        handedness="LEFT",
        camera_view="SIDE",
        store=BatchStore(tmp_path / "out"),
        analyzer=analyzer,
        log=lambda _msg: None,
    )
    assert [c.analysis_id for c in batch.clips] == ["good1"]
    assert [(p.name, d) for p, d in failures] == [("bad.mp4", "Processing produced no output")]


def test_empty_folder_creates_no_batch(tmp_path: Path) -> None:
    folder = tmp_path / "clips"
    _clips(folder, ["readme.txt"])
    with pytest.raises(ValueError, match="No .mp4 or .mov"):
        cli.create_batch_from_folder(
            folder,
            name="x",
            stroke="FOREHAND_CLEAR",
            handedness="RIGHT",
            camera_view="SIDE",
            store=BatchStore(tmp_path / "out"),
            analyzer=lambda *_a: "never",
        )
    assert not (tmp_path / "out/labelling/batches").exists()


def test_cli_creates_a_batch_from_existing_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "BatchStore", lambda: BatchStore(tmp_path))
    assert cli.main(["create", "--analysis-ids", "abc", "def", "--name", "Quick check"]) == 0
    out = capsys.readouterr().out
    batch_id = out.split("(")[1].split(")")[0]
    assert f"http://localhost:3000/coach/{batch_id}" in out
    assert [c.analysis_id for c in BatchStore(tmp_path).get(batch_id).clips] == ["abc", "def"]


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
