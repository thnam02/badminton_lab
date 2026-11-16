"""Filtering rules for MultiSense clips (existing quality signals only)."""

from __future__ import annotations

from app.labelling.multisense.filter import (
    REASON_NO_SWING,
    REASON_PLAYER_CUTOFF_OR_SMALL,
    REASON_RACKET_ARM_HIDDEN,
    REASON_WRONG_PERSON,
    drop_reason,
)


def test_drop_when_no_swing():
    assert drop_reason({"quality": {}, "evidence": {"swing_count": 0}}) == REASON_NO_SWING
    assert drop_reason({"quality": {}, "evidence": {}}) == REASON_NO_SWING


def test_keep_when_contact_present_even_if_swing_count_missing():
    assert (
        drop_reason({"quality": {"warnings": []}, "evidence": {"contact": {"frame_index": 12}}})
        is None
    )


def test_drop_player_too_small_or_cut_off():
    assert (
        drop_reason(
            {
                "quality": {"warnings": ["SMALL_PLAYER_SIZE"], "metrics": {}},
                "evidence": {"swing_count": 1, "contact": {"frame_index": 1}},
            }
        )
        == REASON_PLAYER_CUTOFF_OR_SMALL
    )
    assert (
        drop_reason(
            {
                "quality": {"warnings": ["LOW_FULL_BODY_COVERAGE"], "metrics": {}},
                "evidence": {"swing_count": 1, "contact": {"frame_index": 1}},
            }
        )
        == REASON_PLAYER_CUTOFF_OR_SMALL
    )


def test_drop_racket_arm_hidden_at_contact():
    assert (
        drop_reason(
            {
                "quality": {"warnings": ["LOW_RACKET_ARM_AT_CONTACT"], "metrics": {}},
                "evidence": {"swing_count": 1, "contact": {"frame_index": 1}},
            }
        )
        == REASON_RACKET_ARM_HIDDEN
    )


def test_drop_wrong_person():
    assert (
        drop_reason(
            {
                "quality": {"warnings": ["WRONG_PLAYER_POSSIBLE"], "metrics": {}},
                "evidence": {"swing_count": 1, "contact": {"frame_index": 1}},
            }
        )
        == REASON_WRONG_PERSON
    )
