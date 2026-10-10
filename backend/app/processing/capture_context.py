"""User-declared capture context: player handedness and camera view.

Handedness convention: the pipeline measures ``right_*`` joints everywhere.
For a LEFT-handed player the raw pose has its ``left_*`` / ``right_*`` labels
swapped immediately after RTMPose, so every downstream ``right_*`` field means
"racket arm" (and ``left_*`` means "non-racket side"). Interior joint angles
and speed magnitudes are mirror-invariant, so no coordinate flip is needed.
Anything that must show the player's real anatomy (e.g. 3D mesh fitting)
should call ``swap_left_right`` again to restore true labels.
"""

from __future__ import annotations

from app.schemas.pose import PoseFrame, PoseSequence

HANDEDNESS_RIGHT = "RIGHT"
HANDEDNESS_LEFT = "LEFT"
HANDEDNESS_UNKNOWN = "UNKNOWN"
HANDEDNESS_VALUES = (HANDEDNESS_RIGHT, HANDEDNESS_LEFT, HANDEDNESS_UNKNOWN)

CAMERA_VIEW_SIDE = "SIDE"
CAMERA_VIEW_FRONT = "FRONT"
CAMERA_VIEW_REAR = "REAR"
CAMERA_VIEW_UNKNOWN = "UNKNOWN"
CAMERA_VIEW_VALUES = (
    CAMERA_VIEW_SIDE,
    CAMERA_VIEW_FRONT,
    CAMERA_VIEW_REAR,
    CAMERA_VIEW_UNKNOWN,
)

WARNING_HANDEDNESS_UNKNOWN = "HANDEDNESS_UNKNOWN"
WARNING_CAMERA_VIEW_FRONT = "CAMERA_VIEW_FRONT"
WARNING_CAMERA_VIEW_REAR = "CAMERA_VIEW_REAR"

# Multiplicative quality-confidence factors — unvalidated prior. Front/rear
# views foreshorten the arm, so 2D elbow/shoulder angles diverge most from 3D.
CAPTURE_CONTEXT_CONFIDENCE_FACTORS: dict[str, float] = {
    WARNING_HANDEDNESS_UNKNOWN: 0.95,  # unvalidated prior
    WARNING_CAMERA_VIEW_FRONT: 0.85,  # unvalidated prior
    WARNING_CAMERA_VIEW_REAR: 0.85,  # unvalidated prior
}

RACKET_ARM_NOTE = (
    "Player declared LEFT-handed: left/right keypoint labels were swapped after "
    "pose estimation, so every right_* field (angles, speeds, metrics) refers "
    "to the racket arm, i.e. the player's anatomical left side."
)


class InvalidCaptureContextError(ValueError):
    pass


def normalize_handedness(value: str | None) -> str:
    raw = (value or HANDEDNESS_UNKNOWN).strip().upper()
    if raw not in HANDEDNESS_VALUES:
        raise InvalidCaptureContextError(
            f"Unsupported handedness '{value}'. Allowed: {', '.join(HANDEDNESS_VALUES)}"
        )
    return raw


def normalize_camera_view(value: str | None) -> str:
    raw = (value or CAMERA_VIEW_UNKNOWN).strip().upper()
    if raw not in CAMERA_VIEW_VALUES:
        raise InvalidCaptureContextError(
            f"Unsupported camera_view '{value}'. Allowed: {', '.join(CAMERA_VIEW_VALUES)}"
        )
    return raw


def capture_context_warnings(handedness: str, camera_view: str) -> list[str]:
    warnings: list[str] = []
    if handedness == HANDEDNESS_UNKNOWN:
        warnings.append(WARNING_HANDEDNESS_UNKNOWN)
    if camera_view == CAMERA_VIEW_FRONT:
        warnings.append(WARNING_CAMERA_VIEW_FRONT)
    elif camera_view == CAMERA_VIEW_REAR:
        warnings.append(WARNING_CAMERA_VIEW_REAR)
    return warnings


def profile_handedness(handedness: str) -> str | None:
    """Reference-profile axis value (UNKNOWN → wildcard)."""
    return None if handedness == HANDEDNESS_UNKNOWN else handedness


def profile_camera_view(camera_view: str) -> str | None:
    return None if camera_view == CAMERA_VIEW_UNKNOWN else camera_view


def _swapped_name(name: str) -> str:
    if name.startswith("left_"):
        return "right_" + name[len("left_") :]
    if name.startswith("right_"):
        return "left_" + name[len("right_") :]
    return name


def swap_left_right(sequence: PoseSequence) -> PoseSequence:
    """Return a copy with every ``left_*`` / ``right_*`` keypoint label swapped."""
    frames = [
        PoseFrame(
            frame_index=f.frame_index,
            timestamp=f.timestamp,
            keypoints={_swapped_name(n): kp for n, kp in f.keypoints.items()},
        )
        for f in sequence.frames
    ]
    return PoseSequence(video=sequence.video, frames=frames)
