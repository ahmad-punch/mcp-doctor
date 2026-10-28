"""Turn a ``Target`` into an unconnected SDK ``Client``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TextIO

from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from mcp_doctor.targets import Target, TransportKind

PROTOCOL_MODES = ("auto", "legacy")
"""``auto`` tries the 2026 ``server/discover`` handshake and falls back to ``initialize``;
``legacy`` always uses ``initialize``."""


def build_client(target: Target, protocol: str = "auto", stderr: TextIO | None = None) -> Client:
    """Create a client for ``target``. Nothing connects until the client is entered.

    ``stderr`` receives a stdio server's standard error, so it can be shown when the
    server fails to start instead of being interleaved with the report.
    """
    return Client(_transport(target, stderr), mode=protocol, cache=None)


def _transport(target: Target, stderr: TextIO | None) -> Any:
    if target.transport is TransportKind.STDIO:
        params = StdioServerParameters(
            command=target.command or "",
            args=target.args,
            env=target.env or None,
            cwd=target.cwd,
        )
        return stdio_client(params, errlog=stderr) if stderr is not None else stdio_client(params)
    url = target.url or ""
    if target.transport is TransportKind.SSE:
        return sse_client(url, headers=target.headers or None)
    return _streamable_http(url, target.headers)


@asynccontextmanager
async def _streamable_http(url: str, headers: dict[str, str]) -> AsyncIterator[Any]:
    async with (
        create_mcp_http_client(headers=headers or None) as http_client,
        streamable_http_client(url, http_client=http_client) as streams,
    ):
        yield streams
