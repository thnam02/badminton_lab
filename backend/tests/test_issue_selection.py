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
