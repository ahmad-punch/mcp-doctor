"""The ``mcp-doctor`` command line."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from typing import Annotated

import anyio
import typer
from rich.console import Console

from mcp_doctor import __version__
from mcp_doctor.ci import DEFAULT_WORKFLOW_PATH, write_workflow
from mcp_doctor.config import ConfigError, default_config_paths, load_servers, select_server
from mcp_doctor.doctor import CheckOptions, check_target
from mcp_doctor.models import Report, Severity
from mcp_doctor.render import print_report, print_rules, to_json
from mcp_doctor.rules import all_rules, known_ids
from mcp_doctor.smoke import SmokeArgsError, SmokeOptions, parse_tool_args
from mcp_doctor.targets import Target, TargetError, TransportKind, stdio_target, url_target

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_UNREACHABLE = 3

app = typer.Typer(
    help="Health check and linter for Model Context Protocol servers.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
console = Console()
err_console = Console(stderr=True)


class FailOn(str, Enum):
    """The lowest severity that makes ``check`` exit non-zero."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    NEVER = "never"


class Protocol(str, Enum):
    """Handshake mode passed to the SDK client."""

    AUTO = "auto"
    LEGACY = "legacy"


class UsageError(Exception):
    """Bad command-line input. The message says how to fix it."""


def _version(value: bool) -> None:
    if value:
        console.print(f"mcp-doctor {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show the version and exit.")
    ] = False,
) -> None:
    """Health check and linter for Model Context Protocol servers."""


@app.command()
def check(
    stdio: Annotated[str | None, typer.Option(help="Command that starts the server over stdio.")] = None,
    url: Annotated[str | None, typer.Option(help="URL of a Streamable HTTP or SSE server.")] = None,
    transport: Annotated[TransportKind, typer.Option(help="Transport for --url: http or sse.")] = TransportKind.HTTP,
    header: Annotated[list[str] | None, typer.Option(help='HTTP header for --url, "Name: value". Repeatable.')] = None,
    config: Annotated[Path | None, typer.Option(help="Claude Desktop, Claude Code, or Cursor config file.")] = None,
    server: Annotated[str | None, typer.Option(help="Server name in --config. Omit to check every server.")] = None,
    smoke: Annotated[bool, typer.Option(help="Call tools that need no arguments and report failures.")] = False,
    tool_args: Annotated[
        list[str] | None, typer.Option("--args", help="Arguments for a smoke call: tool='{\"x\": 1}'. Repeatable.")
    ] = None,
    smoke_timeout: Annotated[float, typer.Option(help="Seconds to wait for each smoke call.")] = 10.0,
    timeout: Annotated[float, typer.Option(help="Seconds to wait for each request during the check.")] = 30.0,
    rules: Annotated[str | None, typer.Option(help="Only run these rule IDs, comma separated.")] = None,
    ignore: Annotated[list[str] | None, typer.Option(help="Rule IDs to skip, comma separated. Repeatable.")] = None,
    fail_on: Annotated[FailOn, typer.Option(help="Exit 1 when a finding is at least this severe.")] = FailOn.ERROR,
    json_output: Annotated[bool, typer.Option("--json", help="Print a JSON report instead of tables.")] = False,
    protocol: Annotated[Protocol, typer.Option(help="auto tries the newest handshake; legacy forces initialize.")] = (
        Protocol.AUTO
    ),
) -> None:
    """Connect to an MCP server, lint what it exposes, and print a health report."""
    try:
        targets = _targets(stdio, url, transport, header or [], config, server)
        options = CheckOptions(
            protocol=protocol.value,
            timeout=timeout,
            smoke=SmokeOptions(timeout=smoke_timeout, args=parse_tool_args(tool_args or [])) if smoke else None,
            ignore=frozenset(_skipped_rules(rules, ignore or [])),
        )
    except (UsageError, TargetError, ConfigError, SmokeArgsError) as exc:
        err_console.print(f"[bold red]error:[/] {exc}")
        raise typer.Exit(EXIT_USAGE) from exc
    reports = [anyio.run(check_target, target, options) for target in targets]
    if json_output:
        sys.stdout.write(to_json(reports) + "\n")
    else:
        for report in reports:
            print_report(console, report)
    raise typer.Exit(exit_code(reports, fail_on))


@app.command("rules")
def list_rules() -> None:
    """List every rule with its ID, severity, and what it checks."""
    print_rules(console, all_rules())


@app.command("init-ci")
def init_ci(
    stdio: Annotated[str, typer.Option(help="Command that starts your server, as CI should run it.")],
    output: Annotated[Path, typer.Option(help="Where to write the workflow.")] = DEFAULT_WORKFLOW_PATH,
    fail_on: Annotated[FailOn, typer.Option(help="Severity that fails the build.")] = FailOn.ERROR,
    force: Annotated[bool, typer.Option(help="Overwrite an existing workflow file.")] = False,
) -> None:
    """Write a GitHub Actions workflow that runs mcp-doctor on every push and pull request."""
    try:
        path = write_workflow(output, stdio, fail_on.value, force)
    except FileExistsError as exc:
        err_console.print(f"[bold red]error:[/] {exc}")
        raise typer.Exit(EXIT_USAGE) from exc
    console.print(f"Wrote [bold]{path}[/]. Commit it to run mcp-doctor in CI.")


def exit_code(reports: list[Report], fail_on: FailOn) -> int:
    """3 if any server was unreachable, 1 if findings reach ``fail_on``, else 0."""
    if any(not report.connected for report in reports):
        return EXIT_UNREACHABLE
    if fail_on is FailOn.NEVER:
        return EXIT_OK
    threshold = Severity(fail_on.value)
    worst = [report.worst_severity() for report in reports]
    return EXIT_FINDINGS if any(sev is not None and sev.at_least(threshold) for sev in worst) else EXIT_OK


def _targets(
    stdio: str | None,
    url: str | None,
    transport: TransportKind,
    headers: list[str],
    config: Path | None,
    server: str | None,
) -> list[Target]:
    chosen = [flag for flag, value in (("--stdio", stdio), ("--url", url), ("--config", config)) if value]
    if len(chosen) > 1:
        raise UsageError(f"pass only one of --stdio, --url, --config (got {', '.join(chosen)})")
    if stdio:
        return [stdio_target(stdio)]
    if url:
        return [url_target(url, transport, headers)]
    if config:
        servers = load_servers(config)
        return [select_server(servers, server, config)] if server else list(servers.values())
    raise UsageError(_no_target_message())


def _no_target_message() -> str:
    lines = ["tell mcp-doctor which server to check with --stdio, --url, or --config."]
    for path in default_config_paths():
        try:
            names = ", ".join(sorted(load_servers(path)))
        except ConfigError:
            continue
        lines.append(f"  found {path}: {names}")
        lines.append(f"    try: mcp-doctor check --config '{path}' --server <name>")
    if len(lines) == 1:
        lines.append('  example: mcp-doctor check --stdio "npx -y @modelcontextprotocol/server-everything"')
    return "\n".join(lines)


def _skipped_rules(selected: str | None, ignored: list[str]) -> set[str]:
    known = known_ids()
    skip = {rule_id for item in ignored for rule_id in _split_ids(item)}
    keep = set(_split_ids(selected)) if selected else known
    unknown = sorted((skip | keep) - known)
    if unknown:
        raise UsageError(f"unknown rule ID(s): {', '.join(unknown)}; run `mcp-doctor rules` to list them")
    return skip | (known - keep)


def _split_ids(value: str) -> list[str]:
    return [part.strip().upper() for part in value.split(",") if part.strip()]


def main() -> None:
    """Console-script entry point."""
    app()
