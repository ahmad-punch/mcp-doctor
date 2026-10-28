"""Where a server lives and how to reach it: a command over stdio, or an HTTP endpoint."""

from __future__ import annotations

import shlex
from enum import Enum

from pydantic import BaseModel, Field


class TargetError(ValueError):
    """Raised when a target cannot be built from user input. The message says how to fix it."""


class TransportKind(str, Enum):
    """The MCP transports mcp-doctor can speak."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


class Target(BaseModel):
    """A server definition, normalised from the command line or a client config file."""

    name: str
    transport: TransportKind
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    def describe(self) -> str:
        """A one-line, credential-free description for report headers."""
        if self.transport is TransportKind.STDIO:
            return shlex.join([self.command or "", *self.args])
        return f"{self.url} ({self.transport.value})"


def stdio_target(command_line: str, name: str | None = None) -> Target:
    """Build a stdio target from a shell-style command line such as ``"npx -y pkg /tmp"``."""
    try:
        parts = shlex.split(command_line)
    except ValueError as exc:
        raise TargetError(f"could not parse --stdio command ({exc}); check the quoting") from exc
    if not parts:
        raise TargetError('--stdio needs a command, e.g. --stdio "npx -y @modelcontextprotocol/server-everything"')
    return Target(name=name or parts[0], transport=TransportKind.STDIO, command=parts[0], args=parts[1:])


def url_target(url: str, transport: TransportKind = TransportKind.HTTP, headers: list[str] | None = None) -> Target:
    """Build an HTTP or SSE target. ``headers`` are ``"Name: value"`` strings."""
    if not url.startswith(("http://", "https://")):
        raise TargetError(f"--url must start with http:// or https://, got {url!r}")
    if transport is TransportKind.STDIO:
        raise TargetError("--transport stdio cannot be combined with --url; use --stdio instead")
    return Target(name=url, transport=transport, url=url, headers=parse_headers(headers or []))


def parse_headers(raw: list[str]) -> dict[str, str]:
    """Parse ``--header "Name: value"`` options into a dict."""
    headers: dict[str, str] = {}
    for item in raw:
        name, sep, value = item.partition(":")
        if not sep or not name.strip():
            raise TargetError(f'--header expects "Name: value", got {item!r}')
        headers[name.strip()] = value.strip()
    return headers
