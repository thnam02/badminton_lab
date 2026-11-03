"""Single source of thresholds for the tiered technique rule set.

Tier 1 — principle-based rules (relative body landmarks / timing).
Tier 2 — angle hints, evaluated only for side-on camera views.
Tier 3 — display-only metrics; never produce an issue.

Every threshold below is an unvalidated prior: it has not been fitted to
coach-labelled data. Bump ``TIERED_RULES_VERSION`` whenever a threshold,
base status, cap or rule membership changes.
"""

from __future__ import annotations

from dataclasses import dataclass

TIERED_RULES_VERSION = "tiered_rules_v1"

TIER_PRINCIPLE = 1
TIER_HINT = 2
TIER_DISPLAY = 3

# Tier 1 codes
KINETIC_CHAIN_ORDER = "KINETIC_CHAIN_ORDER"
LOW_CONTACT_POINT = "LOW_CONTACT_POINT"
LATE_ELBOW_ACCELERATION = "LATE_ELBOW_ACCELERATION"
LOW_RACKET_PREPARATION = "LOW_RACKET_PREPARATION"
# Tier 2 codes
BENT_ELBOW_AT_CONTACT = "BENT_ELBOW_AT_CONTACT"
LIMITED_LEG_DRIVE = "LIMITED_LEG_DRIVE"
STIFF_PREPARATION_KNEE = "STIFF_PREPARATION_KNEE"

TIER_BY_CODE: dict[str, int] = {
    KINETIC_CHAIN_ORDER: TIER_PRINCIPLE,
    LOW_CONTACT_POINT: TIER_PRINCIPLE,
    LATE_ELBOW_ACCELERATION: TIER_PRINCIPLE,
    LOW_RACKET_PREPARATION: TIER_PRINCIPLE,
    BENT_ELBOW_AT_CONTACT: TIER_HINT,
    LIMITED_LEG_DRIVE: TIER_HINT,
    STIFF_PREPARATION_KNEE: TIER_HINT,
}

# Tier 2 rules run only for this declared camera view.
TIER_HINT_CAMERA_VIEW = "SIDE"


@dataclass(frozen=True, slots=True)
class TieredRulesConfig:
    # Tier 1: flag when the elbow |ω| peak precedes the shoulder peak by more
    # than this many frames (swing window).
    chain_elbow_lead_max_frames: int = 1  # unvalidated prior
    # Tier 1: flag when contact wrist y exceeds nose y by more than this margin
    # (normalized image y grows downward, so larger y = lower).
    contact_wrist_below_nose_margin: float = 0.0  # unvalidated prior
    # Tier 1: flag when the elbow |ω| peak is more than this many frames after contact.
    late_elbow_peak_max_frames: int = 2  # unvalidated prior
    # Tier 1: flag when backswing-end wrist y exceeds shoulder y by more than this margin.
    backswing_wrist_below_shoulder_margin: float = 0.0  # unvalidated prior

    # Tier 2 (SIDE view only): flag strictly below / above these values.
    smash_min_contact_elbow_deg: float = 130.0  # unvalidated prior
    clear_min_contact_elbow_deg: float = 140.0  # unvalidated prior
    min_leg_drive_deg: float = 5.0  # unvalidated prior
    max_preparation_knee_deg: float = 170.0  # unvalidated prior

    # Base status when a rule fires (before the severity cap).
    kinetic_chain_order_status: str = "MODERATE"  # unvalidated prior
    low_contact_point_status: str = "MODERATE"  # unvalidated prior
    late_elbow_acceleration_status: str = "MINOR"
    low_racket_preparation_status: str = "MINOR"
    tier_hint_status: str = "MINOR"

    # Severity caps while the selected reference profile is provisional/seeded.
    tier1_cap_provisional: str = "MODERATE"
    tier2_cap_provisional: str = "MINOR"
    # Caps once a VALIDATED, non-provisional profile is selected.
    tier1_cap_validated: str = "MAJOR"
    tier2_cap_validated: str = "MINOR"


# Tier 3: (metric field, label, unit) shown for context only.
TIER_DISPLAY_METRICS: tuple[tuple[str, str, str], ...] = (
    ("contact_shoulder_angle_deg", "Shoulder angle at contact", "deg"),
    ("peak_trunk_rotation_deg", "Trunk rotation (2D)", "deg"),
    ("preparation_elbow_angle_deg", "Preparation elbow angle", "deg"),
    ("follow_through_speed_ratio", "Follow-through speed ratio", ""),
    ("peak_wrist_speed", "Peak wrist speed", ""),
)


def default_tiered_rules_config() -> TieredRulesConfig:
    return TieredRulesConfig()
