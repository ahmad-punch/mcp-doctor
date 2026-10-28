"""Turn findings into a 0-100 health score.

Each finding costs points by severity. A rule stops costing points after
``MAX_COUNTED_PER_RULE`` findings, so one systemic issue (say, 60 tools without
parameter descriptions) cannot hide every other problem behind a zero.
"""

from __future__ import annotations

from collections import Counter

from mcp_doctor.models import Finding, Severity

WEIGHTS = {Severity.ERROR: 10, Severity.WARNING: 4, Severity.INFO: 1}
MAX_COUNTED_PER_RULE = 3


def score(findings: list[Finding], connected: bool = True) -> int:
    """Compute the health score. A server that cannot be reached scores 0."""
    if not connected:
        return 0
    per_rule = Counter(f.rule for f in findings)
    severity_of = {f.rule: f.severity for f in findings}
    penalty = sum(WEIGHTS[severity_of[rule]] * min(count, MAX_COUNTED_PER_RULE) for rule, count in per_rule.items())
    return max(0, 100 - penalty)
