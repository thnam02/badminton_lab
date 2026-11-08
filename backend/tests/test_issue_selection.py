"""Tests for deterministic coaching issue selection."""

from __future__ import annotations

from app.ai.issue_selection import select_top_issues


def test_select_top_issues_filters_insufficient_and_uncertain() -> None:
    issues = [
        {
            "code": "A",
            "severity": "HIGH",
            "status": "MAJOR",
            "combined_confidence": 0.9,
        },
        {
            "code": "B",
            "severity": "HIGH",
            "status": "INSUFFICIENT_EVIDENCE",
            "combined_confidence": 0.99,
            "uncertain": True,
        },
        {
            "code": "C",
            "severity": "LOW",
            "status": "MINOR",
            "combined_confidence": 0.5,
        },
    ]
    selected = select_top_issues(issues, max_issues=3)
    assert [i["code"] for i in selected] == ["A", "C"]


def test_select_top_issues_ranks_by_status_then_confidence() -> None:
    issues = [
        {
            "code": "minor_high_conf",
            "severity": "LOW",
            "status": "MINOR",
            "combined_confidence": 0.95,
        },
        {
            "code": "major_low_conf",
            "severity": "HIGH",
            "status": "MAJOR",
            "combined_confidence": 0.6,
        },
        {
            "code": "moderate",
            "severity": "MEDIUM",
            "status": "MODERATE",
            "combined_confidence": 0.8,
        },
    ]
    selected = select_top_issues(issues, max_issues=2)
    assert [i["code"] for i in selected] == ["major_low_conf", "moderate"]


def test_select_top_issues_ranks_tier1_before_tier2_hints() -> None:
    issues = [
        {"code": "hint", "tier": 2, "status": "MINOR", "severity": "LOW", "combined_confidence": 0.99},
        {"code": "t1_minor", "tier": 1, "status": "MINOR", "severity": "LOW", "combined_confidence": 0.6},
        {"code": "t1_moderate", "tier": 1, "status": "MODERATE", "severity": "MEDIUM", "combined_confidence": 0.6},
    ]
    selected = select_top_issues(issues, max_issues=3)
    assert [i["code"] for i in selected] == ["t1_moderate", "t1_minor", "hint"]


def test_is_tentative_flags() -> None:
    from app.ai.issue_selection import is_tentative

    assert is_tentative({"tier": 2, "reference_validated": True})
    assert is_tentative({"tier": 1, "reference_validated": False})
    assert not is_tentative({"tier": 1, "reference_validated": True})
    assert not is_tentative({"code": "legacy"})
    assert is_tentative({"tentative": True})
