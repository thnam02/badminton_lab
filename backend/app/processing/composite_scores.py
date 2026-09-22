"""Composite technique scores (chain / power / base) from stroke metrics.

Canonical formulas (product-specified). Ideal ranges / tolerances marked as
unvalidated priors unless noted as an existing technique threshold.
"""

from __future__ import annotations

from typing import Any


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def range_score(
    value: float | None,
    *,
    ideal_min: float,
    ideal_max: float,
    tolerance: float,
) -> float | None:
    """1.0 inside [ideal_min, ideal_max]; linear falloff over ``tolerance`` outside."""
    if value is None:
        return None
    v = float(value)
    if ideal_min <= v <= ideal_max:
        return 1.0
    if tolerance <= 0.0:
        return 0.0
    if v < ideal_min:
        return clip((v - (ideal_min - tolerance)) / tolerance)
    return clip(((ideal_max + tolerance) - v) / tolerance)


def weighted_average(*pairs: tuple[float | None, float]) -> float | None:
    """Weighted mean; missing terms are dropped and remaining weights renormalize."""
    present = [(v, w) for v, w in pairs if v is not None]
    if not present:
        return None
    total_weight = sum(w for _, w in present)
    if total_weight <= 0.0:
        return None
    return sum(float(v) * float(w) for v, w in present) / total_weight


def _order_score(kinetic_chain_order: str | None) -> float | None:
    if not kinetic_chain_order:
        return None
    order = str(kinetic_chain_order).strip().lower()
    # Unvalidated prior: full proximal→distal sequence scores 1.0.
    if order == "hip_shoulder_elbow":
        return 1.0
    if order in {"hip_shoulder", "shoulder_elbow", "hip_elbow"}:
        return 0.55  # unvalidated prior
    return 0.25  # unvalidated prior


def _timing_score(metrics: dict[str, Any]) -> float | None:
    hs = metrics.get("kinetic_chain_hip_shoulder_gap_frames")
    se = metrics.get("kinetic_chain_shoulder_elbow_gap_frames")
    elbow_off = metrics.get("peak_elbow_omega_offset_frames")
    hs_s = range_score(
        float(hs) if hs is not None else None,
        ideal_min=1.0,  # unvalidated prior
        ideal_max=10.0,  # unvalidated prior
        tolerance=8.0,  # unvalidated prior
    )
    se_s = range_score(
        float(se) if se is not None else None,
        ideal_min=1.0,  # unvalidated prior
        ideal_max=10.0,  # unvalidated prior
        tolerance=8.0,  # unvalidated prior
    )
    elbow_s = range_score(
        float(elbow_off) if elbow_off is not None else None,
        ideal_min=-6.0,  # unvalidated prior
        ideal_max=-1.0,  # unvalidated prior
        tolerance=5.0,  # unvalidated prior
    )
    return weighted_average((hs_s, 0.35), (se_s, 0.35), (elbow_s, 0.30))


def _leg_drive_score(metrics: dict[str, Any]) -> float | None:
    """Smash exposes knee_contribution_deg; clear does not — term may be absent."""
    knee = metrics.get("knee_contribution_deg")
    if knee is None:
        return None
    return range_score(
        float(knee),
        ideal_min=12.0,  # unvalidated prior
        ideal_max=40.0,  # unvalidated prior
        tolerance=15.0,  # unvalidated prior
    )


def _trunk_rotation_score(metrics: dict[str, Any]) -> float | None:
    trunk = metrics.get("peak_trunk_rotation_deg")
    if trunk is None:
        return None
    return range_score(
        float(trunk),
        ideal_min=15.0,  # unvalidated prior
        ideal_max=45.0,  # unvalidated prior
        tolerance=20.0,  # unvalidated prior
    )


def chain_score(metrics: dict[str, Any]) -> float | None:
    """Kinetic-chain quality: order, timing, leg drive, trunk rotation (X-factor)."""
    return weighted_average(
        (_order_score(metrics.get("kinetic_chain_order")), 0.40),  # unvalidated prior
        (_timing_score(metrics), 0.30),  # unvalidated prior
        (_leg_drive_score(metrics), 0.15),  # unvalidated prior
        (_trunk_rotation_score(metrics), 0.15),  # unvalidated prior
    )


def power_score(
    peak_speed_percentile: float | None,
    follow_through_ratio: float | None,
    accel_fraction: float | None,
) -> float | None:
    """Identical formula shape for smash and clear.

    ``peak_speed_percentile`` is expected in [0, 1] (fraction of reference CDF).
    ``follow_through_ratio`` / ``accel_fraction`` come from metrics shared by both
    stroke types (``follow_through_speed_ratio``, ``acceleration_phase_fraction``).
    """
    speed_score = (
        clip(float(peak_speed_percentile))
        if peak_speed_percentile is not None
        else None
    )
    retention_score = (
        clip(float(follow_through_ratio) / 0.6)
        if follow_through_ratio is not None
        else None
    )
    timing_efficiency_score = range_score(
        float(accel_fraction) if accel_fraction is not None else None,
        ideal_min=0.30,  # unvalidated prior
        ideal_max=0.50,  # unvalidated prior
        tolerance=0.15,  # unvalidated prior
    )
    return weighted_average(
        (speed_score, 0.5),
        (retention_score, 0.3),
        (timing_efficiency_score, 0.2),
    )


