"""Align MultiSense Unix annotation times with Side video clock."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

import cv2
import numpy as np

from app.labelling.multisense.annotations import SwingAnnotation


@dataclass(frozen=True, slots=True)
class VideoSync:
    """Maps annotation Unix time -> video seconds: t_vid = unix - t0 + offset."""

    duration_s: float
    t0: float
    offset_s: float
    fps: float

    def unix_to_video(self, unix: float) -> float:
        return float(unix) - self.t0 + self.offset_s


def probe_duration(path) -> tuple[float, float]:
    meta = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            text=True,
        )
    )
    duration = float(meta["format"]["duration"])
    fps = 30.0
    for stream in meta.get("streams") or []:
        if stream.get("codec_type") == "video":
            rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "30/1"
            if isinstance(rate, str) and "/" in rate:
                a, b = rate.split("/", 1)
                fps = float(a) / float(b) if float(b) else 30.0
            break
    return duration, fps


def _motion_series(path, sample_hz: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / sample_hz)))
    prev = None
    times: list[float] = []
    energy: list[float] = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (128, 96))
            h, w = gray.shape
            gray = gray[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
            if prev is not None:
                times.append(idx / fps)
                energy.append(float(np.mean(cv2.absdiff(gray, prev))))
            prev = gray
        idx += 1
    cap.release()
    return np.asarray(times), np.asarray(energy)


def estimate_sync(path, swings: list[SwingAnnotation]) -> VideoSync:
    """t0 = last_stop - duration; offset maximizes motion energy inside annotation windows."""
    if not swings:
        raise ValueError("No swings to sync against")
    duration, fps = probe_duration(path)
    last_stop = max(s.stop_unix for s in swings)
    t0 = last_stop - duration
    times, energy = _motion_series(path)
    if len(times) == 0:
        return VideoSync(duration_s=duration, t0=t0, offset_s=0.0, fps=fps)

    windows = [(s.start_unix - t0, s.stop_unix - t0) for s in swings]

    def score(offset: float) -> float:
        total = 0.0
        n = 0
        for a, b in windows:
            mask = (times >= a + offset) & (times <= b + offset)
            if mask.any():
                total += float(energy[mask].max())
                n += 1
        return total / max(n, 1)

    offsets = np.arange(-2.0, 8.0, 0.5)
    best = float(max(offsets, key=score))
    return VideoSync(duration_s=duration, t0=t0, offset_s=best, fps=fps)


def swing_time_in_video(
    sync: VideoSync,
    swing: SwingAnnotation,
    times: np.ndarray | None = None,
    energy: np.ndarray | None = None,
    path=None,
) -> float:
    """Contact/swing instant in video seconds: peak motion in the synced annotation window."""
    start = sync.unix_to_video(swing.start_unix)
    stop = sync.unix_to_video(swing.stop_unix)
    mid = 0.5 * (start + stop)
    if times is None or energy is None:
        if path is None:
            return mid
        times, energy = _motion_series(path)
    mask = (times >= start) & (times <= stop)
    if not mask.any():
        return mid
    return float(times[mask][int(np.argmax(energy[mask]))])
