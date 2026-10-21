"""Data shapes shared by the probe, the rule engine, and the renderers.

Everything the linter looks at is a plain JSON-like ``dict`` taken from the wire, not an
SDK model. Servers in the wild send malformed payloads, and the point of a linter is to
see them as they are rather than as a validating model would normalise them.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

JSONDict = dict[str, Any]


class Severity(str, Enum):
    """How serious a finding is. Ordered from most to least severe."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Lower is more severe; used for sorting and threshold checks."""
        return _SEVERITY_RANK[self]

    def at_least(self, threshold: Severity) -> bool:
        """True when this severity is as serious as ``threshold`` or worse."""
        return self.rank <= threshold.rank


_SEVERITY_RANK = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


class _CamelModel(BaseModel):
    """Base for models that serialise to camelCase JSON for the ``--json`` report."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Finding(_CamelModel):
    """One rule violation against one target (a tool, resource, prompt, or the server)."""

    rule: str
    severity: Severity
    target: str
    message: str
    hint: str


class Timings(_CamelModel):
    """Wall-clock latencies in milliseconds. ``None`` means the step did not run."""

    initialize_ms: float | None = None
    tools_list_ms: float | None = None


class Snapshot(_CamelModel):
    """Everything the probe learned about a server, in wire format.

    Rules run against this object only, so they can be unit tested with fixture dicts
    and never need a live connection.
    """

    server_name: str | None = None
    server_version: str | None = None
    protocol_version: str | None = None
    capabilities: JSONDict = Field(default_factory=dict)
    instructions: str | None = None
    tools: list[JSONDict] = Field(default_factory=list)
    resources: list[JSONDict] = Field(default_factory=list)
    resource_templates: list[JSONDict] = Field(default_factory=list)
    prompts: list[JSONDict] = Field(default_factory=list)
    list_errors: dict[str, str] = Field(default_factory=dict)
    timings: Timings = Field(default_factory=Timings)


class SmokeStatus(str, Enum):
    """Outcome of calling one tool during a smoke test."""

    OK = "ok"
    TOOL_ERROR = "tool_error"
    PROTOCOL_ERROR = "protocol_error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class SmokeResult(_CamelModel):
    """The result of calling a single tool with ``{}`` or user-supplied arguments."""

    tool: str
    status: SmokeStatus
    duration_ms: float | None = None
    detail: str = ""


class Report(_CamelModel):
    """The full outcome of checking one server: what we saw, what we found, the score."""

    target: str
    connected: bool
    connection_error: str | None = None
    snapshot: Snapshot | None = None
    findings: list[Finding] = Field(default_factory=list)
    smoke: list[SmokeResult] = Field(default_factory=list)
    score: int = 0

    def worst_severity(self) -> Severity | None:
        """The most severe finding in the report, or ``None`` when it is clean."""
        if not self.findings:
            return None
        return min((f.severity for f in self.findings), key=lambda s: s.rank)

    def count(self, severity: Severity) -> int:
        """How many findings have exactly this severity."""
        return sum(1 for f in self.findings if f.severity is severity)
