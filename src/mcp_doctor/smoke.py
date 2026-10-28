"""Call tools to see whether they actually work (``--smoke``).

Only tools that can be called safely without guessing are exercised: tools with no
required parameters get ``{}``; tools with required parameters run only when the user
supplies arguments with ``--args``. Tools that look destructive are skipped unless the
user names them explicitly, because a health check must never delete someone's data.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from mcp import Client, MCPError
from mcp_types import MISSING_REQUIRED_CLIENT_CAPABILITY, REQUEST_TIMEOUT, CallToolResult, TextContent

from mcp_doctor.models import Finding, JSONDict, SmokeResult, SmokeStatus
from mcp_doctor.probe import describe_exception, elapsed_ms
from mcp_doctor.rules import smoke as smoke_rules
from mcp_doctor.rules.engine import finding
from mcp_doctor.rules.schema import required_of
from mcp_doctor.rules.tools import suggests_mutation

_DETAIL_LIMIT = 200

_STATUS_RULES = {
    SmokeStatus.PROTOCOL_ERROR: smoke_rules.PROTOCOL_ERROR,
    SmokeStatus.TIMEOUT: smoke_rules.TIMEOUT,
    SmokeStatus.TOOL_ERROR: smoke_rules.TOOL_ERROR,
}


class SmokeArgsError(ValueError):
    """Raised when an ``--args`` value cannot be parsed. The message shows the expected form."""


@dataclass(frozen=True)
class SmokeOptions:
    """How to run the smoke test: per-call timeout and user-supplied arguments by tool name."""

    timeout: float = 10.0
    args: dict[str, JSONDict] = field(default_factory=dict)


def parse_tool_args(raw: list[str]) -> dict[str, JSONDict]:
    """Parse ``--args tool='{"x": 1}'`` options into ``{"tool": {"x": 1}}``."""
    parsed: dict[str, JSONDict] = {}
    for item in raw:
        name, sep, payload = item.partition("=")
        if not sep or not name:
            raise SmokeArgsError(f'--args expects tool=JSON, e.g. --args \'echo={{"message": "hi"}}\', got {item!r}')
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SmokeArgsError(f"--args for {name!r} is not valid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise SmokeArgsError(f"--args for {name!r} must be a JSON object, got {type(value).__name__}")
        parsed[name] = value
    return parsed


async def run_smoke(client: Client, tools: list[JSONDict], options: SmokeOptions) -> list[SmokeResult]:
    """Call every eligible tool once and record what happened."""
    results: list[SmokeResult] = []
    listed = {tool.get("name") for tool in tools}
    for tool in tools:
        name = tool.get("name")
        if not isinstance(name, str):
            continue
        reason = skip_reason(tool, options)
        if reason:
            results.append(SmokeResult(tool=name, status=SmokeStatus.SKIPPED, detail=reason))
            continue
        results.append(await _call(client, name, options.args.get(name, {}), options.timeout))
    results.extend(
        SmokeResult(tool=name, status=SmokeStatus.SKIPPED, detail="--args names a tool the server does not list")
        for name in sorted(options.args)
        if name not in listed
    )
    return results


def skip_reason(tool: JSONDict, options: SmokeOptions) -> str | None:
    """Why a tool should not be called automatically, or ``None`` if it is safe to call."""
    name = str(tool.get("name"))
    if name in options.args:
        return None
    required = required_of(tool.get("inputSchema"))
    if required:
        return f"needs {', '.join(required)}; pass --args '{name}={{...}}' to call it"
    annotations = tool.get("annotations")
    hints: dict[str, Any] = annotations if isinstance(annotations, dict) else {}
    if hints.get("readOnlyHint") is True:
        return None
    if hints.get("destructiveHint") is True or suggests_mutation(name):
        return f"may change state; pass --args '{name}={{}}' to call it anyway"
    return None


async def _call(client: Client, name: str, arguments: JSONDict, timeout: float) -> SmokeResult:
    start = time.perf_counter()
    try:
        result = await client.call_tool(name, arguments, read_timeout_seconds=timeout)
    except MCPError as exc:
        if exc.code == MISSING_REQUIRED_CLIENT_CAPABILITY:
            detail = f"needs a client capability mcp-doctor does not offer: {exc.message}"
            return SmokeResult(tool=name, status=SmokeStatus.SKIPPED, duration_ms=elapsed_ms(start), detail=detail)
        status = SmokeStatus.TIMEOUT if exc.code == REQUEST_TIMEOUT else SmokeStatus.PROTOCOL_ERROR
        detail = f"no response within {timeout:g}s" if status is SmokeStatus.TIMEOUT else describe_exception(exc)
        return SmokeResult(tool=name, status=status, duration_ms=elapsed_ms(start), detail=detail)
    except Exception as exc:  # e.g. structuredContent that fails the declared outputSchema
        return SmokeResult(
            tool=name, status=SmokeStatus.PROTOCOL_ERROR, duration_ms=elapsed_ms(start), detail=describe_exception(exc)
        )
    if result.is_error:
        return SmokeResult(
            tool=name, status=SmokeStatus.TOOL_ERROR, duration_ms=elapsed_ms(start), detail=_first_text(result)
        )
    return SmokeResult(tool=name, status=SmokeStatus.OK, duration_ms=elapsed_ms(start))


def _first_text(result: CallToolResult) -> str:
    for block in result.content:
        if isinstance(block, TextContent):
            text = " ".join(block.text.split())
            return text if len(text) <= _DETAIL_LIMIT else text[: _DETAIL_LIMIT - 3] + "..."
    return "tool returned isError with no text content"


def smoke_findings(results: list[SmokeResult], ignore: frozenset[str] | set[str]) -> Iterator[Finding]:
    """Turn failed smoke calls into findings under the X-series rules."""
    for result in results:
        rule = _STATUS_RULES.get(result.status)
        if rule is not None and rule.id not in ignore:
            yield finding(rule, f"tool:{result.tool}", result.detail)
