"""MultiSense ground-truth labels stay off coach payloads; export can read them."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.labelling.batches import BatchClip
from app.labelling.datasets import create_dataset, dataset_summary
from app.labelling.multisense import SOURCE_NAME
from app.labelling.multisense.cut import ClipMeta
from app.labelling.multisense.external_labels import (
    coach_safe_view,
    load_external_labels,
    save_external_labels,
)
from tests.test_labelling_clips import seed_analysis


@pytest.fixture
def outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    return tmp_path


def test_coach_safe_view_strips_hidden_fields():
    raw = {
        "analysis_id": "a1",
        "source_file": "clip.mp4",
        "skill_level": "Expert",
        "hitting_position": "Front",
        "sound": "Clear",
        "ball_landing": "H=1;V=2",
        "participant_id": "Sub01",
        "source": SOURCE_NAME,
    }
    safe = coach_safe_view(raw)
    assert "skill_level" not in safe
    assert "hitting_position" not in safe
    assert "sound" not in safe
    assert "ball_landing" not in safe
    assert "participant_id" not in safe
    assert "source" not in safe
    assert safe["analysis_id"] == "a1"


def test_dataset_summary_hides_source_from_coach(outputs: Path):
    clips = []
    for i in range(8):
        aid = f"msclip{i}"
        seed_analysis(outputs, aid, stroke="FOREHAND_CLEAR")
        clips.append(BatchClip(analysis_id=aid, source_file=f"{aid}.mp4"))
    batch, _ = create_dataset(
        technique="FOREHAND_CLEAR",
        due_date=None,
        source=SOURCE_NAME,
        existing=clips,
        output_dir=outputs,
    )
    coach_view = dataset_summary(batch, include_source=False)
    admin_view = dataset_summary(batch, include_source=True)
    assert "source" not in coach_view
    assert admin_view["source"] == SOURCE_NAME
    assert batch.due_date is None


def test_external_labels_roundtrip(tmp_path: Path):
    meta = ClipMeta(
        clip_id="Sub01_fhclear_001",
        source_file="side.mov",
        participant_id="Sub01",
        skill_level="Beginner",
        hitting_position="Front",
        sound="Clear",
        ball_landing="H=0;V=1",
        ball_landing_horizontal="0",
        ball_landing_vertical="1",
        swing_time=1.0,
        swing_unix=1.0,
        start_s=0.0,
        end_s=2.5,
        stroke_num=1,
        handedness="RIGHT",
    )
    save_external_labels("aid1", meta, tmp_path)
    loaded = load_external_labels("aid1", tmp_path)
    assert loaded is not None
    assert loaded["skill_level"] == "Beginner"
    assert loaded["hitting_position"] == "Front"
    assert loaded["sound"] == "Clear"
