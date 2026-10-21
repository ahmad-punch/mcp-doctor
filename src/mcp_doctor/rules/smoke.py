"""Rules whose findings come from actually calling tools (``--smoke``)."""

from __future__ import annotations

from mcp_doctor.models import Severity
from mcp_doctor.rules.registry import Scope, declare

PROTOCOL_ERROR = declare(
    "X001",
    Severity.ERROR,
    Scope.SMOKE,
    "Tool call failed with a protocol error",
    "Report tool failures as a result with isError: true instead of raising; the model can then recover.",
)

TIMEOUT = declare(
    "X002",
    Severity.ERROR,
    Scope.SMOKE,
    "Tool call timed out",
    "Make the tool return promptly, or report progress and honour cancellation for long work.",
)

TOOL_ERROR = declare(
    "X003",
    Severity.WARNING,
    Scope.SMOKE,
    "Tool returned isError for a valid call",
    "A call that satisfies the input schema should succeed; tighten the schema or fix the handler.",
)
