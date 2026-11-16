"""Cut one-stroke Side clips from MultiSense long videos."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.labelling.multisense import MIN_GAP_S, POST_S, PRE_S, SOURCE_NAME
from app.labelling.multisense.annotations import (
    SwingAnnotation,
    find_side_video,
    load_forehand_clears,
    load_handedness,
)
from app.labelling.multisense.sync import (
    _motion_series,
    estimate_sync,
    swing_time_in_video,
)


@dataclass(slots=True)
class ClipMeta:
    clip_id: str
    source_file: str
    participant_id: str
    skill_level: str
    hitting_position: str
    sound: str
    ball_landing: str
    ball_landing_horizontal: str
    ball_landing_vertical: str
    swing_time: float
    swing_unix: float
    start_s: float
    end_s: float
    stroke_num: int
    handedness: str
    source: str = SOURCE_NAME

    def to_dict(self) -> dict:
        return asdict(self)


def skip_close_swings(times: list[float], min_gap: float = MIN_GAP_S) -> list[bool]:
    """True = keep. Drop a swing if another kept swing is within min_gap seconds."""
    keep = [True] * len(times)
    last_kept: float | None = None
    order = sorted(range(len(times)), key=lambda i: times[i])
    for i in order:
        t = times[i]
        if last_kept is not None and abs(t - last_kept) < min_gap:
            keep[i] = False
            continue
        last_kept = t
    return keep


def cut_window(swing_time: float, *, pre: float = PRE_S, post: float = POST_S, duration: float) -> tuple[float, float]:
    start = max(0.0, swing_time - pre)
    end = min(duration, swing_time + post)
    return start, end


def _ffmpeg_cut(src: Path, dest: Path, start: float, end: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(src),
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )


def cut_participant(
    root: Path,
    participant_id: str,
    out_dir: Path,
    *,
    swings: list[SwingAnnotation] | None = None,
    handedness_map: dict[str, str] | None = None,
    log=print,
) -> list[ClipMeta]:
    video = find_side_video(root, participant_id)
    if video is None:
        log(f"{participant_id}: no Side video, skip")
        return []
    all_swings = swings if swings is not None else load_forehand_clears(root)
    mine = [s for s in all_swings if s.participant_id == participant_id]
    if not mine:
        return []
    mine = sorted(mine, key=lambda s: s.start_unix)
    sync = estimate_sync(video, mine)
    times, energy = _motion_series(video)
    swing_times = [swing_time_in_video(sync, s, times, energy) for s in mine]
    keep = skip_close_swings(swing_times)
    hand_map = handedness_map if handedness_map is not None else load_handedness(root)
    handedness = hand_map.get(participant_id, "RIGHT")
    if participant_id not in hand_map:
        log(f"WARNING: no handedness for {participant_id}; using RIGHT")

    out: list[ClipMeta] = []
    part_dir = out_dir / participant_id
    part_dir.mkdir(parents=True, exist_ok=True)
    for swing, t_vid, ok in zip(mine, swing_times, keep, strict=True):
        if not ok:
            continue
        start, end = cut_window(t_vid, duration=sync.duration_s)
        if end - start < 1.0:
            continue
        clip_id = f"{participant_id}_fhclear_{swing.stroke_num:03d}"
        dest = part_dir / f"{clip_id}.mp4"
        meta_path = part_dir / f"{clip_id}.json"
        try:
            _ffmpeg_cut(video, dest, start, end)
        except subprocess.CalledProcessError as exc:
            log(f"  cut failed {clip_id}: {exc}")
            continue
        meta = ClipMeta(
            clip_id=clip_id,
            source_file=str(video.relative_to(root)) if video.is_relative_to(root) else str(video),
            participant_id=participant_id,
            skill_level=swing.skill_level,
            hitting_position=swing.hitting_position,
            sound=swing.sound,
            ball_landing=swing.ball_landing,
            ball_landing_horizontal=swing.ball_landing_horizontal,
            ball_landing_vertical=swing.ball_landing_vertical,
            swing_time=t_vid,
            swing_unix=0.5 * (swing.start_unix + swing.stop_unix),
            start_s=start,
            end_s=end,
            stroke_num=swing.stroke_num,
            handedness=handedness,
        )
        meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
        out.append(meta)
    log(f"{participant_id}: cut {len(out)} clips from {video.name} (offset={sync.offset_s:+.1f}s)")
    return out


def cut_all(root: Path, out_dir: Path, *, log=print) -> list[ClipMeta]:
    swings = load_forehand_clears(root)
    hands = load_handedness(root)
    participants = sorted({s.participant_id for s in swings if find_side_video(root, s.participant_id)})
    out: list[ClipMeta] = []
    for pid in participants:
        out.extend(
            cut_participant(
                root,
                pid,
                out_dir,
                swings=[s for s in swings if s.participant_id == pid],
                handedness_map=hands,
                log=log,
            )
        )
    manifest = out_dir / "manifest.json"
    manifest.write_text(json.dumps([m.to_dict() for m in out], indent=2), encoding="utf-8")
    log(f"Total clips: {len(out)} -> {manifest}")
    return out


def load_manifest(out_dir: Path) -> list[ClipMeta]:
    raw = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    return [ClipMeta(**row) for row in raw]
