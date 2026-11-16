"""Dataset composition: size, skill mix, max 2 per participant, no reuse."""

from __future__ import annotations

from app.labelling.multisense.compose import compose_datasets, normalize_skill
from app.labelling.multisense.cut import ClipMeta


def _clip(pid: str, n: int, skill: str) -> ClipMeta:
    return ClipMeta(
        clip_id=f"{pid}_{n}",
        source_file="x.mov",
        participant_id=pid,
        skill_level=skill,
        hitting_position="Front",
        sound="Clear",
        ball_landing="H=0;V=1",
        ball_landing_horizontal="0",
        ball_landing_vertical="1",
        swing_time=1.0,
        swing_unix=1.0,
        start_s=0.0,
        end_s=2.5,
        stroke_num=n,
        handedness="RIGHT",
    )


def test_compose_three_datasets_of_eight_with_caps():
    pool: list[ClipMeta] = []
    # Plenty of each skill across many participants.
    skills = (["Beginner"] * 3 + ["Intermediate"] * 3 + ["Expert"] * 2) * 6
    for i, skill in enumerate(skills):
        pool.append(_clip(f"Sub{i % 12:02d}", i, skill))

    picks = compose_datasets(pool, count=3)
    assert len(picks) == 3
    used: set[str] = set()
    for pick in picks:
        assert len(pick.clips) == 8
        assert all(c.clip_id not in used for c in pick.clips)
        used.update(c.clip_id for c in pick.clips)
        assert max(pick.participant_counts.values()) <= 2
        assert pick.skill_counts.get("Beginner", 0) == 3
        assert pick.skill_counts.get("Intermediate", 0) == 3
        assert pick.skill_counts.get("Expert", 0) == 2


def test_compose_relaxes_mix_when_only_beginners_available():
    # 8 participants × 4 clips supports 3×8 under a max-2-per-participant cap.
    pool = [_clip(f"Sub{i:02d}", j, "Beginner") for i in range(8) for j in range(4)]
    picks = compose_datasets(pool, count=3)
    assert len(picks) == 3
    for pick in picks:
        assert len(pick.clips) == 8
        assert max(pick.participant_counts.values()) <= 2
        assert normalize_skill("Beginner") in pick.skill_counts
