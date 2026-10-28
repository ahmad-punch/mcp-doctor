"""Rules about the server as a whole: handshake metadata, latency, and listing failures."""

from __future__ import annotations

from collections.abc import Iterator

from mcp_doctor.models import Severity, Snapshot
from mcp_doctor.rules.registry import Scope, Violation, rule

SLOW_INITIALIZE_MS = 5000.0
SLOW_TOOLS_LIST_MS = 1000.0


@rule(
    "S001",
    Severity.INFO,
    Scope.SERVER,
    "Server sends no `instructions`",
    "Return instructions from initialize: a short paragraph on what the server is for and how its tools fit.",
)
def missing_instructions(snapshot: Snapshot) -> Iterator[Violation]:
    if not (snapshot.instructions or "").strip():
        yield "server", "initialize result carries no instructions"


@rule(
    "S002",
    Severity.WARNING,
    Scope.SERVER,
    "Server exposes no tools, resources, or prompts",
    "Check that handlers are registered before the server starts and that capabilities are advertised.",
)
def empty_server(snapshot: Snapshot) -> Iterator[Violation]:
    listed = snapshot.tools or snapshot.resources or snapshot.resource_templates or snapshot.prompts
    if not listed and not snapshot.list_errors:
        yield "server", "nothing was listed by tools/list, resources/list, or prompts/list"


@rule(
    "C001",
    Severity.WARNING,
    Scope.CONNECTION,
    f"Initialize took longer than {SLOW_INITIALIZE_MS / 1000:g}s",
    "Defer expensive startup work until first use; clients often time out slow servers.",
)
def slow_initialize(snapshot: Snapshot) -> Iterator[Violation]:
    elapsed = snapshot.timings.initialize_ms
    if elapsed is not None and elapsed > SLOW_INITIALIZE_MS:
        yield "server", f"connect + initialize took {elapsed:.0f} ms"


@rule(
    "C002",
    Severity.WARNING,
    Scope.CONNECTION,
    f"tools/list took longer than {SLOW_TOOLS_LIST_MS / 1000:g}s",
    "Build tool definitions once at startup instead of on every tools/list request.",
)
def slow_tools_list(snapshot: Snapshot) -> Iterator[Violation]:
    elapsed = snapshot.timings.tools_list_ms
    if elapsed is not None and elapsed > SLOW_TOOLS_LIST_MS:
        yield "server", f"tools/list took {elapsed:.0f} ms"


@rule(
    "C003",
    Severity.ERROR,
    Scope.CONNECTION,
    "A list request for an advertised capability failed",
    "The server advertised this capability but the request errored; fix the handler or drop the capability.",
)
def list_request_failed(snapshot: Snapshot) -> Iterator[Violation]:
    for method, error in sorted(snapshot.list_errors.items()):
        yield "server", f"{method} failed: {error}"
