"""Run a full check against one server: connect, list, lint, smoke test, score."""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from typing import IO

from mcp import Client

from mcp_doctor.connect import build_client
from mcp_doctor.models import Report
from mcp_doctor.probe import collect, describe_exception, elapsed_ms
from mcp_doctor.rules import lint
from mcp_doctor.rules.engine import sort_findings
from mcp_doctor.scoring import score
from mcp_doctor.smoke import SmokeOptions, run_smoke, smoke_findings
from mcp_doctor.targets import Target, TransportKind

_STDERR_TAIL_LINES = 8


@dataclass(frozen=True)
class CheckOptions:
    """Knobs for a single check run."""

    protocol: str = "auto"
    timeout: float = 30.0
    smoke: SmokeOptions | None = None
    ignore: frozenset[str] = field(default_factory=frozenset)


async def check_target(target: Target, options: CheckOptions) -> Report:
    """Check a server described by ``target``.

    A stdio server's stderr is captured so that, if it fails to start, the report can
    show why instead of interleaving the server's logs with mcp-doctor's output.
    """
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
        client = build_client(target, options.protocol, stderr if target.transport is TransportKind.STDIO else None)
        report = await check_client(client, target.describe(), options)
        if not report.connected:
            report.connection_error = _with_hint(target, report.connection_error or "", _tail(stderr))
        return report


async def check_client(client: Client, label: str, options: CheckOptions) -> Report:
    """Check a server through an unentered ``Client``. Tests use this with in-process servers."""
    client.read_timeout_seconds = options.timeout
    start = time.perf_counter()
    report: Report | None = None
    try:
        async with client:
            snapshot = await collect(client, elapsed_ms(start))
            findings = lint(snapshot, options.ignore)
            smoke = await run_smoke(client, snapshot.tools, options.smoke) if options.smoke else []
            findings = sort_findings([*findings, *smoke_findings(smoke, options.ignore)])
            report = Report(
                target=label, connected=True, snapshot=snapshot, findings=findings, smoke=smoke, score=score(findings)
            )
    except Exception as exc:
        if report is None:
            return Report(target=label, connected=False, connection_error=describe_exception(exc))
    if report is None:  # only reachable if the client swallowed an error during setup
        return Report(target=label, connected=False, connection_error="connection closed during the handshake")
    return report


def _tail(stream: IO[str]) -> str:
    stream.seek(0)
    lines = [line.rstrip() for line in stream.read().splitlines() if line.strip()]
    return "\n".join(lines[-_STDERR_TAIL_LINES:])


def _with_hint(target: Target, error: str, stderr_tail: str) -> str:
    if target.transport is TransportKind.STDIO:
        hint = f"Run `{target.describe()}` by itself to confirm it starts and speaks MCP on stdout."
    else:
        hint = "Check the URL and that the server is running; pass --header for auth or --transport sse for SSE."
    parts = [error, hint]
    if stderr_tail:
        parts.append("Server stderr (last lines):\n" + stderr_tail)
    return "\n".join(parts)
