"""Picture boundaries and metric mappings for the coach rule builder.

Every picture value below is an unvalidated prior: it fixes what each picture
shows and where its boundary sits, not what good technique is. The frontend
draws each picture from these same values.
"""

from __future__ import annotations

from dataclasses import dataclass

# Moments a coach can pick, in stroke order.
MOMENT_PREPARATION = "preparation"
MOMENT_BACKSWING_END = "backswing_end"
MOMENT_CONTACT = "contact"
MOMENT_FOLLOW_THROUGH = "follow_through"
MOMENTS: dict[str, str] = {
    MOMENT_PREPARATION: "Getting ready",
    MOMENT_BACKSWING_END: "Racket back",
    MOMENT_CONTACT: "The hit",
    MOMENT_FOLLOW_THROUGH: "Follow-through",
}

PART_ELBOW = "elbow"
PART_KNEES = "knees"
PART_HAND_HEIGHT = "hand_height"
PART_SHOULDER = "shoulder"
BODY_PARTS: dict[str, str] = {
    PART_ELBOW: "Hitting arm (elbow)",
    PART_KNEES: "Knees",
    PART_HAND_HEIGHT: "Height of the hit",
    PART_SHOULDER: "Shoulder",
}

UNIT_DEG = "deg"
# Wrist height above the hitting-side shoulder, in torso lengths (vertical
# shoulder-to-hip distance on the same frame), so camera distance cancels out.
UNIT_TORSO_ABOVE_SHOULDER = "torso_lengths_above_shoulder"


@dataclass(frozen=True, slots=True)
class BoundaryPicture:
    id: str
    label: str
    value: float


@dataclass(frozen=True, slots=True)
class BoundarySet:
    id: str
    unit: str
    pictures: tuple[BoundaryPicture, ...]

    def picture(self, picture_id: str) -> BoundaryPicture | None:
        return next((p for p in self.pictures if p.id == picture_id), None)


BOUNDARY_SETS: dict[str, BoundarySet] = {
    "elbow_angle": BoundarySet(
        id="elbow_angle",
        unit=UNIT_DEG,
        pictures=(
            BoundaryPicture("very_bent", "Very bent", 100.0),  # unvalidated prior
            BoundaryPicture("bent", "Bent", 120.0),  # unvalidated prior
            BoundaryPicture("slightly_bent", "Slightly bent", 140.0),  # unvalidated prior
            BoundaryPicture("nearly_straight", "Nearly straight", 160.0),  # unvalidated prior
            BoundaryPicture("straight", "Straight", 180.0),  # unvalidated prior
        ),
    ),
    "knee_angle": BoundarySet(
        id="knee_angle",
        unit=UNIT_DEG,
        pictures=(
            BoundaryPicture("deep_bend", "Deep bend", 100.0),  # unvalidated prior
            BoundaryPicture("bent", "Bent", 120.0),  # unvalidated prior
            BoundaryPicture("slightly_bent", "Slightly bent", 140.0),  # unvalidated prior
            BoundaryPicture("nearly_straight", "Nearly straight", 160.0),  # unvalidated prior
            BoundaryPicture("straight", "Straight", 180.0),  # unvalidated prior
        ),
    ),
    "hand_height": BoundarySet(
        id="hand_height",
        unit=UNIT_TORSO_ABOVE_SHOULDER,
        pictures=(
            BoundaryPicture("below_shoulder", "Below the shoulder", -0.3),  # unvalidated prior
            BoundaryPicture("shoulder", "Shoulder height", 0.0),  # unvalidated prior
            BoundaryPicture("head", "Head height", 0.35),  # unvalidated prior
            BoundaryPicture("above_head", "Above the head", 0.7),  # unvalidated prior
            BoundaryPicture("full_reach", "Full reach", 1.1),  # unvalidated prior
        ),
    ),
}

FLAG_BELOW = "flag_below"
FLAG_ABOVE = "flag_above"

# How the measurement is taken for a clip.
MEASURE_ELBOW_AT_HIT = "elbow_angle_at_hit"
MEASURE_HAND_HEIGHT_AT_HIT = "hand_height_at_hit"
MEASURE_HAND_HEIGHT_AT_BACKSWING_END = "hand_height_at_backswing_end"
MEASURE_PREPARATION_KNEE = "preparation_knee_metric"

# Coach label questions (the "Do you see these problems?" step when reviewing clips).
QUESTION_LOW_CONTACT = "low_contact"
QUESTION_BENT_ELBOW = "bent_elbow"
QUESTION_LEG_DRIVE = "leg_drive"
QUESTION_STIFF_KNEE = "stiff_knee"
QUESTION_LOW_RACKET_PREP = "low_racket_prep"
LABEL_QUESTIONS: dict[str, str] = {
    QUESTION_LOW_CONTACT: "Hit too low",
    QUESTION_BENT_ELBOW: "Arm bent at the hit",
    QUESTION_LEG_DRIVE: "No push from the legs",
    QUESTION_STIFF_KNEE: "Legs too straight while getting ready",
    QUESTION_LOW_RACKET_PREP: "Racket not up in time",
}


