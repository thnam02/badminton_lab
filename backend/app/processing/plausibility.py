"""Physiological plausibility gate for stroke metrics.

Values outside the ranges below are treated as tracking errors: they are
removed from the metrics object (so rules and composite scores never see
them), listed in ``implausible_measurements`` and flagged with
``IMPLAUSIBLE_MEASUREMENT``. All ranges are unvalidated priors.
"""

from __future__ import annotations

import math
from typing import Any

WARNING_IMPLAUSIBLE_MEASUREMENT = "IMPLAUSIBLE_MEASUREMENT"

# Joint group → inclusive plausible range (degrees).
PLAUSIBLE_RANGES_DEG: dict[str, tuple[float, float]] = {
    "elbow": (60.0, 180.0),  # unvalidated prior
    "knee": (60.0, 180.0),  # unvalidated prior
    "shoulder": (0.0, 180.0),  # unvalidated prior
    "trunk_rotation": (0.0, 90.0),  # unvalidated prior
}

# Metric field → joint group whose range applies.
GATED_METRICS: dict[str, str] = {
    "contact_elbow_angle_deg": "elbow",
    "preparation_elbow_angle_deg": "elbow",
    "backswing_min_elbow_angle_deg": "elbow",
    "contact_knee_angle_deg": "knee",
    "preparation_knee_angle_deg": "knee",
    "backswing_min_knee_angle_deg": "knee",
    "contact_shoulder_angle_deg": "shoulder",
    "peak_trunk_rotation_deg": "trunk_rotation",
}

# Derived metric → inputs; dropped when any input is implausible.
DERIVED_METRICS: dict[str, tuple[str, ...]] = {
    "knee_contribution_deg": ("contact_knee_angle_deg", "preparation_knee_angle_deg"),
}


def apply_plausibility_gate(metrics: Any) -> None:
    """Null out implausible metric values in place and record why."""
    dropped: list[dict[str, Any]] = []
    for field_name, group in GATED_METRICS.items():
        if not hasattr(metrics, field_name):
            continue
        value = getattr(metrics, field_name)
        if value is None:
            continue
        lo, hi = PLAUSIBLE_RANGES_DEG[group]
        if math.isfinite(float(value)) and lo <= float(value) <= hi:
            continue
        setattr(metrics, field_name, None)
        dropped.append(
            {
                "metric": field_name,
                "value": float(value),
                "plausible_min": lo,
                "plausible_max": hi,
                "reason": f"{group} angle outside plausible range",
            }
        )

    dropped_names = {d["metric"] for d in dropped}
    for field_name, inputs in DERIVED_METRICS.items():
        if not hasattr(metrics, field_name) or getattr(metrics, field_name) is None:
            continue
        bad = [name for name in inputs if name in dropped_names]
        if not bad:
            continue
        dropped.append(
            {
                "metric": field_name,
                "value": float(getattr(metrics, field_name)),
                "plausible_min": None,
                "plausible_max": None,
                "reason": f"derived from implausible {', '.join(bad)}",
            }
        )
        setattr(metrics, field_name, None)

    metrics.implausible_measurements = dropped
    metrics.measurement_warnings = [WARNING_IMPLAUSIBLE_MEASUREMENT] if dropped else []
