"""Pick clips into coach datasets with skill mix and per-participant caps."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from app.labelling.multisense.cut import ClipMeta

# Target mix per dataset of 8 (Part 1 is beginner-only until Parts 2/3 arrive).
TARGET_SIZE = 8
TARGET_MIX = {"Beginner": 3, "Intermediate": 3, "Expert": 2}
MAX_PER_PARTICIPANT = 2

# Annotation skill labels -> bucket
_SKILL_ALIASES = {
    "beginner": "Beginner",
    "novice": "Beginner",
    "intermediate": "Intermediate",
    "expert": "Expert",
}


def normalize_skill(raw: str) -> str:
    key = (raw or "").strip().casefold()
    return _SKILL_ALIASES.get(key, raw.strip().title() if raw else "Beginner")


@dataclass(frozen=True, slots=True)
class DatasetPick:
    clips: list[ClipMeta]

    @property
    def skill_counts(self) -> dict[str, int]:
        return dict(Counter(normalize_skill(c.skill_level) for c in self.clips))

    @property
    def participant_counts(self) -> dict[str, int]:
        return dict(Counter(c.participant_id for c in self.clips))


def compose_datasets(
    pool: list[ClipMeta],
    *,
    count: int = 3,
    size: int = TARGET_SIZE,
    target_mix: dict[str, int] | None = None,
    max_per_participant: int = MAX_PER_PARTICIPANT,
) -> list[DatasetPick]:
    """Greedy fill of ``count`` datasets. Relaxes skill mix when a bucket is empty."""
    mix = dict(target_mix or TARGET_MIX)
    used: set[str] = set()
    datasets: list[DatasetPick] = []

    for _ in range(count):
        picked: list[ClipMeta] = []
        per_part: dict[str, int] = defaultdict(int)
        need = dict(mix)

        def try_take(skill: str | None) -> bool:
            for clip in pool:
                if clip.clip_id in used:
                    continue
                if per_part[clip.participant_id] >= max_per_participant:
                    continue
                if skill is not None and normalize_skill(clip.skill_level) != skill:
                    continue
                picked.append(clip)
                used.add(clip.clip_id)
                per_part[clip.participant_id] += 1
                bucket = normalize_skill(clip.skill_level)
                if bucket in need and need[bucket] > 0:
                    need[bucket] -= 1
                return True
            return False

        # First honour the target mix where possible.
        for skill, n in mix.items():
            for _ in range(n):
                if len(picked) >= size:
                    break
                try_take(skill)

        # Fill remaining slots with any skill.
        while len(picked) < size:
            if not try_take(None):
                break

        if len(picked) < size:
            break
        datasets.append(DatasetPick(clips=picked))
    return datasets
