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

# v4: thresholds unchanged; angles are measured on pixel-scaled keypoints.
TIERED_RULES_VERSION = "tiered_rules_v4"

TIER_PRINCIPLE = 1
TIER_HINT = 2
TIER_DISPLAY = 3

# Retired as a rule (now the Tier 3 kinetic-chain timing display metric); the
# code stays so older analyses keep their titles.
KINETIC_CHAIN_ORDER = "KINETIC_CHAIN_ORDER"
# Tier 1 codes
LOW_CONTACT_POINT = "LOW_CONTACT_POINT"
LATE_ELBOW_ACCELERATION = "LATE_ELBOW_ACCELERATION"
LOW_RACKET_PREPARATION = "LOW_RACKET_PREPARATION"
# Tier 2 codes
BENT_ELBOW_AT_CONTACT = "BENT_ELBOW_AT_CONTACT"
LIMITED_LEG_DRIVE = "LIMITED_LEG_DRIVE"
STIFF_PREPARATION_KNEE = "STIFF_PREPARATION_KNEE"

TIER_BY_CODE: dict[str, int] = {
    LOW_CONTACT_POINT: TIER_PRINCIPLE,
    LATE_ELBOW_ACCELERATION: TIER_PRINCIPLE,
    LOW_RACKET_PREPARATION: TIER_PRINCIPLE,
    BENT_ELBOW_AT_CONTACT: TIER_HINT,
    LIMITED_LEG_DRIVE: TIER_HINT,
    STIFF_PREPARATION_KNEE: TIER_HINT,
}

# Metric fields each rule needs; a rule whose inputs are missing or excluded
# by the plausibility gate is reported as not checked.
RULE_INPUTS: dict[str, tuple[str, ...]] = {
    LOW_CONTACT_POINT: ("contact_window_min_wrist_y_normalized", "contact_nose_y_normalized"),
    LATE_ELBOW_ACCELERATION: ("swing_peak_elbow_omega_offset_frames",),
    LOW_RACKET_PREPARATION: (
        "backswing_end_wrist_y_normalized",
        "backswing_end_shoulder_y_normalized",
    ),
    BENT_ELBOW_AT_CONTACT: ("contact_elbow_angle_deg",),
    LIMITED_LEG_DRIVE: ("knee_contribution_deg",),
    STIFF_PREPARATION_KNEE: ("preparation_knee_angle_deg",),
}

# What each rule checks, for "not checked" explanations.
RULE_CHECK_LABELS: dict[str, str] = {
    LOW_CONTACT_POINT: "Contact height",
    LATE_ELBOW_ACCELERATION: "Elbow acceleration timing",
    LOW_RACKET_PREPARATION: "Racket preparation height",
    BENT_ELBOW_AT_CONTACT: "Elbow angle at contact",
    LIMITED_LEG_DRIVE: "Leg drive",
    STIFF_PREPARATION_KNEE: "Preparation knee bend",
}

# Tier 2 rules run only for this declared camera view.
TIER_HINT_CAMERA_VIEW = "SIDE"

# LOW_CONTACT_POINT uses the highest wrist within ±N frames of contact.
CONTACT_WRIST_WINDOW_FRAMES = 2  # unvalidated prior


@dataclass(frozen=True, slots=True)
class TieredRulesConfig:
    # Tier 1: flag when the highest wrist y near contact exceeds nose y by more
    # than this margin (normalized image y grows downward, so larger y = lower).
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


LOW_RELIABILITY_2D_NOTE = "Low reliability in 2D video."

# Tier 3: (metric field, label, unit, note) shown for context only.
TIER_DISPLAY_METRICS: tuple[tuple[str, str, str, str | None], ...] = (
    ("contact_shoulder_angle_deg", "Shoulder angle at contact", "deg", None),
    ("peak_trunk_rotation_deg", "Trunk rotation (2D)", "deg", None),
    ("preparation_elbow_angle_deg", "Preparation elbow angle", "deg", None),
    ("follow_through_speed_ratio", "Follow-through speed ratio", "", None),
    ("peak_wrist_speed", "Peak wrist speed", "", None),
    (
        "peak_wrist_speed_body_norm",
        "Peak wrist speed (torso lengths per second)",
        "torso lengths/s",
        None,
    ),
    (
        "swing_elbow_lead_over_shoulder_frames",
        "Arm-elevation timing (elbow peak lead over shoulder)",
        "frames",
        None,
    ),
    # Kinetic chain order (formerly the KINETIC_CHAIN_ORDER rule). Needs 3D
    # landmarks or coach-labelled data before it can become a rule again.
    (
        "acceleration_elbow_extension_lead_over_trunk_frames",
        "Kinetic chain timing (elbow extension lead over trunk turn, during the hit)",
        "frames",
        LOW_RELIABILITY_2D_NOTE,
    ),
    (
        "peak_trunk_rotation_velocity_deg_s",
        "Trunk rotation speed (during the hit)",
        "deg/s",
        LOW_RELIABILITY_2D_NOTE,
    ),
)


def default_tiered_rules_config() -> TieredRulesConfig:
    return TieredRulesConfig()
