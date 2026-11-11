"""Run registered rules against a snapshot and turn violations into findings."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from mcp_doctor.models import Finding, Severity, Snapshot
from mcp_doctor.rules.registry import Rule, all_rules


def lint(snapshot: Snapshot, ignore: Collection[str] = ()) -> list[Finding]:
    """Evaluate every static rule not in ``ignore`` and return findings, most severe first."""
    findings: list[Finding] = []
    for rule in all_rules():
        if rule.check is None or rule.id in ignore:
            continue
        findings.extend(finding(rule, target, message) for target, message in rule.check(snapshot))
    return sort_findings(findings)


def finding(rule: Rule, target: str, message: str) -> Finding:
    """Build a finding that carries the rule's severity and fix hint."""
    return Finding(rule=rule.id, severity=rule.severity, target=target, message=message, hint=rule.hint)


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Order findings by severity, then rule ID, then target, for stable output."""
    return sorted(findings, key=lambda f: (f.severity.rank, f.rule, f.target))


def with_severity(findings: list[Finding], overrides: Mapping[str, Severity]) -> list[Finding]:
    """Apply per-rule severity overrides from the settings file."""
    return [f.model_copy(update={"severity": overrides[f.rule]}) if f.rule in overrides else f for f in findings]