def base_score(
    prep_knee_angle: float | None,
    contact_wrist_y: float | None,
) -> float | None:
    """Preparation knee load + contact height.

    ``contact_wrist_y`` is image y (lower ⇒ higher contact). The 0.58 anchor is the
    real ``technique_max_contact_wrist_y_normalized`` threshold (higher_is_better=False);
    the 0.20 divisor is still an unvalidated range-width guess.
    """
    knee_load_score = range_score(
        float(prep_knee_angle) if prep_knee_angle is not None else None,
        ideal_min=110.0,  # unvalidated prior
        ideal_max=140.0,  # unvalidated prior
        tolerance=20.0,  # unvalidated prior
    )
    if contact_wrist_y is None:
        contact_height_score = None
    else:
        # 0.58 = existing technique threshold; 0.20 width = unvalidated guess.
        contact_height_score = clip((0.58 - float(contact_wrist_y)) / 0.2)
    return weighted_average((knee_load_score, 0.5), (contact_height_score, 0.5))


def _normalize_percentile_01(raw: float | None) -> float | None:
    """Accept 0–1 fractions or 0–100 percentile ranks."""
    if raw is None:
        return None
    v = float(raw)
    if v > 1.0:
        v = v / 100.0
    return clip(v)


def resolve_peak_speed_percentile_01(
    metrics: dict[str, Any],
    *,
    peak_speed_percentile: float | None = None,
) -> float | None:
    """Resolve speed term for power_score.

    Prefer an explicit real percentile (0–1 or 0–100). If none is supplied,
    fall back to the min-max stopgap from ``peak_wrist_speed`` (see
    ``stopgap_speed_score_from_peak_wrist``).
    """
    if peak_speed_percentile is not None:
        return _normalize_percentile_01(peak_speed_percentile)
    if metrics.get("peak_speed_percentile") is not None:
        return _normalize_percentile_01(metrics.get("peak_speed_percentile"))
    return stopgap_speed_score_from_peak_wrist(metrics.get("peak_wrist_speed"))


# ---------------------------------------------------------------------------
# STOPGAP — NOT a real percentile / NOT a validated population distribution.
#
# Observed peak_wrist_speed on 16 local analysis clips with that field
# (2026-09-22 workspace outputs): min ≈ 1.62, max ≈ 4.33 (norm image units/s).
# Padded placeholder bounds below are for **individual-analysis relative
# scoring only**. Replace once reference profiles include peak_wrist_speed.
# Do NOT use this to make cross-population claims.
# ---------------------------------------------------------------------------
_PEAK_WRIST_SPEED_STOPGAP_MIN = 1.4
_PEAK_WRIST_SPEED_STOPGAP_MAX = 4.6


def stopgap_speed_score_from_peak_wrist(peak_wrist_speed: float | None) -> float | None:
    """Min-max normalize peak_wrist_speed into [0, 1] against the stopgap range.

    STOPGAP: not a real percentile. Must be replaced when reference profiles
    include peak_wrist_speed. Individual relative scoring only.
    """
    if peak_wrist_speed is None:
        return None
    span = _PEAK_WRIST_SPEED_STOPGAP_MAX - _PEAK_WRIST_SPEED_STOPGAP_MIN
    if span <= 1e-9:
        return None
    return clip(
        (float(peak_wrist_speed) - _PEAK_WRIST_SPEED_STOPGAP_MIN) / span
    )


def compute_composite_scores(
    metrics: dict[str, Any],
    *,
    peak_speed_percentile: float | None = None,
) -> dict[str, Any]:
    """Return coaching-facing composite scores.

    ``available`` is False when every top-level score is None (insufficient inputs
    on a current-version analysis). Downstream should treat ``available=False``
    the same as a missing/pre-1.1.0 field — never coerce to 0.
    """
    chain = chain_score(metrics)
    speed_pct = resolve_peak_speed_percentile_01(
        metrics, peak_speed_percentile=peak_speed_percentile
    )
    power = power_score(
        speed_pct,
        metrics.get("follow_through_speed_ratio"),
        metrics.get("acceleration_phase_fraction"),
    )
    base = base_score(
        metrics.get("preparation_knee_angle_deg"),
        metrics.get("contact_wrist_y_normalized"),
    )
    available = any(s is not None for s in (chain, power, base))
    return {
        "available": available,
        "chain_score": chain,
        "power_score": power,
        "base_score": base,
        "components": {
            "chain": {
                "order": _order_score(metrics.get("kinetic_chain_order")),
                "timing": _timing_score(metrics),
                "leg_drive": _leg_drive_score(metrics),
                "trunk_rotation": _trunk_rotation_score(metrics),
            },
            "power": {
                "peak_speed_percentile": speed_pct,
                "speed_score_source": (
                    "explicit_percentile"
                    if peak_speed_percentile is not None
                    or metrics.get("peak_speed_percentile") is not None
                    else (
                        "stopgap_minmax_peak_wrist_speed"
                        if metrics.get("peak_wrist_speed") is not None
                        else None
                    )
                ),
                "follow_through_ratio": metrics.get("follow_through_speed_ratio"),
                "accel_fraction": metrics.get("acceleration_phase_fraction"),
            },
            "base": {
                "prep_knee_angle": metrics.get("preparation_knee_angle_deg"),
                "contact_wrist_y": metrics.get("contact_wrist_y_normalized"),
            },
        },
        "notes": (
            "Composite scores use canonical formulas; most ranges/weights are "
            "unvalidated priors. contact_wrist_y: lower y = higher contact; "
            "height score anchors on technique threshold 0.58 with unvalidated "
            "0.20 width. When no real peak_speed_percentile is supplied, POWER "
            "uses a STOPGAP min-max of peak_wrist_speed on a small local clip "
            "set (not a population percentile) — replace once profiles include "
            "peak_wrist_speed."
        ),
    }
