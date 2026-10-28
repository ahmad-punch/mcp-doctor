"""Render reports for humans (rich tables) and machines (JSON)."""

from __future__ import annotations

import json

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from mcp_doctor import __version__
from mcp_doctor.models import Report, Severity, SmokeResult, SmokeStatus, Snapshot
from mcp_doctor.rules.registry import Rule

SEVERITY_STYLE = {Severity.ERROR: "bold red", Severity.WARNING: "yellow", Severity.INFO: "cyan"}
SMOKE_STYLE = {
    SmokeStatus.OK: "green",
    SmokeStatus.TOOL_ERROR: "yellow",
    SmokeStatus.PROTOCOL_ERROR: "bold red",
    SmokeStatus.TIMEOUT: "bold red",
    SmokeStatus.SKIPPED: "dim",
}


def to_json(reports: list[Report]) -> str:
    """Serialise reports as the stable ``--json`` document."""
    payload = {
        "tool": "mcp-doctor",
        "version": __version__,
        "reports": [report.model_dump(mode="json", by_alias=True) for report in reports],
    }
    return json.dumps(payload, indent=2)


def print_report(console: Console, report: Report) -> None:
    """Print one report: server summary, findings, smoke results, and the score."""
    if not report.connected or report.snapshot is None:
        console.print(
            Panel(
                Text(report.connection_error or "unknown error"),
                title=Text.assemble(("Could not connect", "bold red"), f" to {report.target}"),
                border_style="red",
            )
        )
        return
    console.print(Panel(_summary(report.target, report.snapshot), title="mcp-doctor", border_style="blue"))
    if report.findings:
        console.print(_findings_table(report))
        console.print(_fixes(report))
    else:
        console.print("[green]No findings.[/]")
    if report.smoke:
        console.print(_smoke_table(report.smoke))
    console.print(_score_line(report))


def print_rules(console: Console, rules: list[Rule]) -> None:
    """Print the rule catalogue for ``mcp-doctor rules``."""
    table = Table(title="mcp-doctor rules", title_justify="left")
    table.add_column("ID", style="bold")
    table.add_column("Severity")
    table.add_column("Scope")
    table.add_column("Checks for")
    for rule in rules:
        table.add_row(
            rule.id, Text(rule.severity.value, style=SEVERITY_STYLE[rule.severity]), rule.scope.value, rule.title
        )
    console.print(table)


def _summary(target: str, snapshot: Snapshot) -> Group:
    name = snapshot.server_name or "(unnamed server)"
    version = f" {snapshot.server_version}" if snapshot.server_version else ""
    timings = snapshot.timings
    lines = [
        Text.assemble((f"{name}{version}", "bold"), f"  protocol {snapshot.protocol_version or '?'}"),
        Text(f"target      {target}", style="dim"),
        Text(
            f"listed      {len(snapshot.tools)} tools, {len(snapshot.resources)} resources, "
            f"{len(snapshot.resource_templates)} templates, {len(snapshot.prompts)} prompts"
        ),
        Text(f"latency     initialize {_ms(timings.initialize_ms)}, tools/list {_ms(timings.tools_list_ms)}"),
    ]
    return Group(*lines)


def _findings_table(report: Report) -> Table:
    table = Table(title="Findings", title_justify="left")
    table.add_column("Severity", no_wrap=True)
    table.add_column("Rule", no_wrap=True)
    table.add_column("Target", overflow="fold")
    table.add_column("Problem", overflow="fold")
    for item in report.findings:
        severity = Text(item.severity.value, style=SEVERITY_STYLE[item.severity])
        table.add_row(severity, item.rule, Text(item.target), Text(item.message))
    return table


def _fixes(report: Report) -> Group:
    """One fix hint per rule that fired, so repeated findings do not repeat advice."""
    hints = {item.rule: item.hint for item in report.findings}
    lines = [Text("How to fix", style="bold")]
    lines.extend(Text.assemble((f"  {rule_id}  ", "bold"), hint) for rule_id, hint in hints.items())
    return Group(*lines)


def _smoke_table(results: list[SmokeResult]) -> Table:
    table = Table(title="Smoke test", title_justify="left")
    table.add_column("Tool")
    table.add_column("Status", no_wrap=True)
    table.add_column("Time", justify="right", no_wrap=True)
    table.add_column("Detail", overflow="fold")
    for result in results:
        status = Text(result.status.value, style=SMOKE_STYLE[result.status])
        table.add_row(Text(result.tool), status, _ms(result.duration_ms), Text(result.detail))
    return table


def _score_line(report: Report) -> Text:
    style = "bold green" if report.score >= 90 else "bold yellow" if report.score >= 70 else "bold red"
    counts = ", ".join(f"{report.count(sev)} {sev.value}" for sev in Severity)
    return Text.assemble("Score ", (f"{report.score}/100", style), f"  ({counts})")


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f} ms"
