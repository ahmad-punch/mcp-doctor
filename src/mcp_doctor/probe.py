"""Connect to a server, perform the handshake, and record everything it lists."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from mcp import Client, MCPError
from mcp_types import METHOD_NOT_FOUND, PaginatedResult
from pydantic import BaseModel

from mcp_doctor.models import JSONDict, Snapshot, Timings

MAX_PAGES = 50
"""Stop following ``nextCursor`` after this many pages, so a broken paginator cannot hang the check."""


class ProbeError(Exception):
    """The server could not be reached or the handshake failed. The message says what to try."""


def elapsed_ms(start: float) -> float:
    """Milliseconds since ``start`` (a ``time.perf_counter()`` value), rounded for display."""
    return round((time.perf_counter() - start) * 1000, 1)


async def collect(client: Client, initialize_ms: float) -> Snapshot:
    """List tools, resources, templates and prompts from an entered client."""
    capabilities = client.server_capabilities
    info = client.server_info
    snapshot = Snapshot(
        server_name=info.name if info else None,
        server_version=info.version if info else None,
        protocol_version=client.protocol_version,
        capabilities=capabilities.model_dump(mode="json", by_alias=True, exclude_none=True),
        instructions=client.instructions,
        timings=Timings(initialize_ms=initialize_ms),
    )
    if capabilities.tools is not None:
        start = time.perf_counter()
        snapshot.tools = await _list(snapshot, "tools/list", "tools", lambda c: client.list_tools(cursor=c))
        snapshot.timings.tools_list_ms = elapsed_ms(start)
    if capabilities.resources is not None:
        snapshot.resources = await _list(
            snapshot, "resources/list", "resources", lambda c: client.list_resources(cursor=c)
        )
        snapshot.resource_templates = await _list(
            snapshot,
            "resources/templates/list",
            "resource_templates",
            lambda c: client.list_resource_templates(cursor=c),
            optional=True,
        )
    if capabilities.prompts is not None:
        snapshot.prompts = await _list(snapshot, "prompts/list", "prompts", lambda c: client.list_prompts(cursor=c))
    return snapshot


async def _list(
    snapshot: Snapshot,
    method: str,
    attribute: str,
    fetch: Callable[[str | None], Awaitable[PaginatedResult]],
    *,
    optional: bool = False,
) -> list[JSONDict]:
    """Follow pagination and return items as wire-format dicts.

    Failures are recorded on the snapshot (rule C003) rather than raised, so one broken
    listing does not hide findings from the others. ``optional`` methods may answer
    "method not found" without that counting as a failure.
    """
    items: list[JSONDict] = []
    cursor: str | None = None
    try:
        for _ in range(MAX_PAGES):
            page = await fetch(cursor)
            items.extend(_dump(item) for item in getattr(page, attribute))
            cursor = page.next_cursor
            if not cursor:
                break
    except MCPError as exc:
        if not (optional and exc.code == METHOD_NOT_FOUND):
            snapshot.list_errors[method] = f"{exc.message} (code {exc.code})"
    except Exception as exc:  # malformed responses surface as pydantic or transport errors
        snapshot.list_errors[method] = describe_exception(exc)
    return items


def _dump(item: BaseModel) -> JSONDict:
    return item.model_dump(mode="json", by_alias=True, exclude_none=True)


def describe_exception(exc: BaseException) -> str:
    """A one-line description of an exception, unwrapping task-group exception groups."""
    inner: Any = exc
    while getattr(inner, "exceptions", None):
        inner = inner.exceptions[0]
    if isinstance(inner, MCPError):
        return f"{inner.message} (code {inner.code})"
    text = str(inner).strip().splitlines()[0] if str(inner).strip() else ""
    return f"{type(inner).__name__}: {text}" if text else type(inner).__name__
