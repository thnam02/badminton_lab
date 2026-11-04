# Known issues

Open problems that are logged but intentionally not fixed yet. Technique rule
thresholds are frozen until new coach-labelled side-view clips exist.

## Acceleration phase can be far too long (clip F)

- **Logged:** 2026-11-04 · **Status:** open, no fix applied
- **Clip:** `c8eac0f3…` (forehand clear, replay label `F_c8eac0f3`)
- **Observed phases (frames):** preparation 0–30, backswing 31–33 (3 frames),
  acceleration 34–68 (**35 frames**), contact 69, follow-through 70–103.
  At ~30 fps the "acceleration" phase spans more than a second, while the
  backswing is only 3 frames.
- **Cause (suspected):** `processing/phases.py` walks back from contact while
  relative wrist speed stays ≥ 0.35 (or rising with elbow ω), so a slow,
  continuous arm lift is absorbed into acceleration instead of backswing.
- **Impact:**
  - Kinetic-chain timing (display only) searches backswing end → contact, so on
    F it still finds peaks 20–27 frames before contact (preparation-like motion,
    not the hit).
  - `acceleration_phase_fraction` (0.5 on F) and the Power score's timing term.
  - Loading-window minimum knee angle for leg drive (backswing start → contact).
- **Next step:** review phase boundaries against new side-view clips with
  coach-marked backswing / acceleration / contact frames before changing
  `phases.py` thresholds.
