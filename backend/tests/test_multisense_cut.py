"""Clip cutting windows, close-swing skip, and metadata fields."""

from __future__ import annotations

from app.labelling.multisense.cut import ClipMeta, cut_window, skip_close_swings


def test_cut_window_is_1_5_before_and_1_0_after():
    start, end = cut_window(10.0, duration=60.0)
    assert (start, end) == (8.5, 11.0)


def test_cut_window_clamps_to_video_bounds():
    assert cut_window(0.5, duration=5.0) == (0.0, 1.5)
    assert cut_window(4.8, duration=5.0) == (3.3, 5.0)


def test_skip_swings_closer_than_1_5s():
    times = [0.0, 1.0, 3.0, 4.4, 6.0]
    keep = skip_close_swings(times, min_gap=1.5)
    assert keep == [True, False, True, False, True]


def test_clip_meta_has_hidden_label_fields():
    meta = ClipMeta(
        clip_id="Sub01_fhclear_001",
        source_file="Data Archive Part1/Sub01/Forehand Clear Side Video.mov",
        participant_id="Sub01",
        skill_level="Beginner",
        hitting_position="Front",
        sound="Clear",
        ball_landing="H=0;V=2",
        ball_landing_horizontal="0",
        ball_landing_vertical="2",
        swing_time=12.3,
        swing_unix=1.0,
        start_s=10.8,
        end_s=13.3,
        stroke_num=1,
        handedness="RIGHT",
    )
    d = meta.to_dict()
    for key in (
        "skill_level",
        "hitting_position",
        "sound",
        "ball_landing",
        "participant_id",
        "swing_time",
        "source_file",
    ):
        assert key in d
