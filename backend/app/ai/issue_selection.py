"""Deterministic technique-issue selection for the coaching prompt payload.

Keeps the on-disk EvidencePackage intact; only the LLM prompt uses the filtered list.
"""

from __future__ import annotations

from typing import Any

# IssueSeverity in schemas/technique.py is LOW / MEDIUM / HIGH
# (mapped from IssueStatus MINOR / MODERATE / MAJOR — not CRITICAL).
SEVERITY_ORDER: dict[str, int] = {
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}

# Prefer calibrated status when present (MAJOR > MODERATE > MINOR).
STATUS_ORDER: dict[str, int] = {
    "MAJOR": 3,
    "MODERATE": 2,
    "MINOR": 1,
}


def select_top_issues(
    technique_issues: list[dict[str, Any]],
    max_issues: int = 3,
) -> list[dict[str, Any]]:
    """Rank deterministically so the LLM explains findings rather than choosing them."""
    reliable = [
        i
        for i in technique_issues
        if not i.get("uncertain")
        and str(i.get("status") or "").upper()
        not in {"INSUFFICIENT_EVIDENCE", "NO_ISSUE"}
    ]

    def _rank(issue: dict[str, Any]) -> tuple[int, int, float]:
        status = str(issue.get("status") or "").upper()
        severity = str(issue.get("severity") or "").upper()
        return (
            STATUS_ORDER.get(status, 0),
            SEVERITY_ORDER.get(severity, 0),
            float(issue.get("combined_confidence") or issue.get("confidence") or 0.0),
        )

    reliable.sort(key=_rank, reverse=True)
    return reliable[: max(0, int(max_issues))]
