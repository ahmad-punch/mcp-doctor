"""End-to-end checks against real servers, in process and over stdio."""

from __future__ import annotations

import sys
import time

import clean_server
import messy_server
from mcp import Client

from conftest import EXAMPLES
from mcp_doctor.doctor import CheckOptions, check_client, check_target
from mcp_doctor.models import Severity, SmokeStatus
from mcp_doctor.smoke import SmokeOptions
from mcp_doctor.targets import stdio_target


async def test_messy_server_reports_expected_rules() -> None:
    report = await check_client(Client(messy_server.server), "messy", CheckOptions())

    assert report.connected
    fired = {f.rule for f in report.findings}
    assert {"T001", "T002", "T006", "T010", "T012", "S001", "R003", "P001", "P002"} <= fired
    assert report.score < 70


async def test_clean_server_has_no_errors_or_warnings() -> None:
    report = await check_client(Client(clean_server.server), "clean", CheckOptions(smoke=SmokeOptions()))

    serious = [f for f in report.findings if f.severity is not Severity.INFO]
    assert serious == []
    assert report.score >= 95
    assert {r.tool: r.status for r in report.smoke}["list_notes"] is SmokeStatus.OK


async def test_smoke_flags_failing_tool_and_skips_unsafe_ones() -> None:
    options = CheckOptions(smoke=SmokeOptions(timeout=5), ignore=frozenset())
    report = await check_client(Client(messy_server.server), "messy", options)

    statuses = {r.tool: r.status for r in report.smoke}
    assert statuses["sync_notes"] is SmokeStatus.TOOL_ERROR
    assert statuses["delete_note"] is SmokeStatus.SKIPPED
    assert "X003" in {f.rule for f in report.findings}


async def test_ignore_suppresses_rules() -> None:
    report = await check_client(Client(messy_server.server), "messy", CheckOptions(ignore=frozenset({"T001", "S001"})))

    assert not {"T001", "S001"} & {f.rule for f in report.findings}


async def test_stdio_transport_and_latency() -> None:
    target = stdio_target(f"{sys.executable} {EXAMPLES / 'clean_server.py'}")
    report = await check_target(target, CheckOptions(timeout=20))

    assert report.connected, report.connection_error
    assert report.snapshot is not None
    assert report.snapshot.server_name == "tidy-notes"
    assert report.snapshot.timings.initialize_ms is not None
    assert report.snapshot.timings.tools_list_ms is not None


async def test_stdio_smoke_timeout() -> None:
    target = stdio_target(f"{sys.executable} {EXAMPLES / 'messy_server.py'}")
    start = time.perf_counter()
    report = await check_target(target, CheckOptions(timeout=20, smoke=SmokeOptions(timeout=0.5)))

    assert {r.tool: r.status for r in report.smoke}["rebuild_index"] is SmokeStatus.TIMEOUT
    assert "X002" in {f.rule for f in report.findings}
    assert time.perf_counter() - start < 15


async def test_unreachable_server_reports_hint() -> None:
    report = await check_target(stdio_target("definitely-not-a-real-command-1234"), CheckOptions(timeout=5))

    assert not report.connected
    assert "Run `definitely-not-a-real-command-1234`" in (report.connection_error or "")
    assert report.score == 0
