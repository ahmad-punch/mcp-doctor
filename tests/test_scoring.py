from __future__ import annotations

from mcp_doctor.models import Finding, Severity
from mcp_doctor.scoring import score


def _finding(rule: str, severity: Severity) -> Finding:
    return Finding(rule=rule, severity=severity, target="tool:x", message="m", hint="h")


def test_clean_server_scores_100() -> None:
    assert score([]) == 100


def test_weights_by_severity() -> None:
    findings = [_finding("T001", Severity.ERROR), _finding("T002", Severity.WARNING), _finding("S001", Severity.INFO)]
    assert score(findings) == 100 - 10 - 4 - 1


def test_one_rule_is_capped() -> None:
    assert score([_finding("T006", Severity.WARNING)] * 50) == 100 - 3 * 4


def test_never_below_zero_and_unreachable_is_zero() -> None:
    errors = [_finding(f"T{i:03}", Severity.ERROR) for i in range(20)]
    assert score(errors) == 0
    assert score([], connected=False) == 0
