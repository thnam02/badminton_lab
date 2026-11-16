"""Load MultiSense annotation + survey tables from the Documentations folder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

STROKE_COL = "Annotation Level 1\n(Stroke Type)"
SKILL_COL = "Annotation Level 2\n(Skill Level)"
LAND_H_COL = "Annotation Level 3\n(Landing Location - Horizontal)"
LAND_V_COL = "Annotation Level 3\n(Landing Location - Vertical)"
HIT_COL = "Annotation Level 4\n(Hitting Location, major voting)"
SOUND_COL = "Annotation Level 5\n(Hitting Sound, major voting)"
FOREHAND = "Forehand Clear"

SIDE_NAME_CANDIDATES = (
    "Forehand Clear Side Video.mov",
    "Forehand Clear Sideo Video.mov",  # Sub08 typo in the archive
)


@dataclass(frozen=True, slots=True)
class SwingAnnotation:
    participant_id: str
    stroke_num: int
    start_unix: float
    stop_unix: float
    skill_level: str
    hitting_position: str
    sound: str
    ball_landing_horizontal: str
    ball_landing_vertical: str

    @property
    def ball_landing(self) -> str:
        return f"H={self.ball_landing_horizontal};V={self.ball_landing_vertical}"


def docs_dir(root: Path) -> Path:
    return root / "Documentations"


def load_forehand_clears(root: Path) -> list[SwingAnnotation]:
    path = docs_dir(root) / "Annotation Data File.xlsx"
    df = pd.read_excel(path)
    rows = df[df[STROKE_COL] == FOREHAND]
    out: list[SwingAnnotation] = []
    for _, r in rows.iterrows():
        out.append(
            SwingAnnotation(
                participant_id=str(r["Subject Number"]),
                stroke_num=int(r["Stroke Num"]),
                start_unix=float(r["Annotation Start Time"]),
                stop_unix=float(r["Annotation Stop Time"]),
                skill_level=str(r[SKILL_COL]),
                hitting_position=str(r[HIT_COL]),
                sound=str(r[SOUND_COL]),
                ball_landing_horizontal=str(r[LAND_H_COL]),
                ball_landing_vertical=str(r[LAND_V_COL]),
            )
        )
    return out


def load_handedness(root: Path) -> dict[str, str]:
    """Map SubXX -> RIGHT|LEFT from the survey Dominant Hand column."""
    path = docs_dir(root) / "Survey Data File.xlsx"
    df = pd.read_excel(path)
    out: dict[str, str] = {}
    for _, r in df.iterrows():
        name = str(r["Name"]).strip()
        hand = str(r["Dominant Hand"]).strip().casefold()
        if hand.startswith("left"):
            out[name] = "LEFT"
        else:
            out[name] = "RIGHT"
    return out


def find_side_video(root: Path, participant_id: str) -> Path | None:
    """Return the Forehand Clear Side .mov for a subject, searching Part folders."""
    for part in sorted(root.glob("Data Archive Part*")):
        folder = part / participant_id
        if not folder.is_dir():
            continue
        for name in SIDE_NAME_CANDIDATES:
            path = folder / name
            if path.is_file():
                return path
        # Fallback: any Side/Sideo mov for forehand clear
        for path in folder.glob("Forehand Clear *Side*.mov"):
            return path
        for path in folder.glob("Forehand Clear *Sideo*.mov"):
            return path
    return None
