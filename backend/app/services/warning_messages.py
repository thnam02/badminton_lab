"""User-facing sentences for pipeline warning codes.

Every warning code the pipeline can emit must appear either in
``WARNING_SENTENCES`` (shown to the user) or in ``INTERNAL_ONLY_WARNING_CODES``
(never shown). Anything else is dropped by the product API and logged.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

# Highest priority first.
WARNING_SENTENCES: dict[str, str] = {
    "NO_POSE_DETECTED": "We couldn't detect a player in this video.",
    "WRONG_PLAYER_POSSIBLE": (
        "We may have followed the wrong player. Check that the skeleton stays on you."
    ),
    "MULTIPLE_SWINGS_DETECTED": "We found {n} swings and analysed the one at {time}.",
    "LOW_RACKET_ARM_AT_CONTACT": (
        "Your racket arm was hard to see at contact, so arm measurements may be less accurate."
    ),
    "CONTACT_UNSTABLE_TRACKING": (
        "Body tracking jumped around near contact, so the contact moment may be off."
    ),
    "CONTACT_AMBIGUOUS_PEAKS": (
        "Your arm sped up twice in quick succession, so the contact moment may be a few frames off."
    ),
    "CONTACT_PEAK_NOT_OVERHEAD": (
        "Your hand wasn't above your shoulder at the analysed moment, so it may not be "
        "the overhead hit."
    ),
    "CONTACT_SPIKE_PEAK": (
        "The arm-speed peak used for contact was very brief, so the contact moment may be off."
    ),
    "LOW_POSE_CONFIDENCE": "Body tracking was uncertain, so some measurements may be less reliable.",
    "LOW_RACKET_ARM_VISIBILITY": "Your racket arm was often hidden or out of view.",
    "LOW_FULL_BODY_COVERAGE": "Parts of your body were out of frame. Keep your whole body in view.",
    "HIGH_MISSING_KEYPOINTS": "Some body points couldn't be tracked in many frames.",
    "HIGH_INTERPOLATED_KEYPOINTS": "Some body positions had to be filled in between frames.",
    "CAMERA_VIEW_FRONT": (
        "The video was filmed from the front, which makes some arm angles harder to measure."
    ),
    "CAMERA_VIEW_REAR": (
        "The video was filmed from behind, which makes some arm angles harder to measure."
    ),
    "SMALL_PLAYER_SIZE": "You appear small in the frame. Filming closer will help.",
    "UNSTABLE_CAMERA": "The camera moved during recording. A steady camera gives better results.",
    "LOW_FPS": "The video frame rate is low, so fast movements may be missed.",
    "LOW_RESOLUTION": "The video resolution is low, which limits tracking accuracy.",
    "HANDEDNESS_UNKNOWN": "Handedness wasn't specified, so we assumed you play right-handed.",
}

# Emitted on purpose but never shown as a warning (surfaced elsewhere in the UI).
INTERNAL_ONLY_WARNING_CODES: frozenset[str] = frozenset(
    {
        "CONTACT_NOT_VERIFIED_BY_SHUTTLE",
    }
)

_PRIORITY = {code: i for i, code in enumerate(WARNING_SENTENCES)}


def unmapped_warning_codes(codes: Iterable[Any]) -> list[str]:
    """Codes with neither a sentence nor an internal-only entry, in input order."""
    out: list[str] = []
    for c in codes:
        code = str(c)
        if code not in WARNING_SENTENCES and code not in INTERNAL_ONLY_WARNING_CODES:
            if code not in out:
                out.append(code)
    return out


def log_unmapped_warnings(codes: Iterable[Any], *, analysis: str) -> None:
    unknown = unmapped_warning_codes(codes)
    if unknown:
        logger.warning(
            "Analysis %s emitted warning codes with no user-facing mapping "
            "(they will be hidden): %s",
            analysis,
            ", ".join(unknown),
        )


def warning_sentences(codes: Iterable[Any], contact: dict[str, Any]) -> list[str]:
    """Plain-language sentences for mapped codes, highest priority first."""
    known = sorted(
        {str(c) for c in codes if str(c) in WARNING_SENTENCES},
        key=lambda c: _PRIORITY[c],
    )
    out: list[str] = []
    for code in known:
        template = WARNING_SENTENCES[code]
        if code == "MULTIPLE_SWINGS_DETECTED":
            n = contact.get("swing_count")
            when = contact.get("chosen_swing_timestamp")
            if n is None or when is None:
                continue
            template = template.format(n=int(n), time=format_timestamp(float(when)))
        out.append(template)
    return out


def format_timestamp(seconds: float) -> str:
    """Same m:ss.ss format as the frontend formatTimestamp."""
    s = max(0.0, seconds)
    m = int(s // 60)
    return f"{m}:{s - m * 60:05.2f}"