@dataclass(frozen=True, slots=True)
class RuleTarget:
    """Existing metric and measurement moment a coach rule is checked against."""

    metric_id: str
    metric_label: str
    measure: str
    boundary_set: str
    direction: str
    label_question: str
    # The question shown above the pictures and the line under it.
    prompt: str
    flag_hint: str
    # Plain-words name of the problem, e.g. for "Catches 9 of your 9 bent-arm clips".
    problem_noun: str


RULE_TARGETS: dict[tuple[str, str], RuleTarget] = {
    (PART_ELBOW, MOMENT_CONTACT): RuleTarget(
        metric_id="contact_elbow_angle_deg",
        metric_label="Elbow angle at the hit frame",
        measure=MEASURE_ELBOW_AT_HIT,
        boundary_set="elbow_angle",
        direction=FLAG_BELOW,
        label_question=QUESTION_BENT_ELBOW,
        prompt="Which is the most bent arm you would still accept?",
        flag_hint="Anything more bent than your choice will be flagged.",
        problem_noun="bent-arm",
    ),
    (PART_KNEES, MOMENT_PREPARATION): RuleTarget(
        metric_id="preparation_knee_angle_deg",
        metric_label="Mean knee angle while getting ready",
        measure=MEASURE_PREPARATION_KNEE,
        boundary_set="knee_angle",
        direction=FLAG_ABOVE,
        label_question=QUESTION_STIFF_KNEE,
        prompt="Which is the straightest knee you would still accept while getting ready?",
        flag_hint="Anything straighter than your choice will be flagged.",
        problem_noun="straight-legs",
    ),
    (PART_HAND_HEIGHT, MOMENT_CONTACT): RuleTarget(
        metric_id="contact_window_min_wrist_y_normalized",
        metric_label="Highest wrist within 2 frames of the hit, above the shoulder",
        measure=MEASURE_HAND_HEIGHT_AT_HIT,
        boundary_set="hand_height",
        direction=FLAG_BELOW,
        label_question=QUESTION_LOW_CONTACT,
        prompt="Which is the lowest hit you would still accept?",
        flag_hint="Any hit lower than your choice will be flagged.",
        problem_noun="low-hit",
    ),
    (PART_HAND_HEIGHT, MOMENT_BACKSWING_END): RuleTarget(
        metric_id="backswing_end_wrist_y_normalized",
        metric_label="Wrist above the shoulder at the end of the backswing",
        measure=MEASURE_HAND_HEIGHT_AT_BACKSWING_END,
        boundary_set="hand_height",
        direction=FLAG_BELOW,
        label_question=QUESTION_LOW_RACKET_PREP,
        prompt="Which is the lowest racket-back position you would still accept?",
        flag_hint="Any hand lower than your choice will be flagged.",
        problem_noun="late-racket",
    ),
}

# Highest wrist is taken within ±N frames of the coach-marked hit, matching
# the live contact-height measurement.
HIT_WRIST_WINDOW_FRAMES = 2  # unvalidated prior

IMPORTANCE_TIP = "tip"
IMPORTANCE_WORTH_FIXING = "worth_fixing"
IMPORTANCE_MUST_FIX_FIRST = "must_fix_first"
IMPORTANCE_LABELS: dict[str, str] = {
    IMPORTANCE_TIP: "A small tip",
    IMPORTANCE_WORTH_FIXING: "Worth fixing",
    IMPORTANCE_MUST_FIX_FIRST: "Must fix first",
}
SEVERITY_CAP_BY_IMPORTANCE: dict[str, str] = {
    IMPORTANCE_TIP: "MINOR",
    IMPORTANCE_WORTH_FIXING: "MODERATE",
    IMPORTANCE_MUST_FIX_FIRST: "MAJOR",
}

AGREEMENT_SEPARATES_WELL = "separates_well"
AGREEMENT_OVERLAPS = "overlaps"
AGREEMENT_NOT_ENOUGH_DATA = "not_enough_data"
AGREEMENT_LABELS: dict[str, str] = {
    AGREEMENT_SEPARATES_WELL: "Separates well",
    AGREEMENT_OVERLAPS: "Overlaps",
    AGREEMENT_NOT_ENOUGH_DATA: "Not enough data",
}
SEPARATES_WELL_MIN_BALANCED_ACCURACY = 0.80  # unvalidated prior
AGREEMENT_MIN_CLIPS_PER_CLASS = 5  # unvalidated prior


def rule_target(body_part: str, moment: str) -> RuleTarget | None:
    return RULE_TARGETS.get((body_part, moment))


def unsupported_reason(body_part: str, moment: str) -> str:
    part = BODY_PARTS.get(body_part, body_part)
    when = MOMENTS.get(moment, moment).lower()
    supported = [MOMENTS[m].lower() for (p, m) in RULE_TARGETS if p == body_part]
    if not supported:
        return f"We don't measure {part.lower()} yet, so this rule can't be checked or saved."
    return (
        f"We don't have a measurement for {part.lower()} at {when}. "
        f"For this body part, pick: {', '.join(supported)}."
    )
